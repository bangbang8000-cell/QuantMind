"""A股个股风险评分卡（v1）。

设计文档：docs/risk_scorecard_design.md

提供基于 `stock_daily_latest` 的确定性风险评分：5 个维度 + 一票否决，输出
0-100 的 risk_score 及各维度明细。计算成本低、可解释、阈值可在配置中调整。

字段单位约定（来自实测）：
- vol_atr_14：绝对价位差（不是百分比）→ 用前必须 / close
- turnover_rate / pct_change：百分数（已 ×100）
- roe：小数（0.31 = 31%）
- pb / pe_ttm：倍数
- amount / float_mv：元
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session
from backend.shared.stock_utils import StockCodeUtil

logger = logging.getLogger(__name__)

# ── 缓存 ────────────────────────────────────────────────────────────────────
_RISK_CACHE_TTL_SECONDS = int(os.getenv("RISK_SCORE_CACHE_TTL_SECONDS", "60"))
_RISK_CACHE_MAX_ENTRIES = int(os.getenv("RISK_SCORE_CACHE_MAX_ENTRIES", "2048"))
_RISK_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


# ── 配置（可被环境变量 / fusion_rules.json 覆盖）────────────────────────────
# v2 权重（设计文档 docs/risk_scorecard_design_v2.md）
DEFAULT_WEIGHTS: dict[str, float] = {
    "liquidity": 0.25,
    "volatility": 0.30,
    "trend": 0.20,
    "overheat": 0.10,
    "fundamental": 0.10,
    "status": 0.05,
}


# ── 数据类 ──────────────────────────────────────────────────────────────────
@dataclass
class DimensionScore:
    score: float                             # 该维度 0-100 分
    reasons: list[str] = field(default_factory=list)


@dataclass
class RiskScoreResult:
    symbol: str                              # 规范化后的前缀格式
    trade_date: str                          # 评分依据的交易日
    risk_score: float                        # 0-100 综合风险
    risk_level: str                          # "极低" / "低" / "中" / "高" / "极高"
    veto: bool                               # 是否被一票否决
    veto_reasons: list[str]
    dimensions: dict[str, DimensionScore]
    weights: dict[str, float]
    snapshot: dict[str, Any]                 # 评分用到的原始字段（便于前端调试）

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "veto": self.veto,
            "veto_reasons": self.veto_reasons,
            "dimensions": {
                k: {"score": round(v.score, 1), "reasons": v.reasons}
                for k, v in self.dimensions.items()
            },
            "weights": self.weights,
            "snapshot": self.snapshot,
        }


# ── 维度评分函数（纯函数，便于单元测试）────────────────────────────────────
def _veto(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """一票否决：ST/次新/停牌/涨停封板/巨幅+巨量。任一触发即 risk=100。"""
    reasons: list[str] = []
    if (row.get("is_st") or 0) == 1:
        reasons.append("ST 股或退市预警")
    if (row.get("listed_days") or 9999) < 90:
        reasons.append(f"次新股（上市 {row.get('listed_days')} 天 < 90）")
    if (row.get("volume") or 0) == 0:
        reasons.append("当日停牌（成交量 = 0）")
    pct = row.get("pct_change")
    tor = row.get("turnover_rate")
    if pct is not None and tor is not None and pct > 9.5 and tor < 1.0:
        reasons.append("涨停封板（追单成交概率低）")
    # v2 新增：巨幅波动 + 巨量 = 高概率黑天鹅
    amt_ratio = row.get("amount_ratio_5d")
    if (
        pct is not None
        and amt_ratio is not None
        and abs(pct) > 8.0
        and amt_ratio > 2.0
    ):
        reasons.append(
            f"巨幅波动 {pct:+.1f}% + 巨量（{amt_ratio:.1f}× 5日均），疑似黑天鹅"
        )
    return (len(reasons) > 0), reasons


def _score_liquidity(row: dict[str, Any]) -> DimensionScore:
    """流动性维度：20日均成交额 + 流通市值 + 换手率异常。"""
    reasons: list[str] = []
    score = 0.0

    amt = row.get("amount_20d_avg")
    if amt is None:
        reasons.append("缺少 20 日成交额数据")
    elif amt < 1e7:
        score += 100; reasons.append(f"日均成交额 {amt/1e4:.0f} 万 < 1000 万（极度危险）")
    elif amt < 3e7:
        score += 70; reasons.append(f"日均成交额 {amt/1e4:.0f} 万 < 3000 万（高风险）")
    elif amt < 5e7:
        score += 40; reasons.append(f"日均成交额 {amt/1e4:.0f} 万 < 5000 万（中等）")
    elif amt < 1e8:
        score += 15

    fmv = row.get("float_mv")
    if fmv is not None:
        if fmv < 1e9:
            score += 20; reasons.append(f"流通市值 {fmv/1e8:.1f} 亿 < 10 亿（超小盘）")
        elif fmv < 2e9:
            score += 10; reasons.append(f"流通市值 {fmv/1e8:.1f} 亿 < 20 亿（小盘）")

    tor = row.get("turnover_rate")
    if tor is not None:
        if tor > 15:
            score += 15; reasons.append(f"换手率 {tor:.1f}% > 15%（投机泡沫）")
        elif tor < 0.3:
            score += 8; reasons.append(f"换手率 {tor:.2f}% < 0.3%（流动性停滞）")

    return DimensionScore(score=min(100.0, score), reasons=reasons)


def _score_volatility(row: dict[str, Any]) -> DimensionScore:
    """波动率+量能维度（v2 改造）：ATR + 当日异动 + 波动率扩张 + 量价配合。"""
    reasons: list[str] = []
    score = 0.0

    # 子项 A：基础 ATR
    atr = row.get("vol_atr_14")
    close = row.get("close")
    if atr is not None and close and close > 0:
        atr_pct = atr / close * 100
        if atr_pct > 8:
            score += 80; reasons.append(f"ATR {atr_pct:.1f}% > 8%（极端波动）")
        elif atr_pct > 6:
            score += 55; reasons.append(f"ATR {atr_pct:.1f}% > 6%（高波动）")
        elif atr_pct > 4.5:
            score += 30; reasons.append(f"ATR {atr_pct:.1f}% > 4.5%（偏高）")
        else:
            score += 10
    else:
        reasons.append("缺少 ATR 数据")

    # 子项 B：当日异动
    pct = row.get("pct_change")
    if pct is not None and abs(pct) > 7:
        score += 15; reasons.append(f"当日涨跌 {pct:+.2f}%（异动）")

    # 子项 C：波动率扩张（v2 新增）
    vs5, vs20 = row.get("vol_std_5"), row.get("vol_std_20")
    if vs5 is not None and vs20 and vs20 > 0:
        expansion = vs5 / vs20
        if expansion > 1.8:
            score += 30
            reasons.append(f"短期波动率扩张 {expansion:.2f}× > 1.8（情绪失控）")
        elif expansion > 1.4:
            score += 15
            reasons.append(f"短期波动率扩张 {expansion:.2f}× > 1.4")

    # 子项 D：量价配合（v2 新增，amount_ratio_5d 由 SQL CTE 计算）
    amt_ratio = row.get("amount_ratio_5d")
    if pct is not None and amt_ratio is not None and amt_ratio > 0:
        if pct < -3 and amt_ratio > 1.5:
            score += 50; reasons.append(
                f"放量下跌（{pct:+.1f}% / 量比 {amt_ratio:.1f}×，疑似主力出货）"
            )
        elif pct > 2 and amt_ratio < 0.8:
            score += 40; reasons.append(
                f"缩量上涨（{pct:+.1f}% / 量比 {amt_ratio:.1f}×，弱势反弹）"
            )
        elif pct < -2 and amt_ratio < 0.8:
            score += 20; reasons.append(
                f"缩量下跌（{pct:+.1f}% / 量比 {amt_ratio:.1f}×，阴跌）"
            )
        elif pct > 2 and amt_ratio > 1.2:
            score -= 10; reasons.append(
                f"放量上涨（{pct:+.1f}% / 量比 {amt_ratio:.1f}×，健康行情）"
            )

    return DimensionScore(score=max(0.0, min(100.0, score)), reasons=reasons)


def _score_trend(row: dict[str, Any]) -> DimensionScore:
    """趋势维度：跌破 ma60、均线空头排列、MACD 死叉、跌破 ma20。"""
    reasons: list[str] = []
    score = 0.0
    close = row.get("close")
    ma5, ma10, ma20, ma60 = (row.get(k) for k in ("ma5", "ma10", "ma20", "ma60"))
    macd_hist = row.get("macd_hist")

    if close is not None and ma60 is not None and close < ma60:
        score += 40; reasons.append("跌破 60 日均线（中期趋势走坏）")
    if all(v is not None for v in (ma5, ma10, ma20, ma60)) and ma5 < ma10 < ma20 < ma60:
        score += 30; reasons.append("均线空头排列（5<10<20<60）")
    if macd_hist is not None and macd_hist < 0:
        score += 20; reasons.append("MACD 死叉（红柱转绿）")
    if close is not None and ma20 is not None and close < ma20:
        score += 10; reasons.append("跌破 20 日均线")

    return DimensionScore(score=min(100.0, score), reasons=reasons)


def _score_fundamental(row: dict[str, Any]) -> DimensionScore:
    """基本面维度：ROE、PB、PE。"""
    reasons: list[str] = []
    score = 0.0

    roe = row.get("roe")
    if roe is not None:
        if roe < -0.05:
            score += 50; reasons.append(f"ROE {roe*100:.1f}% < -5%（严重亏损）")
        elif roe < 0:
            score += 30; reasons.append(f"ROE {roe*100:.1f}% < 0（亏损）")
        elif roe < 0.03:
            score += 15; reasons.append(f"ROE {roe*100:.1f}% < 3%（盈利能力弱）")

    pb = row.get("pb")
    if pb is not None:
        if pb < 0.8:
            score += 20; reasons.append(f"PB {pb:.2f} < 0.8（警惕净资产穿仓）")
        elif pb < 1.0:
            score += 10; reasons.append(f"PB {pb:.2f} < 1.0（折价）")

    pe = row.get("pe_ttm")
    if pe is not None:
        if pe < 0:
            score += 20; reasons.append(f"PE {pe:.1f} < 0（亏损公司）")
        elif pe > 200:
            score += 15; reasons.append(f"PE {pe:.0f} > 200（估值泡沫）")

    return DimensionScore(score=min(100.0, score), reasons=reasons)


def _score_status(row: dict[str, Any]) -> DimensionScore:
    """状态维度（非否决部分）：连板涨停次数。"""
    reasons: list[str] = []
    score = 0.0
    clud = row.get("consecutive_limit_up_days") or 0
    if clud >= 3:
        score += 60; reasons.append(f"连板 {clud} 天 ≥ 3（追高极险）")
    elif clud >= 2:
        score += 30; reasons.append(f"连板 {clud} 天")
    return DimensionScore(score=min(100.0, score), reasons=reasons)


def _score_overheat(row: dict[str, Any]) -> DimensionScore:
    """过热维度（v2 新增）：短期超涨 + 超买共振。

    设计要点：
    - 单纯 RSI 高不打分（强势股长期 RSI 在 60-80）
    - 必须 RSI 超买 + 短期累计涨幅高 才计入
    - KDJ 仅用于与 RSI 共振，单独不打分
    - return_5d / _20d 必须 clip 到 (-0.99, 5.0) 防指数/异常值污染
    """
    reasons: list[str] = []
    score = 0.0

    # clip 防异常值（如指数 399300 的 return_5d=1039）
    def _clip(x):
        if x is None:
            return None
        return max(-0.99, min(5.0, float(x)))

    r5 = _clip(row.get("return_5d"))
    r20 = _clip(row.get("return_20d"))
    rsi = row.get("rsi_14")
    kdj = row.get("kdj_k")

    # 子项 A：短期暴涨
    if r5 is not None:
        if r5 > 0.25:
            score += 60; reasons.append(f"5 日累计 {r5*100:.1f}% > 25%（短期暴涨）")
        elif r5 > 0.15:
            score += 30; reasons.append(f"5 日累计 {r5*100:.1f}% > 15%（短期强涨）")

    # 子项 B：月度大涨
    if r20 is not None:
        if r20 > 0.50:
            score += 20; reasons.append(f"20 日累计 {r20*100:.0f}% > 50%（月度翻倍）")
        elif r20 > 0.30:
            score += 10; reasons.append(f"20 日累计 {r20*100:.0f}% > 30%")

    # 子项 C：超买共振（必须叠加短期上涨）
    if rsi is not None:
        if rsi > 80 and r5 is not None and r5 > 0.15:
            score += 50; reasons.append(f"RSI {rsi:.0f} > 80 且 5 日强涨（强超买）")
        elif rsi > 75 and r5 is not None and r5 > 0.10:
            score += 30; reasons.append(f"RSI {rsi:.0f} > 75 且 5 日上涨（中度超买）")
        elif rsi > 75 and kdj is not None and kdj > 85:
            score += 25; reasons.append(f"RSI {rsi:.0f} + KDJ {kdj:.0f} 共振超买")

    return DimensionScore(score=min(100.0, score), reasons=reasons)


# ── 等级 ──────────────────────────────────────────────────────────────────
def _bucket(score: float) -> str:
    if score >= 80: return "极高"
    if score >= 60: return "高"
    if score >= 40: return "中"
    if score >= 20: return "低"
    return "极低"


# ── 数据获取 + 聚合 ────────────────────────────────────────────────────────
# v2: 同时拉 20 日均成交额（流动性维度）和 5 日均成交额（量价配合子项）
#
# 日期语义：
# - target_day: 评分基于的交易日（推理批次日 / 用户指定日 / 最新日）
#   * 若 :td IS NULL → 取该 symbol 在表里的最新交易日（向后兼容）
#   * 否则取 ≤ :td 的最近一个交易日（容忍非交易日传入，自动落到前一交易日）
_FETCH_SQL = f"""
WITH target_day AS (
    SELECT MAX(trade_date) AS d FROM stock_daily_latest
    WHERE symbol = :s
      AND (cast(:td as date) IS NULL OR trade_date <= cast(:td as date))
),
amt_20d AS (
    SELECT AVG(amount) AS amount_20d_avg
    FROM stock_daily_latest s, target_day l
    WHERE s.symbol = :s
      AND s.trade_date BETWEEN l.d - INTERVAL '30 day' AND l.d
),
amt_5d AS (
    -- 5 日均成交额：用过去 5 个交易日（不含当日），所以 BETWEEN d-8 AND d-1
    SELECT AVG(amount) AS amount_5d_avg
    FROM stock_daily_latest s, target_day l
    WHERE s.symbol = :s
      AND s.trade_date BETWEEN l.d - INTERVAL '8 day' AND l.d - INTERVAL '1 day'
)
SELECT s.trade_date, s.symbol, s.stock_name, s.industry,
       s.close, s.open, s.high, s.low, s.volume, s.amount,
       s.pct_change, s.turnover_rate, s.vol_atr_14,
       s.vol_std_5, s.vol_std_20,
       s.float_mv, s.total_mv,
       s.ma5, s.ma10, s.ma20, s.ma60, s.macd_hist,
       s.pb, s.pe_ttm, s.roe,
       s.is_st, s.listed_days, s.consecutive_limit_up_days,
       s.rsi_14, s.kdj_k, s.return_5d, s.return_20d,
       a20.amount_20d_avg, a5.amount_5d_avg,
       CASE WHEN a5.amount_5d_avg IS NOT NULL AND a5.amount_5d_avg > 0
            THEN s.amount / a5.amount_5d_avg ELSE NULL END AS amount_ratio_5d
