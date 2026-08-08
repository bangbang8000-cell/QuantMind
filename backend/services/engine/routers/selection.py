"""选股 API — 实盘选股（策略文档 v2.0）。

数据流:
  engine_signal_scores (DB)  →  读取最新/指定交易日信号
      →  申万行业映射 → 行业信号（avgTop1、强行业数、市场状态）
      →  个股分数区间 + 主板 + ST/涨跌停 + 3 天趋势过滤
      →  返回候选股、行业排行、被排除示例

口径说明:
  - engine_signal_scores.trade_date 存的是「信号生效日」(T+1)，与回测引擎一致：
    取 trade_date 作为「推理完成日」，买入在 T+1 执行。
  - symbol 格式混杂（sh600519 / 600036.SH / SH600036），统一经 StockCodeUtil.to_suffix 归一。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from time import time as _now
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session
from backend.shared.stock_utils import StockCodeUtil

from backend.services.engine.auth_context import get_authenticated_identity
from backend.services.engine.inference.inference_backtest_service import (
    _compute_industry_signals,
    _market_state,
    _select_stocks_daily,
    StrategyConfig,
)
from backend.services.engine.inference.shenwan_industry import (
    load_shenwan_industry_map,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/selection", tags=["Selection"])

# 策略预设参数（与回测引擎 preset 对齐）
_PRESETS: dict[str, dict[str, float | int]] = {
    "conservative": {"entry": 0.10, "exit": 0.10, "strong_min": 5},
    "balanced": {"entry": 0.09, "exit": 0.06, "strong_min": 2},
    "aggressive": {"entry": 0.07, "exit": 0.06, "strong_min": 1},
}


def _resolve_config(strategy: str) -> StrategyConfig:
    preset = _PRESETS.get(strategy, _PRESETS["balanced"])
    cfg = StrategyConfig()
    cfg.entry_threshold = float(preset["entry"])
    cfg.exit_threshold = float(preset["exit"])
    cfg.strong_industry_min = int(preset["strong_min"])
    return cfg


def _position_advice(avg_top1: float, strong_count: int) -> dict[str, str]:
    """按仓位管理表给出仓位建议。"""
    if avg_top1 >= 0.12 and strong_count >= 5:
        return {"position": "100%", "reason": "牛市，满仓可追强信号"}
    if avg_top1 >= 0.10 and strong_count >= 3:
        return {"position": "50%", "reason": "震荡偏强，半仓只做强区间"}
    if avg_top1 >= 0.09 and strong_count >= 2:
        return {"position": "30%", "reason": "震荡，轻仓快进快出"}
    if avg_top1 >= 0.06:
        return {"position": "0-30%", "reason": "震荡偏弱，观望或极轻仓"}
    return {"position": "0%", "reason": "熊市，绝对空仓"}


async def _load_signal_day(
    tenant_id: str,
    user_id: str,
    trade_date: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    """读取指定交易日（或最新）的信号。返回 (resolved_date, [{symbol, fusion_score}])。"""
    params: dict[str, Any] = {"tenant_id": tenant_id, "user_id": user_id}

    if trade_date:
        params["trade_date"] = date.fromisoformat(trade_date)
        where = "s.trade_date = :trade_date"
    else:
        where = """
            s.trade_date = (
                SELECT MAX(trade_date) FROM engine_signal_scores
                WHERE tenant_id = :tenant_id AND user_id = :user_id
            )
        """

    query = text(
        f"""
        SELECT s.symbol, s.fusion_score, s.trade_date
        FROM engine_signal_scores s
        WHERE s.tenant_id = :tenant_id AND s.user_id = :user_id AND {where}
        ORDER BY s.fusion_score DESC
        """
    )

    rows = []
    async with get_session(read_only=True) as session:
        result = await session.execute(query, params)
        rows = result.mappings().all()

    if not rows:
        return (trade_date or "", [])

    resolved_date = str(rows[0]["trade_date"] or trade_date or "")
    signals = [
        {"symbol": str(r["symbol"]).upper(), "fusion_score": float(r["fusion_score"])}
        for r in rows
        if r["fusion_score"] is not None
    ]
    return (resolved_date, signals)


async def _load_stock_names(
    symbols: list[str],
) -> dict[str, str]:
    """批量查股票名称（stock_daily_latest.stock_name，symbol 前缀格式）。"""
    if not symbols:
        return {}
    prefix_map: dict[str, str] = {}
    for s in symbols:
        try:
            prefix_map[StockCodeUtil.to_prefix(s)] = s
        except Exception:
            continue
    if not prefix_map:
        return {}

    result_map: dict[str, str] = {}
    async with get_session(read_only=True) as session:
        for chunk in _chunks(list(prefix_map.keys()), 500):
            q = text(
                """
                SELECT DISTINCT ON (symbol) symbol, stock_name
                FROM stock_daily_latest
                WHERE symbol = ANY(:codes)
                  AND stock_name IS NOT NULL AND stock_name != ''
                ORDER BY symbol, trade_date DESC
                """
            )
            res = await session.execute(q, {"codes": chunk})
            for row in res.mappings():
                prefix = str(row["symbol"] or "").strip().upper()
                suffix = prefix_map.get(prefix)
                if suffix:
                    result_map[suffix] = str(row["stock_name"] or "")
    return result_map


def _chunks(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


async def _load_index_above_ma20(target_date: str | None = None) -> tuple[bool, str]:
    """上证指数在指定日期（缺省最新）收盘 vs MA20。"""
    try:
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        hub = QuantDBDataHub()
        end = date.fromisoformat(target_date) if target_date else date.today()
        start = end - timedelta(days=40)
        df = hub.fetch_index_kline("000001.SH", start, end)
        if df is None or df.empty:
            return True, "无指数数据"
        df = df.sort_values("trade_date")
        close = df["close"].astype(float)
        close.index = pd.DatetimeIndex(pd.to_datetime(df["trade_date"]))
        # 取 target_date 当日（或之前最近一日）的收盘与 MA20
        up_to = close.loc[:pd.Timestamp(end)]
        if len(up_to) < 20:
            return True, "指数数据不足20日"
        last = float(up_to.iloc[-1])
        ma20 = float(up_to.rolling(20).mean().iloc[-1])
        return (last >= ma20, f"上证{last:.0f}/MA20{ma20:.0f}")
    except Exception as exc:
        logger.warning("加载指数 MA20 失败: %s", exc)
        return True, "指数数据不可用"


async def _load_price_flags(
    trade_date: str,
    symbols: list[str],
) -> dict[str, dict[str, Any]]:
    """加载个股价格/涨跌停/ST 标记（stock_daily_latest，当日或最近一条）。

    用于实盘过滤涨停买不进/跌停卖不出、ST 剔除。取当日若缺失则取最近一日。
    """
    if not symbols:
        return {}
    normalized = {StockCodeUtil.to_prefix(s): s for s in symbols}
    flags: dict[str, dict[str, Any]] = {}
    d_param = date.fromisoformat(trade_date) if trade_date else None
    if d_param is None:
        return {}
    async with get_session(read_only=True) as session:
        seen: set[str] = set()
        for chunk in _chunks(list(normalized.keys()), 300):
            # DISTINCT ON 取每个 symbol 最新一条（<= trade_date），避免拉全历史
            q = text(
                """
                SELECT DISTINCT ON (symbol) symbol, trade_date, pct_change, is_st
                FROM stock_daily_latest
                WHERE symbol = ANY(:codes)
                  AND trade_date <= :d
                ORDER BY symbol, trade_date DESC
                """
            )
            res = await session.execute(q, {"codes": chunk, "d": d_param})
            for row in res.mappings():
                sym = str(row["symbol"] or "").strip().upper()
                suffix = normalized.get(sym)
                if suffix is None or suffix in seen:
                    continue
                seen.add(suffix)
                flags[suffix] = {
                    "pct_change": float(row["pct_change"]) if row["pct_change"] is not None else None,
                    "is_st": int(row["is_st"] or 0),
                }
    return flags


@router.get("/daily")
async def daily_selection(
    request: Request,
    strategy: str = Query("balanced"),
    date: str | None = Query(None, description="信号交易日，缺省取最新"),
    ignore_ma20: bool = Query(False, description="勾选后忽略大盘MA20强制空仓，允许入场"),
):
    """今日选股：市场状态 + 行业排行 + 候选股 + 被排除示例。"""
    user_id, tenant_id = get_authenticated_identity(request)
    cfg = _resolve_config(strategy)

    # 1. 读信号
    trade_date, signals = await _load_signal_day(tenant_id, user_id, date)
    if not signals:
        return {
            "status": "success",
            "meta": {"trade_date": trade_date or None, "strategy": strategy, "total_signals": 0},
            "market_state": {"state": "无信号", "should_enter": False, "position_advice": "0%"},
            "industry_signals": [],
            "candidates": [],
            "excluded_examples": [],
            "warnings": [f"无推理信号（tenant={tenant_id}, user={user_id}, date={date or '最新'}）"],
        }

    # 2. 归一化 symbol → DataFrame[symbol, score]
    day_scores = pd.DataFrame(
        [{"symbol": s["symbol"], "score": s["fusion_score"]} for s in signals]
    )
    day_scores["symbol"] = day_scores["symbol"].map(StockCodeUtil.to_suffix)
    day_scores = day_scores.drop_duplicates(subset="symbol", keep="last")

    # 3. 行业信号
    industry_map = load_shenwan_industry_map()
    ind_top1, ind_count, avg_top1, strong_count = _compute_industry_signals(
        day_scores, industry_map
    )
    state = _market_state(avg_top1, strong_count)
    index_above_ma20, index_detail = await _load_index_above_ma20(trade_date or None)
    position = _position_advice(avg_top1, strong_count)

    # 4. 入场判断 + 选股
    ma20_ok = index_above_ma20 or ignore_ma20
    should_enter = (
        ma20_ok
        and avg_top1 >= cfg.entry_threshold
        and strong_count >= cfg.strong_industry_min
    )
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    if should_enter:
        # 只对分数区间内的候选股查价格/ST 标记（避免全市场 19 批查询）
        score_mask = (day_scores["score"] >= cfg.score_min) & (day_scores["score"] <= cfg.score_max)
        if cfg.main_board_only:
            score_mask &= day_scores["symbol"].apply(_is_main_board_code)
        score_mask &= ~day_scores["symbol"].apply(_is_star_market_code)
        cand_symbols = day_scores.loc[score_mask, "symbol"].tolist()
        price_flags = await _load_price_flags(trade_date, cand_symbols)
        # 把实盘价格/ST 标记转成回测选股所需的 price_day DataFrame
        price_rows = [
            {
                "symbol": sym,
                "pct_change": fl["pct_change"],
                "is_st": fl["is_st"],
            }
            for sym, fl in price_flags.items()
        ]
        price_day = pd.DataFrame(price_rows) if price_rows else pd.DataFrame()
        picks = _select_stocks_daily(day_scores, industry_map, cfg, price_day)
        candidates = picks
    else:
        reason = []
        if not index_above_ma20 and not ignore_ma20:
            reason.append(f"大盘跌破MA20（{index_detail}）")
        if avg_top1 < cfg.entry_threshold:
            reason.append(f"行业avgTop1={avg_top1:.3f} 低于入场线{cfg.entry_threshold}")
        if strong_count < cfg.strong_industry_min:
            reason.append(f"强行业数{strong_count} 低于阈值{cfg.strong_industry_min}")
        excluded.append({
            "symbol": "", "score": 0, "reason": "未入场",
            "detail": "；".join(reason) or "市场状态不满足入场条件",
        })

    # 5. 行业排行（Top1 排序前 15，单次 groupby 取各行业最高分股）
    top_stock_by_ind = _top_stock_by_industry(day_scores, industry_map)
    industry_signals = sorted(
        [{"industry": i, "top1": v, "stock": top_stock_by_ind.get(i, "")}
         for i, v in ind_top1.items()],
        key=lambda x: -x["top1"],
    )[:15]

    # 6. 股票名称补齐
    cand_symbols = [c["symbol"] for c in candidates]
    name_map = await _load_stock_names(cand_symbols)
    for c in candidates:
        c["name"] = name_map.get(c["symbol"], "")
        # 买入理由
        reasons = ["黄金区间" if cfg.score_min <= c["score"] <= cfg.score_max else "分数区间"]
        if c.get("trend") in ("先升后降", "上升中", "明日回落"):
            reasons.append("先升后降")
        if _is_main_board_code(c["symbol"]):
            reasons.append("主板")
        ind = c.get("industry", "")
        if ind in ind_top1 and ind_top1[ind] >= cfg.entry_threshold:
            reasons.append("行业确认")
        c["buy_reason"] = "+".join(reasons)
        c["warnings"] = []

    return {
        "status": "success",
        "meta": {
            "trade_date": trade_date,
            "strategy": strategy,
            "total_signals": len(signals),
            "strategy_config": {
                "entry_threshold": cfg.entry_threshold,
                "exit_threshold": cfg.exit_threshold,
                "strong_industry_min": cfg.strong_industry_min,
                "score_min": cfg.score_min,
                "score_max": cfg.score_max,
                "max_positions": cfg.max_positions,
            },
        },
        "market_state": {
            "state": state,
            "avg_top1": round(avg_top1, 4),
            "strong_count": strong_count,
            "index_above_ma20": index_above_ma20,
            "index_detail": index_detail,
            "ignore_ma20": ignore_ma20,
            "should_enter": should_enter,
            "position": position["position"],
            "position_reason": position["reason"],
        },
        "industry_signals": industry_signals,
        "candidates": candidates,
        "excluded_examples": excluded,
        "warnings": [],
    }


@router.get("/history")
async def selection_history(
    request: Request,
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    strategy: str = Query("balanced"),
):
    """历史选股（按天重算，供回看）。"""
    user_id, tenant_id = get_authenticated_identity(request)
    cfg = _resolve_config(strategy)
    industry_map = load_shenwan_industry_map()

    query = text(
        """
        SELECT trade_date, symbol, fusion_score
        FROM engine_signal_scores
        WHERE tenant_id = :tenant_id AND user_id = :user_id
          AND trade_date BETWEEN :from AND :to
        ORDER BY trade_date, fusion_score DESC
        """
    )
    rows = []
    async with get_session(read_only=True) as session:
        result = await session.execute(
            query, {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "from": date.fromisoformat(from_date),
                "to": date.fromisoformat(to_date),
            }
        )
        rows = result.mappings().all()

    if not rows:
        return {"status": "success", "days": [], "total": 0}

    panel = pd.DataFrame(
        [{"trade_date": str(r["trade_date"]), "symbol": str(r["symbol"]).upper(),
          "score": float(r["fusion_score"])} for r in rows if r["fusion_score"] is not None]
    )
    panel["symbol"] = panel["symbol"].map(StockCodeUtil.to_suffix)

    days: list[dict[str, Any]] = []
    for trade_date, group in panel.groupby("trade_date", sort=True):
        day_df = group.drop_duplicates(subset="symbol", keep="last")
        ind_top1, _, avg_top1, strong_count = _compute_industry_signals(day_df, industry_map)
        state = _market_state(avg_top1, strong_count)
        should_enter = avg_top1 >= cfg.entry_threshold and strong_count >= cfg.strong_industry_min
        picks = _select_stocks_daily(day_df, industry_map, cfg, None) if should_enter else []
        days.append({
            "trade_date": trade_date,
            "state": state,
            "avg_top1": round(avg_top1, 4),
            "strong_count": strong_count,
            "should_enter": should_enter,
            "candidates": picks,
        })

    return {"status": "success", "days": days, "total": len(days)}


def _top_stock_by_industry(
    day_scores: pd.DataFrame,
    industry_map: dict[str, str],
) -> dict[str, str]:
    """单次返回各行业分数最高股票的 symbol（避免逐行业反复排序）。"""
    joined = day_scores.copy()
    joined["industry"] = joined["symbol"].map(industry_map)
    joined = joined[joined["industry"].notna() & (joined["industry"] != "")]
    if joined.empty:
        return {}
    idx = joined.groupby("industry")["score"].idxmax()
    return {joined.loc[i, "industry"]: str(joined.loc[i, "symbol"]) for i in idx.values}


def _is_main_board_code(symbol: str) -> bool:
    s = symbol.split(".")[0] if "." in symbol else symbol
    return s.startswith(("600", "601", "603", "605", "000", "001", "002"))


def _is_star_market_code(symbol: str) -> bool:
    s = symbol.split(".")[0] if "." in symbol else symbol
    return s.startswith(("688", "300", "301"))


# ---------------------------------------------------------------------------
# 负分多空参考（QuantMind负分精确落地规则）
# 分数×市值×板块 网格矩阵，依据 2024-2026 跨年 328万条 统计
# ---------------------------------------------------------------------------

def _cap_bucket(total_mv: float | None) -> str:
    """按总市值(元)分桶：微盘<30亿 小盘30-100亿 中盘100-300亿 大盘300-1000亿 超大盘>1000亿。"""
    if total_mv is None:
        return "未知"
    if total_mv < 3e9:
        return "微盘"
    if total_mv < 1e10:
        return "小盘"
    if total_mv < 3e10:
        return "中盘"
    if total_mv < 1e11:
        return "大盘"
    return "超大盘"


def _board_type(symbol: str) -> str:
    """板块类型：科创板 / 创业板 / 主板 / 北交所。"""
    s = symbol.split(".")[0] if "." in symbol else symbol
    if s.startswith("688"):
        return "科创板"
    if s.startswith(("300", "301")):
        return "创业板"
    if s.startswith(("600", "601", "603", "605", "000", "001", "002")):
        return "主板"
    return "其他"


def _short_signal(score: float, cap: str) -> tuple[bool, str]:
    """按研究矩阵判断是否做空/回避。返回 (是否做空, 理由)。"""
    if score >= -0.06:
        return False, "轻负分(>-0.06)无信息"
    # 大盘/超大盘：负分是错杀，不做空
    if cap in ("大盘", "超大盘"):
        if score <= -0.22:
            return True, "超大盘跌破警戒线-0.22，大盘股也会崩"
        return False, "大盘/超大盘负分是错杀"
    # 科创板负分抗跌，做空价值最低
    return True, "负分可做空"


def _missed_opportunity(score: float, cap: str, board: str) -> bool:
    """判断是否为「负分错杀」（值得关注反弹）。"""
    if score >= -0.06:
        return False
    # 超大盘 -0.13~-0.14 上涨概率 56.8%
    if cap == "超大盘" and -0.14 <= score <= -0.13:
        return True
    # 大盘 -0.11 上涨概率 51.3%
    if cap == "大盘" and -0.115 <= score <= -0.105:
        return True
    # 科创板 -0.06~-0.15 均收全为正
    if board == "科创板" and score >= -0.15:
        return True
    # 银行等行业错杀
    return False


# 市值快照缓存：stock_daily_latest 每次写入全表最新交易日，一天内市值基本不变，
# 无需每个请求都跑 5s 的 DISTINCT ON 全表扫描。
_cap_cache: dict[str, float | None] = {}
_cap_cache_ts: float = 0.0
_CAP_CACHE_TTL = 600.0  # 10 分钟


async def _load_cap_snapshot() -> dict[str, float | None]:
    """加载全表最新交易日的市值快照（prefix symbol → 市值元），带缓存。"""
    global _cap_cache, _cap_cache_ts
    if _cap_cache and (_now() - _cap_cache_ts) < _CAP_CACHE_TTL:
        return _cap_cache

    caps: dict[str, float | None] = {}
    async with get_session(read_only=True) as session:
        r = await session.execute(text(
            "SELECT symbol, total_mv FROM stock_daily_latest "
            "WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_latest) "
            "AND total_mv IS NOT NULL"
        ))
        for row in r.mappings():
            caps[str(row["symbol"]).strip().upper()] = float(row["total_mv"])
    _cap_cache = caps
    _cap_cache_ts = _now()
    return caps


async def _load_cap_and_name(
    symbols: list[str],
) -> tuple[dict[str, float | None], dict[str, str]]:
    """批量加载市值(元)和股票名称。

    市值: stock_daily_latest.total_mv（prefix 格式 SH600172，最新交易日快照，带缓存）
    名称: stocks.name（suffix 格式 600172.SH）
    返回 ({suffix_symbol: total_mv}, {suffix_symbol: name})
    """
    caps: dict[str, float | None] = {}
    names: dict[str, str] = {}
    if not symbols:
        return caps, names

    prefix_map = {StockCodeUtil.to_prefix(s): s for s in symbols}
    snapshot = await _load_cap_snapshot()
    for prefix, suffix in prefix_map.items():
        if prefix in snapshot:
            caps[suffix] = snapshot[prefix]

    # 名称（suffix 格式）
    suffix_list = [s for s in symbols if "." in s or len(s) >= 6]
    async with get_session(read_only=True) as session:
        for chunk in _chunks(suffix_list, 500):
            q2 = text(
                "SELECT symbol, name FROM stocks WHERE symbol = ANY(:codes) "
                "AND name IS NOT NULL AND name != ''"
            )
            res2 = await session.execute(q2, {"codes": chunk})
            for row in res2.mappings():
                sym = str(row["symbol"] or "").strip().upper()
                names[sym] = str(row["name"] or "")
    return caps, names


@router.get("/negative")
async def negative_selection(
    request: Request,
    date: str | None = Query(None, description="信号交易日，缺省取最新"),
):
    """负分多空参考：做空候选 + 错杀参考 + 分数×市值分布矩阵。"""
    user_id, tenant_id = get_authenticated_identity(request)

    trade_date, signals = await _load_signal_day(tenant_id, user_id, date)
    if not signals:
        return {
            "status": "success",
            "meta": {"trade_date": trade_date or None, "total_signals": 0},
            "short_candidates": [], "missed_reference": [],
            "matrix": [], "warnings": ["无推理信号"],
        }

    # 归一化 symbol → suffix
    day_scores = pd.DataFrame(
        [{"symbol": s["symbol"], "score": s["fusion_score"]} for s in signals]
    )
    day_scores["symbol"] = day_scores["symbol"].map(StockCodeUtil.to_suffix)
    day_scores = day_scores.drop_duplicates(subset="symbol", keep="last")

    # 只保留负分（研究关注 < -0.06）
    neg_df = day_scores[day_scores["score"] < -0.06].copy()
    neg_df = neg_df.sort_values("score")

    # 市值 + 名称
    all_symbols = neg_df["symbol"].tolist()
    caps, names = await _load_cap_and_name(all_symbols)
    neg_df["cap"] = neg_df["symbol"].map(lambda s: _cap_bucket(caps.get(s)))
    neg_df["board"] = neg_df["symbol"].map(_board_type)
    neg_df["name"] = neg_df["symbol"].map(names)

    # 做空候选 + 错杀参考
    short_candidates: list[dict[str, Any]] = []
    missed_reference: list[dict[str, Any]] = []
    for row in neg_df.itertuples(index=False):
        item = {
            "symbol": row.symbol,
            "name": row.name or "",
            "score": round(float(row.score), 4),
            "cap": row.cap,
            "board": row.board,
        }
        do_short, reason = _short_signal(float(row.score), row.cap)
        if do_short:
            # 做空聚焦小市值/微盘，分数越负优先级越高
            item["short_reason"] = reason
            short_candidates.append(item)
        if _missed_opportunity(float(row.score), row.cap, row.board):
            item["missed_reason"] = "负分错杀，可能反弹"
            missed_reference.append(item)

    # 做空候选按 (市值从小到大, 分数从负到正) 排序
    cap_order = {"微盘": 0, "小盘": 1, "中盘": 2, "大盘": 3, "超大盘": 4, "未知": 5}
    short_candidates.sort(key=lambda x: (cap_order.get(x["cap"], 5), x["score"]))

    # 分数×市值矩阵（统计每格股票数 + 做空建议）
    matrix: list[dict[str, Any]] = []
    score_bands = [
        ("≤-0.25", lambda s: s <= -0.25),
        ("-0.25~-0.20", lambda s: -0.25 < s <= -0.20),
        ("-0.20~-0.15", lambda s: -0.20 < s <= -0.15),
        ("-0.15~-0.10", lambda s: -0.15 < s <= -0.10),
        ("-0.10~-0.06", lambda s: -0.10 < s <= -0.06),
    ]
    cap_buckets = ["微盘", "小盘", "中盘", "大盘", "超大盘"]
    for band_label, band_fn in score_bands:
        row_entries: list[dict[str, Any]] = []
        for cap_label in cap_buckets:
            count = int(((neg_df["score"].map(band_fn)) & (neg_df["cap"] == cap_label)).sum())
            row_entries.append({"cap": cap_label, "count": count})
        matrix.append({"score_band": band_label, "caps": row_entries})

    return {
        "status": "success",
        "meta": {
            "trade_date": trade_date,
            "total_signals": len(signals),
            "negative_count": len(neg_df),
        },
        "short_candidates": short_candidates[:30],
        "missed_reference": missed_reference[:20],
        "matrix": matrix,
        "warnings": [],
    }


async def _load_industry_negative_avg(
    signals: list[dict[str, Any]],
    day_scores: pd.DataFrame,
    industry_map: dict[str, str],
) -> list[dict[str, Any]]:
    """负分行业 avg：按申万行业统计负分股票的数量、均值、最深分。"""
    if day_scores.empty:
        return []

    # symbol (suffix) → 行业
    sym_industry: dict[str, str] = {}
    for row in day_scores.itertuples(index=False):
        sym = row.symbol  # 已是 suffix 格式（600519.SH）
        sym_industry[sym] = industry_map.get(sym) or ""

    neg = day_scores[day_scores["score"] < 0].copy()
    neg["industry"] = neg["symbol"].map(sym_industry)
    neg = neg[neg["industry"].notna() & (neg["industry"] != "")]

    if neg.empty:
        return []

    agg = neg.groupby("industry").agg(
        neg_count=("score", "count"),
        neg_avg=("score", "mean"),
        neg_min=("score", "min"),
    ).reset_index()
    agg = agg.sort_values("neg_avg").reset_index(drop=True)
    return [
        {
            "industry": r.industry,
            "neg_count": int(r.neg_count),
            "neg_avg": round(float(r.neg_avg), 4),
            "neg_min": round(float(r.neg_min), 4),
        }
        for r in agg.itertuples(index=False)
    ]


async def _load_board_negative_avg(
    day_scores: pd.DataFrame,
) -> list[dict[str, Any]]:
    """板块负分 avg：主板/创业板/科创板/北交所/其他。"""
    if day_scores.empty:
        return []
    neg = day_scores[day_scores["score"] < 0].copy()
    neg["board"] = neg["symbol"].map(_board_type)
    if neg.empty:
        return []
    agg = neg.groupby("board").agg(
        neg_count=("score", "count"),
        neg_avg=("score", "mean"),
    ).reset_index()
    return [
        {
            "board": r.board,
            "neg_count": int(r.neg_count),
            "neg_avg": round(float(r.neg_avg), 4),
        }
        for r in agg.itertuples(index=False)
    ]


@router.post("/score-calibration")
async def submit_score_calibration(
    request: Request,
    days: int = Query(180, ge=30, le=478, description="回测历史交易日数"),
    horizons: str = Query("1,3,5,10", description="未来 N 日收益列表，逗号分隔，如 1,3,5,10"),
    top_n: int = Query(50, ge=10, le=200, description="排名前 N 内重点标注"),
):
    """提交模型分数校准任务，立即返回 task_id，后台异步计算。"""
    user_id, tenant_id = get_authenticated_identity(request)
    task_id = f"calib_{int(_now() * 1000)}_{__import__('uuid').uuid4().hex[:8]}"
    _calib_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "message": "任务已提交，等待调度",
        "user_id": user_id,
        "params": {"days": days, "horizons": horizons, "top_n": top_n},
        "result": None,
        "error": None,
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    asyncio.create_task(
        _run_score_calibration(task_id, user_id, tenant_id, days, horizons, top_n),
        name=f"score-calib-{task_id}",
    )
    return {
        "status": "submitted",
        "task_id": task_id,
        "data": {"task_id": task_id, "status": "pending", "progress": 0},
    }


@router.get("/score-calibration/{task_id}")
async def get_score_calibration_task(task_id: str, request: Request):
    """查询校准任务进度。"""
    user_id, tenant_id = get_authenticated_identity(request)
    task = _calib_tasks.get(task_id)
    if not task:
        return {"status": "not_found", "detail": "任务不存在"}
    if task.get("user_id") != user_id:
        return {"status": "error", "detail": "无权访问该任务"}
    return {
        "status": task.get("status"),
        "task_id": task_id,
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "result": task.get("result"),
        "error": task.get("error"),
        "meta": {
            "model_scope": "全部历史信号（当前模型版本）",
            "backtest_days": task.get("params", {}).get("days"),
            "horizons": _parse_horizons(task.get("params", {}).get("horizons", "1,3,5,10")),
            "top_n": task.get("params", {}).get("top_n"),
        },
    }


async def _run_score_calibration(
    task_id: str, user_id: str, tenant_id: str, days: int, horizons: str, top_n: int
) -> None:
    """后台执行分数校准，分阶段更新进度。"""
    try:
        _calib_tasks[task_id]["status"] = "running"
        _calib_tasks[task_id]["progress"] = 5
        _calib_tasks[task_id]["message"] = "读取历史信号..."

        horizon_list = _parse_horizons(horizons)

        # 1. 读取历史信号（限制条数避免全表扫描）
        query = text(
            """
            SELECT trade_date, symbol, fusion_score, score_rank
            FROM engine_signal_scores
            WHERE tenant_id = :tenant_id AND user_id = :user_id
              AND fusion_score IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 2000000
            """
        )
        rows = []
        async with get_session(read_only=True) as session:
            result = await session.execute(query, {"tenant_id": tenant_id, "user_id": user_id})
            rows = result.mappings().all()
        if not rows:
            _calib_tasks[task_id]["status"] = "failed"
            _calib_tasks[task_id]["error"] = "无历史信号数据"
            return

        _calib_tasks[task_id]["progress"] = 15
        _calib_tasks[task_id]["message"] = "分组统计信号..."

        # 按日期分组取最近 days 个交易日
        date_scores: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            d = str(r["trade_date"])
            date_scores.setdefault(d, []).append(
                {"symbol": str(r["symbol"]).upper(), "score": float(r["fusion_score"]),
                 "rank": int(r["score_rank"]) if r["score_rank"] else None}
            )
        all_dates = sorted(date_scores.keys())[-days:]
        if not all_dates:
            _calib_tasks[task_id]["status"] = "failed"
            _calib_tasks[task_id]["error"] = "无可用交易日"
            return

        # 2. 加载价格面板（线程池避免阻塞事件循环）
        _calib_tasks[task_id]["progress"] = 30
        _calib_tasks[task_id]["message"] = "加载价格面板..."
        from pathlib import Path as _Path
        from backend.services.engine.inference.inference_backtest_service import _load_price_panel

        data_dir = _Path(__import__("os").getenv("QLIB_DIR", "/app/db/qlib_data/cn_data"))
        panel = await asyncio.to_thread(_load_price_panel, data_dir, all_dates)
        if panel.empty:
            _calib_tasks[task_id]["status"] = "failed"
            _calib_tasks[task_id]["error"] = "无法加载价格面板"
            return
        close_pivot = panel.pivot_table(index="symbol", columns="trade_date", values="close", aggfunc="last")
        del panel

        # 3. 市值快照
        _calib_tasks[task_id]["progress"] = 45
        _calib_tasks[task_id]["message"] = "加载市值快照..."
        caps_snapshot = await _load_cap_snapshot()

        # 4. 逐日计算多周期收益
        _calib_tasks[task_id]["progress"] = 55
        _calib_tasks[task_id]["message"] = "回测多周期收益..."
        records: list[dict[str, Any]] = []
        max_h = max(horizon_list)
        total_days = len(all_dates)
        for idx, d in enumerate(all_dates):
            if idx + max_h >= total_days:
                break
            day_items = date_scores[d]
            if not day_items:
                continue
            sorted_items = sorted(day_items, key=lambda x: -x["score"])
            total = len(sorted_items)
            for rank_i, it in enumerate(sorted_items):
                suffix = StockCodeUtil.to_suffix(it["symbol"])
                prefix = StockCodeUtil.to_prefix(it["symbol"])
                try:
                    c0 = close_pivot.at[suffix, d]
                except KeyError:
                    continue
                if not c0 or c0 <= 0:
                    continue
                rets: dict[int, float] = {}
                for h in horizon_list:
                    f_idx = idx + h
                    if f_idx >= total_days:
                        continue
                    f_date = all_dates[f_idx]
                    try:
                        c1 = close_pivot.at[suffix, f_date]
                    except KeyError:
                        continue
                    if not c1:
                        continue
                    rets[h] = (float(c1) / float(c0) - 1.0) * 100.0
                if not rets:
                    continue
                cap = _cap_bucket(caps_snapshot.get(prefix))
                board = _board_type(suffix)
                records.append({
                    "score": it["score"], "rets": rets, "cap": cap, "board": board,
                    "rank_pct": (rank_i + 1) / total, "rank": rank_i + 1, "total": total,
                })
            if idx % 20 == 0:
                _calib_tasks[task_id]["progress"] = 55 + int(40 * (idx + 1) / total_days)
                _calib_tasks[task_id]["message"] = f"回测中... {idx+1}/{total_days} 天"

        if not records:
            _calib_tasks[task_id]["status"] = "failed"
            _calib_tasks[task_id]["error"] = "回测无有效样本"
            return

        _calib_tasks[task_id]["progress"] = 95
        _calib_tasks[task_id]["message"] = "汇总统计..."

        result = await _aggregate_calibration(records, all_dates, date_scores, horizon_list, top_n)
        _calib_tasks[task_id]["status"] = "completed"
        _calib_tasks[task_id]["progress"] = 100
        _calib_tasks[task_id]["message"] = "完成"
        _calib_tasks[task_id]["result"] = result
    except Exception as exc:
        logger.error("score calibration task %s failed: %s", task_id, exc, exc_info=True)
        _calib_tasks[task_id]["status"] = "failed"
        _calib_tasks[task_id]["error"] = str(exc)


def _parse_horizons(horizons: str) -> list[int]:
    out = []
    for h in str(horizons).split(","):
        h = h.strip()
        if h.isdigit() and 1 <= int(h) <= 20:
            out.append(int(h))
    return out or [1, 3, 5, 10]


async def _aggregate_calibration(
    records: list[dict[str, Any]],
    all_dates: list[str],
    date_scores: dict[str, list[dict[str, Any]]],
    horizon_list: list[int],
    top_n: int,
) -> dict[str, Any]:
    """从 records 聚合分数档矩阵与汇总。"""
    def _band(score: float) -> str:
        if score <= -0.25: return "≤-0.25"
        if score <= -0.20: return "-0.25~-0.20"
        if score <= -0.15: return "-0.20~-0.15"
        if score <= -0.10: return "-0.15~-0.10"
        if score <= -0.06: return "-0.10~-0.06"
        if score < 0: return "-0.06~0"
        if score < 0.05: return "0~0.05"
        if score < 0.08: return "0.05~0.08"
        if score < 0.10: return "0.08~0.10"
        if score < 0.12: return "0.10~0.12"
        if score < 0.15: return "0.12~0.15"
        if score < 0.20: return "0.15~0.20"
        return "≥0.20"

    import collections
    band_labels = ["≤-0.25","-0.25~-0.20","-0.20~-0.15","-0.15~-0.10","-0.10~-0.06","-0.06~0",
                   "0~0.05","0.05~0.08","0.08~0.10","0.10~0.12","0.12~0.15","0.15~0.20","≥0.20"]

    # 分数档×市值档×horizon
    band_cap_h: dict[tuple[str, str, int], list[float]] = collections.defaultdict(list)
    band_h: dict[str, dict[int, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    band_ranks: dict[str, list[int]] = collections.defaultdict(list)
    band_rank_pcts: dict[str, list[float]] = collections.defaultdict(list)
    for r in records:
        b = _band(r["score"])
        for h, ret in r["rets"].items():
            band_cap_h[(b, r["cap"], h)].append(ret)
            band_h[b][h].append(ret)
        band_ranks[b].append(r["rank"])
        band_rank_pcts[b].append(r["rank_pct"])

    main_h = horizon_list[0] if horizon_list else 5
    cap_order = ["微盘", "小盘", "中盘", "大盘", "超大盘"]
    matrix = []
    for band_label in band_labels:
        caps = []
        for cap in cap_order:
            rets = band_cap_h.get((band_label, cap, main_h), [])
            if rets:
                caps.append({
                    "cap": cap, "n": len(rets),
                    "down_prob": round(sum(1 for x in rets if x < 0) / len(rets) * 100.0, 1),
                    "avg_ret": round(sum(rets)/len(rets), 3),
                })
            else:
                caps.append({"cap": cap, "n": 0, "down_prob": None, "avg_ret": None})
        matrix.append({"score_band": band_label, "caps": caps})

    score_summary = []
    for band_label in band_labels:
        h_dict = band_h.get(band_label)
        if not h_dict:
            continue
        ranks = band_ranks[band_label]
        rank_pcts = band_rank_pcts[band_label]
        horizons_stats = []
        for h in sorted(h_dict.keys()):
            rets = h_dict[h]
            if not rets:
                continue
            sorted_rets = sorted(rets)
            horizons_stats.append({
                "horizon": h, "n": len(rets),
                "win_rate": round(sum(1 for x in rets if x > 0) / len(rets) * 100.0, 1),
                "down_prob": round(sum(1 for x in rets if x < 0) / len(rets) * 100.0, 1),
                "avg_ret": round(sum(rets) / len(rets), 3),
                "median_ret": round(sorted_rets[len(sorted_rets)//2], 3),
            })
        main_rets = band_h[band_label].get(main_h, [])
        score_summary.append({
            "score_band": band_label,
            "n": len(ranks),
            "top50_count": sum(1 for rk in ranks if rk <= 50),
            "avg_rank": round(sum(ranks) / len(ranks), 1),
            "avg_rank_pct": round(sum(rank_pcts) / len(rank_pcts), 3),
            "main_horizon_avg_ret": round(sum(main_rets) / len(main_rets), 3) if main_rets else None,
            "horizons": horizons_stats,
        })

    # 负分行业/板块 avg（最新日）
    latest_date = all_dates[-1]
    latest_items = date_scores[latest_date]
    latest_df = pd.DataFrame(
        [{"symbol": StockCodeUtil.to_suffix(x["symbol"]), "score": x["score"]}
         for x in latest_items]
    )
    industry_map = load_shenwan_industry_map()
    neg_industry_avg = await _load_industry_negative_avg(latest_items, latest_df, industry_map)
    neg_board_avg = await _load_board_negative_avg(latest_df)

    # 推荐分数区间
    recommended = None
    for s in score_summary:
        avg = s.get("main_horizon_avg_ret")
        if s["n"] >= 50 and avg is not None and avg > 0:
            if recommended is None or avg > recommended.get("main_horizon_avg_ret", -999):
                recommended = s

    return {
        "matrix": matrix,
        "score_summary": score_summary,
        "neg_industry_avg": neg_industry_avg[:10],
        "neg_board_avg": neg_board_avg,
        "recommended_band": recommended,
        "total_samples": len(records),
        "latest_trade_date": latest_date,
    }


# 校准任务内存存储
_calib_tasks: dict[str, dict[str, Any]] = {}
