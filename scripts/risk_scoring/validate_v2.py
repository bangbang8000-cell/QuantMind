"""风险评分卡 v2 — 正交性 + 单调性验证脚本。

一次性脚本，验证：
1. 6 个维度两两相关性（Pearson）< 0.5（避免重复定义同一件事）
2. 各维度按分数分桶后，未来 5/10/20 日实际波动率/回撤是否单调

用法：
    docker exec quantmind python /app/scripts/risk_scoring/validate_v2.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

# 让脚本能被 docker exec 直接调
sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.services.api.risk_scoring.scorecard import (
    DEFAULT_WEIGHTS,
    _compute_from_row,
)
from backend.shared.database_manager_v2 import get_session


# ── 配置 ───────────────────────────────────────────────────────────────────
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 6, 22)
SAMPLE_DATES = 10
SAMPLE_STOCKS_PER_DATE = 800

MONO_DATE = date(2026, 4, 30)
MONO_FUTURE_DAYS = 20


# ── 一次性拉取某日全量评分数据 ─────────────────────────────────────────────
async def _fetch_day_features(trade_date: date, limit: int) -> list[dict[str, Any]]:
    """拉取某日全市场（截断 limit）的所有评分字段。"""
    sql = """
    WITH base_day AS (SELECT cast(:td as date) AS d),
    amt_20d AS (
        SELECT s.symbol, AVG(s.amount) AS amount_20d_avg
        FROM stock_daily_latest s, base_day b
        WHERE s.trade_date BETWEEN b.d - INTERVAL '30 day' AND b.d
        GROUP BY s.symbol
    ),
    amt_5d AS (
        SELECT s.symbol, AVG(s.amount) AS amount_5d_avg
        FROM stock_daily_latest s, base_day b
        WHERE s.trade_date BETWEEN b.d - INTERVAL '8 day' AND b.d - INTERVAL '1 day'
        GROUP BY s.symbol
    )
    SELECT s.symbol, s.trade_date, s.stock_name,
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
    FROM stock_daily_latest s
    LEFT JOIN amt_20d a20 USING(symbol)
    LEFT JOIN amt_5d  a5  USING(symbol)
    WHERE s.trade_date = :td
      AND s.symbol ~ '^[0-9]{6}\\.(SH|SZ|BJ)$'           -- 排除指数
      AND s.symbol !~ '^9[0-9]{5}'                       -- 排除部分异常代码
    LIMIT :lim
    """
    async with get_session(read_only=True) as session:
        res = await session.execute(text(sql), {"td": trade_date, "lim": limit})
        return [dict(r) for r in res.mappings().all()]


# ── 正交性：抽 N 个交易日算 6 维度，再算两两相关系数 ────────────────────────
def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(ys) < 3 or len(xs) != len(ys):
        return 0.0
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    sx = (sum((xs[i]-mx)**2 for i in range(n))) ** 0.5
    sy = (sum((ys[i]-my)**2 for i in range(n))) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


async def _list_trade_days() -> list[date]:
    """拿到测试区间内的所有交易日，等距抽 SAMPLE_DATES 个。"""
    sql = """
        SELECT DISTINCT trade_date
        FROM stock_daily_latest
        WHERE trade_date BETWEEN :s AND :e
        ORDER BY trade_date
    """
    async with get_session(read_only=True) as session:
        res = await session.execute(text(sql), {"s": START_DATE, "e": END_DATE})
        days = [r[0] for r in res.all()]
    if len(days) <= SAMPLE_DATES:
        return days
    step = len(days) // SAMPLE_DATES
    return days[::step][:SAMPLE_DATES]


async def test_orthogonality() -> dict[str, dict[str, float]]:
    """对采样日 × 采样票，对每只票算 6 个维度的分数，最后两两相关。"""
    sample_days = await _list_trade_days()
    print(f"\n[ORTHO] sampling {len(sample_days)} trade days from {START_DATE}~{END_DATE}")

    # 收集每个维度的分数序列（跨日聚合）
    dim_keys = list(DEFAULT_WEIGHTS.keys())
    series: dict[str, list[float]] = {k: [] for k in dim_keys}

    for d in sample_days:
        rows = await _fetch_day_features(d, SAMPLE_STOCKS_PER_DATE)
        print(f"  {d}: fetched {len(rows)} rows")
        for row in rows:
            # 算分数（带 veto 的不计入正交性 — 否则被 veto 拉成 100 会污染）
            from backend.services.api.risk_scoring.scorecard import _veto
            veto, _ = _veto(row)
            if veto:
                continue
            r = _compute_from_row(row)
            for k in dim_keys:
                series[k].append(r.dimensions[k].score)

    n = len(series[dim_keys[0]])
    print(f"[ORTHO] total non-veto samples: {n}")

    # 两两 Pearson
    matrix: dict[str, dict[str, float]] = {}
    for i, a in enumerate(dim_keys):
        matrix[a] = {}
        for j, b in enumerate(dim_keys):
            if i <= j:
                matrix[a][b] = round(_pearson(series[a], series[b]), 3)
            else:
                matrix[a][b] = matrix[b][a]

    # 打印
    print("\n[ORTHO] Pearson correlation matrix:")
    header = "        " + "  ".join(f"{k[:6]:>6s}" for k in dim_keys)
    print(header)
    for a in dim_keys:
        cells = "  ".join(f"{matrix[a][b]:6.3f}" for b in dim_keys)
        flag = ""
        for b in dim_keys:
            if a != b and abs(matrix[a][b]) >= 0.5:
                flag = " ⚠"
                break
        print(f"  {a[:7]:7s}  {cells}{flag}")

    # 标记
    fails = []
    for i, a in enumerate(dim_keys):
        for b in dim_keys[i+1:]:
            r = matrix[a][b]
            if abs(r) >= 0.5:
                fails.append((a, b, r))
    if fails:
        print("\n[ORTHO] ❌ failed pairs (|r| >= 0.5):")
        for a, b, r in fails:
            print(f"   {a} <-> {b}: r = {r}")
    else:
        print("\n[ORTHO] ✅ all pairs |r| < 0.5")

    return matrix


# ── 单调性：评分 → 未来回撤是否单调 ────────────────────────────────────────
async def _fetch_future_returns(symbol: str, base_date: date, days: int) -> dict[str, float]:
    """拉取 base_date 之后 days 个交易日内的最低收盘价，计算最大回撤。"""
    sql = """
        SELECT trade_date, close FROM stock_daily_latest
        WHERE symbol = :s
          AND trade_date > :td
          AND trade_date <= :td_end
        ORDER BY trade_date
    """
    td_end = base_date + timedelta(days=days)
    async with get_session(read_only=True) as session:
        res = await session.execute(text(sql), {"s": symbol, "td": base_date, "td_end": td_end})
        rows = res.all()
    if len(rows) < 3:
        return {"max_drawdown": 0.0, "future_vol": 0.0, "valid": False}

    closes = [float(r[1]) for r in rows if r[1] is not None]
    if len(closes) < 3:
        return {"max_drawdown": 0.0, "future_vol": 0.0, "valid": False}

    # 从评分日的下一日 close 起算最大回撤
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c - peak) / peak    # 负数
        if dd < max_dd:
            max_dd = dd

    # 未来期间日收益率的样本标准差
    rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    fv = stdev(rets) if len(rets) >= 2 else 0.0

    return {"max_drawdown": max_dd, "future_vol": fv, "valid": True}


async def test_monotonicity() -> None:
    """评分日 MONO_DATE 全市场打分 → 按各维度分桶 → 评估未来 20 日表现。"""
    print(f"\n[MONO] base date {MONO_DATE}, future {MONO_FUTURE_DAYS} days")
    rows = await _fetch_day_features(MONO_DATE, 5000)
    print(f"[MONO] fetched {len(rows)} stocks on {MONO_DATE}")

    # 算分数 + 拉未来回撤（注意：批量拉，慢，限量到前 1500 票）
    samples = []
    for i, row in enumerate(rows[:1500]):
        from backend.services.api.risk_scoring.scorecard import _veto
        veto, _ = _veto(row)
        if veto:
            continue
        r = _compute_from_row(row)
        fut = await _fetch_future_returns(row["symbol"], MONO_DATE, MONO_FUTURE_DAYS)
        if not fut["valid"]:
            continue
        samples.append({
            "symbol": row["symbol"],
            "total": r.risk_score,
            **{k: r.dimensions[k].score for k in DEFAULT_WEIGHTS},
            "future_dd": fut["max_drawdown"],
            "future_vol": fut["future_vol"],
        })

    print(f"[MONO] {len(samples)} valid samples (non-veto + future data)")

    # 按总分 5 分位 + 每个维度 5 分位
    def bucket_and_report(field: str):
        sorted_s = sorted(samples, key=lambda x: x[field])
        n = len(sorted_s)
        if n < 50:
            return
        buckets = []
        for i in range(5):
            chunk = sorted_s[i*n//5 : (i+1)*n//5]
            if not chunk:
                continue
            avg_score = mean(x[field] for x in chunk)
            avg_dd = mean(x["future_dd"] for x in chunk)
            avg_vol = mean(x["future_vol"] for x in chunk)
            buckets.append((i+1, len(chunk), avg_score, avg_dd, avg_vol))
        print(f"\n[MONO] field={field}  (n={n}, 5 buckets ascending by score)")
        print(f"  {'bucket':>6s}  {'n':>5s}  {'avg_score':>10s}  {'avg_future_dd':>14s}  {'avg_future_vol':>15s}")
        for b, count, sc, dd, vol in buckets:
            print(f"  {b:>6d}  {count:>5d}  {sc:>10.2f}  {dd*100:>13.2f}%  {vol*100:>14.2f}%")
        # 单调性检查：只看 score 真正不同的桶（去重 score）
        # 因为很多维度有大量 score=0 的票，会让低分桶 score 都是 0
        distinct_buckets = []
        seen_score = -1
        for b, count, sc, dd, vol in buckets:
            if sc > seen_score + 0.01:   # 至少差 0.01 算"不同 score"
                distinct_buckets.append((sc, dd, vol))
                seen_score = sc
        if len(distinct_buckets) >= 2:
            dds = [x[1] for x in distinct_buckets]
            vols = [x[2] for x in distinct_buckets]
            dd_mono = all(dds[i] >= dds[i+1] for i in range(len(dds)-1))
            vol_mono = all(vols[i] <= vols[i+1] for i in range(len(vols)-1))
            mark_dd = '✅' if dd_mono else '❌'
            mark_vol = '✅' if vol_mono else '❌'
            print(f"  → (distinct {len(distinct_buckets)} buckets) DD monotonic: {mark_dd} | VOL monotonic: {mark_vol}")
        else:
            print(f"  → only {len(distinct_buckets)} distinct bucket(s) — too few to test monotonicity")

    bucket_and_report("total")
    for k in DEFAULT_WEIGHTS:
        bucket_and_report(k)


# ── 主入口 ────────────────────────────────────────────────────────────────
async def main():
    print("="*70)
    print(" Risk Scorecard v2 — Orthogonality + Monotonicity Validation")
    print("="*70)
    matrix = await test_orthogonality()
    await test_monotonicity()
    print("\n" + "="*70)
    print(" DONE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