FROM stock_daily_latest s, target_day l, amt_20d a20, amt_5d a5
WHERE s.symbol = :s
  AND s.trade_date = l.d
LIMIT 1
"""


async def _fetch_snapshot(symbol: str, trade_date: date | None = None) -> dict[str, Any] | None:
    """读取一只票指定交易日的快照 + 20/5 日均成交额。

    若 trade_date=None，取 symbol 在表里的最新交易日。
    若指定 trade_date，取 ≤ trade_date 的最近一个交易日。
    """
    async with get_session(read_only=True) as session:
        res = await session.execute(text(_FETCH_SQL), {"s": symbol, "td": trade_date})
        row = res.mappings().first()
    return dict(row) if row else None


def _compute_from_row(row: dict[str, Any]) -> RiskScoreResult:
    """纯函数：根据已经查好的 row 算评分，便于单元测试和批量。"""
    symbol = str(row.get("symbol") or "")
    trade_date = row.get("trade_date")
    trade_date_str = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date or "")

    veto, veto_reasons = _veto(row)

    dims = {
        "liquidity": _score_liquidity(row),
        "volatility": _score_volatility(row),
        "trend": _score_trend(row),
        "overheat": _score_overheat(row),
        "fundamental": _score_fundamental(row),
        "status": _score_status(row),
    }

    if veto:
        risk_score = 100.0
    else:
        risk_score = sum(DEFAULT_WEIGHTS[k] * dims[k].score for k in DEFAULT_WEIGHTS)

    # 透出原始字段方便前端展示和 debug；过滤 None 以避免 JSON 噪声
    snapshot_keys = (
        "stock_name", "industry", "close", "pct_change", "turnover_rate",
        "vol_atr_14", "vol_std_5", "vol_std_20",
        "float_mv", "total_mv",
        "ma5", "ma10", "ma20", "ma60", "macd_hist",
        "pb", "pe_ttm", "roe",
        "is_st", "listed_days", "consecutive_limit_up_days",
        "rsi_14", "kdj_k", "return_5d", "return_20d",
        "amount_20d_avg", "amount_5d_avg", "amount_ratio_5d",
    )
    snapshot = {k: row.get(k) for k in snapshot_keys if row.get(k) is not None}

    return RiskScoreResult(
        symbol=StockCodeUtil.to_prefix(symbol),
        trade_date=trade_date_str,
        risk_score=risk_score,
        risk_level=_bucket(risk_score),
        veto=veto,
        veto_reasons=veto_reasons,
        dimensions=dims,
        weights=dict(DEFAULT_WEIGHTS),
        snapshot=snapshot,
    )


def _parse_trade_date(value: date | str | None) -> date | None:
    """容忍 None / 'YYYY-MM-DD' / date / datetime；非法格式返回 None（回落到最新日）。"""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ── 对外入口 ──────────────────────────────────────────────────────────────
async def compute_risk_score(
    symbol: str,
    trade_date: date | str | None = None,
) -> dict[str, Any]:
    """单票风险评分。结果带 60s 内存缓存。

    Args:
        symbol: 股票代码，前缀或后缀格式都接受。
        trade_date: 评分基于的交易日。None=最新日；指定日期=取 ≤ 该日的最近交易日。
                    支持 date / 'YYYY-MM-DD' 字符串两种格式。非法格式静默回落到 None。

    返回结构见 RiskScoreResult.to_dict()。若该 symbol 在指定区间查不到任何行，
    返回 {"symbol": ..., "error": "no_data"}。
    """
    normalized = StockCodeUtil.to_prefix(symbol)
    td = _parse_trade_date(trade_date)
    cache_key = f"risk-score:{normalized}:{td.isoformat() if td else 'latest'}"

    now = time.monotonic()
    cached = _RISK_CACHE.get(cache_key)
    if cached and (now - cached[0]) <= _RISK_CACHE_TTL_SECONDS:
        return cached[1]

    row = await _fetch_snapshot(normalized, td)
    if row is None:
        payload = {"symbol": normalized, "error": "no_data"}
    else:
        payload = _compute_from_row(row).to_dict()

    _RISK_CACHE[cache_key] = (now, payload)
    if len(_RISK_CACHE) > _RISK_CACHE_MAX_ENTRIES:
        oldest_key = min(_RISK_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _RISK_CACHE.pop(oldest_key, None)
    return payload


async def compute_risk_scores_batch(
    symbols: list[str],
    trade_date: date | str | None = None,
) -> dict[str, dict[str, Any]]:
    """批量评分。对每个 symbol 调单票版本（带缓存）。

    Args:
        symbols: 股票代码列表。
        trade_date: 评分基于的交易日（统一应用到所有 symbol）。
    """
    out: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for s in symbols:
        if not s:
            continue
        norm = StockCodeUtil.to_prefix(s)
        if norm in seen:
            continue
        seen.add(norm)
        try:
            out[norm] = await compute_risk_score(norm, trade_date)
        except Exception as exc:
            logger.warning("compute_risk_score(%s) failed: %s", s, exc)
            out[norm] = {"symbol": norm, "error": "compute_failed"}
    return out
