"""批量多日推理结果的截面聚合（纯函数、零 IO）。

输入是调用方备好的 panel DataFrame，输出是纯 dict —— 本模块不碰 DB/Redis/文件。

日期口径：`trade_date` 与 `dates` 均为**数据交易日 T**（生成信号所用特征的日期），
由调用方负责归一化。注意 `engine_signal_scores.trade_date` 实际存的是信号生效日
T+1，取数层应改用 `qm_model_inference_runs.data_trade_date` 才能与用户输入的锚定日
及 `load_forward_labels` 的 signal_date 对齐。**本模块不做任何 T/T+1 转换**；
若 panel 里出现 `dates` 之外的日期，会剔除并在 `meta.warnings` 中报出。

核心口径约束：跨日主排序键一律用每日截面百分位 `pct`（0~1）或日内排名 `rk`，
不用原始 `fusion_score`。模型输出随市场 regime 漂移（普涨日整体分数上移），
直接平均原始分数会把市场 beta 当成选股 alpha。`movers.raw_score_change` 是
唯一暴露原始分数变化的榜单，仅作对照，带 warning 字段。

缺席语义：某股票某日因停牌/ST/涨跌停过滤不在 panel 里 —— 缺席是 NaN，不是 0。
均值/趋势只在实际出现的日子上计算，缺席程度由 `coverage` 单独反映。

数据完整性：同日多 run 共存、同日重跑清理旧信号都会让聚合结论看似正常实则失真，
故 (trade_date, symbol) 重复与行数异常稀疏的日期一律记入 `meta.warnings`。
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import numpy as np
import pandas as pd

from backend.shared.inference_stats import compute_score_distribution

_REQUIRED_COLUMNS = ("trade_date", "symbol", "fusion_score")

# 某日行数低于全窗口中位数的此比例即视为「信号被部分清理」
_SPARSE_DAY_RATIO = 0.2

# 严格单调在小 N 下退化为噪声（N=3 纯随机即约 1/6 单调），超此占比即告警
_MONOTONIC_NOISE_MAX_N = 4
_MONOTONIC_NOISE_RATIO = 0.10

# 趋势"显著"判定阈值：小样本（N=5）Spearman p 值本就不可信，
# 故显著性 = |rho| 阈值 + Mann-Kendall S 归一化阈值 + 最小观测数的组合，
# 不依赖 p 值。p 值仅在 appear_days >= 4 时作为附加信息输出。
_TREND_RHO_MIN = 0.7
_TREND_MK_MIN = 0.6
_TREND_MIN_POINTS = 3


# ---------------------------------------------------------------------------
# 统计基元（项目环境无 scipy，故自实现）
# ---------------------------------------------------------------------------


def _rankdata(values: np.ndarray) -> np.ndarray:
    """平均法处理并列的秩（等价 scipy.stats.rankdata 默认行为）。"""
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    sorted_v = values[order]
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2:
        return None
    xd = x - x.mean()
    yd = y - y.mean()
    denom = math.sqrt(float((xd * xd).sum()) * float((yd * yd).sum()))
    if denom <= 0.0:
        return None
    return float((xd * yd).sum() / denom)


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2:
        return None
    return _pearson(
        _rankdata(np.asarray(x, dtype=float)), _rankdata(np.asarray(y, dtype=float))
    )


def _betacf(a: float, b: float, x: float) -> float:
    """不完全 Beta 函数的连分数展开（Numerical Recipes betacf）。"""
    max_it, eps, fpmin = 300, 3.0e-16, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    if x < (a + 1.0) / (a + b + 2.0):
        front = math.exp(log_beta + a * math.log(x) + b * math.log1p(-x))
        return front * _betacf(a, b, x) / a
    front = math.exp(log_beta + b * math.log1p(-x) + a * math.log(x))
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_two_sided_p(t_stat: float, df: int) -> float:
    if df <= 0:
        return 1.0
    if not math.isfinite(t_stat):
        return 0.0
    return float(_betainc(df / 2.0, 0.5, df / (df + t_stat * t_stat)))


def _mann_kendall_s(values: np.ndarray) -> int:
    """MK 检验的 S 统计量：所有 i<j 对中上升对数减下降对数。"""
    s = 0
    n = len(values)
    for i in range(n - 1):
        diff = values[i + 1 :] - values[i]
        s += int(np.sum(diff > 0)) - int(np.sum(diff < 0))
    return s


def _zscores(values: list[float | None]) -> list[float]:
    present = [v for v in values if v is not None and math.isfinite(v)]
    if len(present) < 2:
        return [0.0 for _ in values]
    mean = float(np.mean(present))
    std = float(np.std(present))
    if std <= 0.0:
        return [0.0 for _ in values]
    return [
        0.0 if v is None or not math.isfinite(v) else (v - mean) / std for v in values
    ]


def _minmax_to_100(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo <= 0.0:
        return [50.0 for _ in values]
    return [round((v - lo) / (hi - lo) * 100.0, 2) for v in values]


def _longest_run(values: np.ndarray, ascending: bool) -> int:
    """最长连续单向观测段的天数（含起点）；相邻观测跨越缺席日时仍视为相邻。"""
    n = len(values)
    if n == 0:
        return 0
    best = run = 1
    for i in range(1, n):
        rising = values[i] > values[i - 1]
        if rising if ascending else values[i] < values[i - 1]:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _r3(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 6)


# ---------------------------------------------------------------------------
# 输入规范化与侧视图
# ---------------------------------------------------------------------------


def _normalize_panel(
    panel: pd.DataFrame, dates: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """规范化输入并返回数据完整性告警 —— 取数层口径错误必须吵出来，不能静默。"""
    missing_cols = [c for c in _REQUIRED_COLUMNS if c not in panel.columns]
    if missing_cols:
        raise ValueError(f"panel 缺少必需列: {missing_cols}")

    warnings: list[str] = []
    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    df["fusion_score"] = pd.to_numeric(df["fusion_score"], errors="coerce")

    # trade_date 应已由取数层归一化为数据交易日 T；窗口外日期说明口径错了
    date_set = set(dates)
    extra_dates = sorted(set(df["trade_date"]) - date_set)
    if extra_dates:
        warnings.append(
            f"panel 含 dates 之外的 trade_date（已剔除 {len(extra_dates)} 个）: "
            f"{extra_dates[:10]} —— 取数层可能未把 T+1 信号生效日归一化为数据日 T"
        )
        df = df[df["trade_date"].isin(date_set)]

    null_scores = int(df["fusion_score"].isna().sum())
    if null_scores:
        warnings.append(f"剔除 {null_scores} 行 fusion_score 为空的记录")
        df = df[df["fusion_score"].notna()]

    if "stock_name" not in df.columns:
        df["stock_name"] = ""
    df["stock_name"] = df["stock_name"].fillna("").astype(str)
    if "signal_side" not in df.columns:
        df["signal_side"] = ""
    df["signal_side"] = df["signal_side"].fillna("").astype(str).str.upper()
    for col in ("rk", "pct"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["_di"] = df["trade_date"].map({d: i for i, d in enumerate(dates)})
    df = df[df["_di"].notna()]
    if df.empty:
        empty = df.assign(
            _day_count=pd.Series(dtype=float), _di=pd.Series(dtype="int64")
        )
        return empty, warnings
    df["_di"] = df["_di"].astype("int64")

    df, dedupe_warnings = _dedupe_rows(df)
    warnings.extend(dedupe_warnings)

    # 防御：调用方 SQL 本应提供 rk/pct，缺失时按当日截面自行补算
    grouped = df.groupby("_di", sort=False)["fusion_score"]
    counts = grouped.transform("size").astype(float)
    if df["rk"].isna().any():
        filled = grouped.rank(ascending=False, method="min")
        df["rk"] = df["rk"].fillna(filled)
    if df["pct"].isna().any():
        asc = grouped.rank(ascending=True, method="min")
        filled = np.where(counts > 1, (asc - 1.0) / (counts - 1.0), 0.5)
        df["pct"] = df["pct"].fillna(pd.Series(filled, index=df.index))
    df["_day_count"] = counts

    warnings.extend(_sparse_day_warnings(df, dates))

    df["rk"] = df["rk"].astype(float)
    df["pct"] = df["pct"].clip(0.0, 1.0).astype(float)
    return df.sort_values(["_di", "rk"], ignore_index=True), warnings


def _dedupe_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """同一 (trade_date, symbol) 重复 = 取数层混入了多个 run，按首次出现去重。

    绝不能让 groupby 静默求平均 —— 两个模型的分数平均出来没有任何语义。
    去重后各日行数变了，调用方基于混合集算的 rk/pct 已失效，故一并置空重算。
    """
    dup_mask = df.duplicated(subset=["trade_date", "symbol"], keep=False)
    if not dup_mask.any():
        return df, []

    dup_dates = sorted(set(df.loc[dup_mask, "trade_date"]))
    detail = ""
    if "run_id" in df.columns:
        runs = sorted({str(r) for r in df.loc[dup_mask, "run_id"].dropna()})
        detail = f"，涉及 run_id: {runs[:5]}"
    removed = int(
        dup_mask.sum()
        - df.loc[dup_mask].groupby(["trade_date", "symbol"], sort=False).ngroups
    )

    kept = df[~df.duplicated(subset=["trade_date", "symbol"], keep="first")].copy()
    kept.loc[kept["trade_date"].isin(dup_dates), ["rk", "pct"]] = np.nan
    return kept, [
        f"检测到 {removed} 行 (trade_date, symbol) 重复，已按首次出现去重{detail}；"
        f"受影响日期 {dup_dates[:10]} 的 rk/pct 已按去重后截面重算 —— "
        "取数层应以 run_id 精确限定单一模型"
    ]


def _sparse_day_warnings(df: pd.DataFrame, dates: list[str]) -> list[str]:
    """行数远低于中位数的交易日通常是被后续重跑部分清理过，结论不可信。"""
    per_day = df.groupby("trade_date", sort=False).size()
    if len(per_day) < 2:
        return []
    median = float(per_day.median())
    if median <= 0:
        return []
    thin = {
        str(d): int(c) for d, c in per_day.items() if c < _SPARSE_DAY_RATIO * median
    }
    if not thin:
        return []
    return [
        f"以下交易日信号行数不足当日中位数（{median:.0f}）的"
        f"{_SPARSE_DAY_RATIO:.0%}：{thin} —— 这些日期的信号可能已被同日重跑部分清理，"
        "其截面分位不代表全市场"
    ]


class _Panel:
    """按 symbol 排序的列式面板；每只股票是一段连续切片 [starts[i], ends[i])。"""

    __slots__ = (
        "dates",
        "day_count",
        "di",
        "ends",
        "names",
        "pct",
        "rk",
        "score",
        "sides",
        "starts",
        "symbols",
    )

    def __init__(
        self,
        *,
        dates: list[str],
        symbols: list[str],
        starts: np.ndarray,
        ends: np.ndarray,
        pct: np.ndarray,
        rk: np.ndarray,
        di: np.ndarray,
        score: np.ndarray,
        day_count: np.ndarray,
        names: list[str],
        sides: list[str],
    ) -> None:
        self.dates = dates
        self.symbols = symbols
        self.starts = starts
        self.ends = ends
        self.pct = pct
        self.rk = rk
        self.di = di
        self.score = score
        self.day_count = day_count
        self.names = names
        self.sides = sides

    def blocks(self) -> Iterator[tuple[str, int, int]]:
        return zip(
            self.symbols,
            (int(v) for v in self.starts),
            (int(v) for v in self.ends),
            strict=True,
        )

    def flipped(self) -> _Panel:
        return _Panel(
            dates=self.dates,
            symbols=self.symbols,
            starts=self.starts,
            ends=self.ends,
            pct=1.0 - self.pct,
            rk=self.day_count + 1.0 - self.rk,
            di=self.di,
            score=self.score,
            day_count=self.day_count,
            names=self.names,
            sides=self.sides,
        )


def _side_view(panel: _Panel, side: str) -> _Panel:
    """空头视图 = pct 翻转 + 日内排名倒置，让同一套逻辑镜像跑一遍。"""
    return panel if side == "long" else panel.flipped()


def _build_panel(df: pd.DataFrame, dates: list[str]) -> _Panel:
    """按 symbol 分块的列式视图 —— 6000 只股票下逐组切 DataFrame 太慢。"""
    df = df.sort_values(["symbol", "_di"], ignore_index=True)
    symbol_col = df["symbol"].to_numpy(dtype=object)
    starts = np.flatnonzero(np.concatenate(([True], symbol_col[1:] != symbol_col[:-1])))
    ends = np.append(starts[1:], len(df)) if len(starts) else np.array([], dtype=int)
    return _Panel(
        dates=dates,
        symbols=[str(s) for s in symbol_col[starts]],
        starts=starts,
        ends=ends,
        pct=df["pct"].to_numpy(dtype=float),
        rk=df["rk"].to_numpy(dtype=float),
        di=df["_di"].to_numpy(dtype=int),
        score=df["fusion_score"].to_numpy(dtype=float),
        day_count=df["_day_count"].to_numpy(dtype=float),
        names=df["stock_name"].tolist(),
        sides=df["signal_side"].tolist(),
    )


# ---------------------------------------------------------------------------
# A. 个股面板
# ---------------------------------------------------------------------------


def _trend(
    day_idx: np.ndarray, pcts: np.ndarray
) -> tuple[float | None, int, float | None]:
    rho = _spearman(day_idx.astype(float), pcts)
    mk_s = _mann_kendall_s(pcts)
    p_value: float | None = None
    if rho is not None and len(pcts) >= 4:
        if abs(rho) >= 1.0:
            p_value = 0.0
        else:
            df = len(pcts) - 2
            t_stat = rho * math.sqrt(df / (1.0 - rho * rho))
            p_value = _t_two_sided_p(t_stat, df)
    return rho, mk_s, p_value


def _symbol_stats(
    panel: _Panel,
    *,
    dates: list[str],
    present_dates: list[str],
    top_k: int,
    decay: float,
    consensus_band: float,
) -> dict[str, dict[str, Any]]:
    n_dates = len(dates)
    anchor_i = n_dates - 1
    present_set = set(present_dates)
    recent = {d for d in dates[-2:] if d in present_set}
    n_present = len(present_dates)
    stats: dict[str, dict[str, Any]] = {}

    for symbol, lo, hi in panel.blocks():
        pcts = panel.pct[lo:hi]
        rks = panel.rk[lo:hi]
        idxs = panel.di[lo:hi]
        day_list = [dates[i] for i in idxs]
        appear = hi - lo

        weights = np.power(decay, anchor_i - idxs)
        weighted_pct = float((weights * pcts).sum() / weights.sum())
        topk_days = [d for d, r in zip(day_list, rks, strict=True) if r <= top_k]
        rho, mk_s, p_value = _trend(idxs, pcts)
        sides = panel.sides[lo:hi]

        if topk_days and len(topk_days) == n_present:
            membership = "core"
        elif topk_days and set(topk_days) <= recent:
            membership = "new_entrant"
        elif topk_days and not (set(topk_days) & recent):
            membership = "dropout"
        else:
            membership = "transient"

        stats[symbol] = {
            "symbol": symbol,
            "stock_name": next((s for s in panel.names[lo:hi] if s), ""),
            "appear_days": int(appear),
            "coverage": round(appear / n_dates, 4) if n_dates else 0.0,
            "mean_pct": _r3(float(pcts.mean())),
            "median_pct": _r3(float(np.median(pcts))),
            "std_pct": _r3(float(pcts.std())) or 0.0,
            "weighted_pct": _r3(weighted_pct),
            "mean_rank": _r3(float(rks.mean())),
            "best_rank": int(rks.min()),
            "worst_rank": int(rks.max()),
            "trend_rho": _r3(rho),
            "trend_p": _r3(p_value),
            "mk_s": mk_s,
            "is_monotonic_up": bool(appear >= 2 and np.all(np.diff(pcts) > 0)),
            "is_monotonic_down": bool(appear >= 2 and np.all(np.diff(pcts) < 0)),
            "up_streak": _longest_run(pcts, ascending=True),
            "down_streak": _longest_run(pcts, ascending=False),
            "topk_hits": len(topk_days),
            "band_hits": int(np.count_nonzero(pcts >= consensus_band)),
            "first_seen": day_list[0],
            "last_seen": day_list[-1],
            "first_topk_day": topk_days[0] if topk_days else None,
            "last_topk_day": topk_days[-1] if topk_days else None,
            "membership": membership,
            "buy_days": sum(1 for s in sides if s == "BUY"),
            "sell_days": sum(1 for s in sides if s == "SELL"),
            "hold_days": sum(1 for s in sides if s == "HOLD"),
        }
    return stats


def _conviction(
    stats: dict[str, dict[str, Any]], *, lam: float, mu: float
) -> dict[str, float]:
    """信念分 = 加权分位 × 覆盖率惩罚 × 波动惩罚 + 趋势加成，再归一化到 0~100。

    注意归一化是 universe 内 min-max，因此该分数是"本次窗口内的相对强弱"，
    不可跨 run 直接比较绝对值。
    """
    symbols = list(stats.keys())
    trend_z = _zscores([stats[s]["trend_rho"] for s in symbols])
    raw = []
    for symbol, tz in zip(symbols, trend_z, strict=True):
        row = stats[symbol]
        value = (
            row["weighted_pct"]
            * math.sqrt(row["coverage"])
            * (1.0 - lam * row["std_pct"])
            + mu * tz
        )
        raw.append(value)
    return dict(zip(symbols, _minmax_to_100(raw), strict=True))


# ---------------------------------------------------------------------------
# B. 分组榜单
# ---------------------------------------------------------------------------


def _is_significant_trend(row: dict[str, Any], *, direction: int) -> bool:
    rho = row["trend_rho"]
    n = row["appear_days"]
    if rho is None or n < _TREND_MIN_POINTS:
        return False
    if direction > 0 and rho < _TREND_RHO_MIN:
        return False
    if direction < 0 and rho > -_TREND_RHO_MIN:
        return False
    pairs = n * (n - 1) / 2
    mk_norm = abs(row["mk_s"]) / pairs if pairs else 0.0
    return mk_norm >= _TREND_MK_MIN and row["mk_s"] * direction > 0


_GROUP_FIELDS = (
    "symbol",
    "stock_name",
    "appear_days",
    "coverage",
    "weighted_pct",
    "mean_pct",
    "std_pct",
    "mean_rank",
    "best_rank",
    "trend_rho",
    "trend_p",
    "mk_s",
    "topk_hits",
    "bottomk_hits",
    "band_hits",
    "band_hits_short",
    "membership",
    "conviction_long",
    "conviction_short",
)


def _project(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [{k: r[k] for k in _GROUP_FIELDS} for r in rows[:limit]]


def _build_groups(
    rows: list[dict[str, Any]],
    short_rows: dict[str, dict[str, Any]],
    *,
    n_dates: int,
    n_present: int,
    top_k: int,
    min_coverage: float,
    side: str,
) -> dict[str, list[dict[str, Any]]]:
    hit_gate = math.ceil(0.6 * n_dates)
    by_conv_long = sorted(rows, key=lambda r: -r["conviction_long"])
    by_conv_short = sorted(rows, key=lambda r: -r["conviction_short"])
    groups: dict[str, list[dict[str, Any]]] = {}

    if side in ("long", "both"):
        # 门槛用分位带而非绝对 Top-K：K=20 在 5500 只里是前 0.36%，
        # 在 75%+ 换手率下「10 天有 6 天进前 0.36%」是不可能事件，恒为空集。
        groups["consensus_long"] = _project(
            [
                r
                for r in by_conv_long
                if r["coverage"] >= 0.8
                and r["weighted_pct"] >= 0.9
                and r["band_hits"] >= hit_gate
            ],
            top_k,
        )
        groups["top_hitters"] = _project(
            sorted(rows, key=lambda r: (-r["topk_hits"], -r["weighted_pct"])),
            top_k,
        )
        groups["stable_core"] = _project(
            [r for r in by_conv_long if n_present and r["topk_hits"] == n_present],
            top_k,
        )
        groups["rising"] = _project(
            sorted(
                [
                    r
                    for r in rows
                    if r["coverage"] >= min_coverage
                    and _is_significant_trend(r, direction=1)
                ],
                key=lambda r: (-r["trend_rho"], -r["weighted_pct"]),
            ),
            top_k,
        )
        groups["fading"] = _project(
            sorted(
                [
                    r
                    for r in rows
                    if r["coverage"] >= min_coverage
                    and _is_significant_trend(r, direction=-1)
                ],
                key=lambda r: (r["trend_rho"], -r["weighted_pct"]),
            ),
            top_k,
        )
        groups["new_entrants"] = _project(
            [r for r in by_conv_long if r["membership"] == "new_entrant"], top_k
        )
        groups["dropouts"] = _project(
            [r for r in by_conv_long if r["membership"] == "dropout"], top_k
        )

    if side in ("short", "both"):
        groups["consensus_short"] = _project(
            [
                r
                for r in by_conv_short
                if r["coverage"] >= 0.8
                and r["weighted_pct"] <= 0.1
                and r["band_hits_short"] >= hit_gate
            ],
            top_k,
        )
        groups["bottom_hitters"] = _project(
            sorted(rows, key=lambda r: (-r["bottomk_hits"], r["weighted_pct"])),
            top_k,
        )
        # 空头视图内趋势显著上升（= 多头分位持续下滑）且已落入偏空区间
        groups["deteriorating_short"] = _project(
            sorted(
                [
                    r
                    for r in rows
                    if r["coverage"] >= min_coverage
                    and r["weighted_pct"] <= 0.5
                    and _is_significant_trend(short_rows[r["symbol"]], direction=1)
                ],
                key=lambda r: (r["trend_rho"], r["weighted_pct"]),
            ),
            top_k,
        )
    return groups


# ---------------------------------------------------------------------------
# C. 涨跌幅榜
# ---------------------------------------------------------------------------


def _build_movers(panel: _Panel, *, top_k: int) -> dict[str, dict[str, Any]]:
    pct_jump: list[dict[str, Any]] = []
    raw_change: list[dict[str, Any]] = []
    rank_change: list[dict[str, Any]] = []
    daily_up: list[dict[str, Any]] = []
    daily_down: list[dict[str, Any]] = []
    dates = panel.dates

    for symbol, lo, hi in panel.blocks():
        if hi - lo < 2:
            continue
        name = next((s for s in panel.names[lo:hi] if s), "")
        days = [dates[i] for i in panel.di[lo:hi]]
        pcts = panel.pct[lo:hi]
        scores = panel.score[lo:hi]
        rks = panel.rk[lo:hi]
        head = {
            "symbol": symbol,
            "stock_name": name,
            "from_date": days[0],
            "to_date": days[-1],
        }

        pct_jump.append(
            {
                **head,
                "value": round(float(pcts[-1] - pcts[0]), 6),
                "pct_from": _r3(float(pcts[0])),
                "pct_to": _r3(float(pcts[-1])),
            }
        )
        raw_change.append(
            {
                **head,
                "value": round(float(scores[-1] - scores[0]), 6),
                "score_from": _r3(float(scores[0])),
                "score_to": _r3(float(scores[-1])),
            }
        )
        rank_change.append(
            {
                **head,
                "value": int(rks[0] - rks[-1]),
                "rank_from": int(rks[0]),
                "rank_to": int(rks[-1]),
            }
        )

        steps = np.diff(pcts)
        i_up = int(np.argmax(steps))
        i_dn = int(np.argmin(steps))
        daily_up.append(
            {
                **head,
                "value": round(float(steps[i_up]), 6),
                "change_date": days[i_up + 1],
                "prev_date": days[i_up],
                "pct_from": _r3(float(pcts[i_up])),
                "pct_to": _r3(float(pcts[i_up + 1])),
            }
        )
        daily_down.append(
            {
                **head,
                "value": round(float(steps[i_dn]), 6),
                "change_date": days[i_dn + 1],
                "prev_date": days[i_dn],
                "pct_from": _r3(float(pcts[i_dn])),
                "pct_to": _r3(float(pcts[i_dn + 1])),
            }
        )

    def top(items: list[dict[str, Any]], reverse: bool) -> list[dict[str, Any]]:
        return sorted(items, key=lambda r: r["value"], reverse=reverse)[:top_k]

    return {
        "pct_jump": {
            "metric": "pct_jump",
            "description": "截面分位变化（末次出现 - 首次出现），主推口径，抗单日噪声",
            "warning": None,
            "up": top(pct_jump, True),
            "down": top(pct_jump, False),
        },
        "daily_max_jump": {
            "metric": "daily_max_jump",
            "description": "相邻观测日分位的最大单日跃升/跌落，附突变发生日 change_date",
            "warning": None,
            "up": top(daily_up, True),
            "down": top(daily_down, False),
        },
        "raw_score_change": {
            "metric": "raw_score_change",
            "description": "原始 fusion_score 变化（末次出现 - 首次出现）",
            "warning": "未做截面标准化，含市场 beta，仅作对照，不可作主排序键",
            "up": top(raw_change, True),
            "down": top(raw_change, False),
        },
        "rank_change": {
            "metric": "rank_change",
            "description": "日内名次前进量（首次 rk - 末次 rk），正数为名次前进",
            "warning": None,
            "up": top(rank_change, True),
            "down": top(rank_change, False),
        },
    }


# ---------------------------------------------------------------------------
# D. 每日横截面统计
# ---------------------------------------------------------------------------


def _build_daily(
    df: pd.DataFrame,
    *,
    dates: list[str],
    top_k: int,
    consensus_pool: set[str],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    by_date = dict(df.groupby("trade_date", sort=False).__iter__())
    topk_sets: dict[str, set[str]] = {
        d: set(g.loc[g["rk"] <= top_k, "symbol"]) for d, g in by_date.items()
    }
    rows: list[dict[str, Any]] = []

    for i, date in enumerate(dates):
        if date not in by_date:
            rows.append({"trade_date": date, "missing": True, "count": 0})
            continue
        g = by_date[date]
        scores = g["fusion_score"]
        sides = g["signal_side"]
        n = len(g)
        prev = dates[i - 1] if i > 0 else None
        jaccard: float | None = None
        if prev is not None and prev in topk_sets:
            cur, old = topk_sets[date], topk_sets[prev]
            union = cur | old
            jaccard = round(len(cur & old) / len(union), 6) if union else None

        rows.append(
            {
                "trade_date": date,
                "missing": False,
                "count": n,
                "score_min": _r3(float(scores.min())),
                "score_max": _r3(float(scores.max())),
                "score_mean": _r3(float(scores.mean())),
                "score_std": _r3(float(scores.std(ddof=0))),
                "score_skew": _r3(float(scores.skew())) if n >= 3 else None,
                "score_kurtosis": _r3(float(scores.kurt())) if n >= 4 else None,
                "p1": _r3(float(scores.quantile(0.01))),
                "p5": _r3(float(scores.quantile(0.05))),
                "p50": _r3(float(scores.quantile(0.50))),
                "p95": _r3(float(scores.quantile(0.95))),
                "p99": _r3(float(scores.quantile(0.99))),
                "buy_count": int((sides == "BUY").sum()),
                "sell_count": int((sides == "SELL").sum()),
                "hold_count": int((sides == "HOLD").sum()),
                "topk_jaccard": jaccard,
                "topk_turnover": None if jaccard is None else round(1.0 - jaccard, 6),
                "consensus_overlap": len(topk_sets[date] & consensus_pool),
                "distribution": compute_score_distribution(scores.tolist()),
            }
        )
    return rows, topk_sets


# ---------------------------------------------------------------------------
# E. 窗口级元信息
# ---------------------------------------------------------------------------


def _build_meta(
    df: pd.DataFrame,
    *,
    dates: list[str],
    present_dates: list[str],
    horizon_days: int,
    top_k: int,
    decay: float,
    lam: float,
    mu: float,
    min_coverage: float,
    consensus_band: float,
    side: str,
    symbol_count: int,
    monotonic_ratio: float,
    data_warnings: list[str],
) -> dict[str, Any]:
    n = len(dates)
    h = max(1, int(horizon_days))
    autocorrs: list[float] = []
    wide = df.pivot_table(index="symbol", columns="trade_date", values="pct")
    for i in range(1, len(present_dates)):
        a, b = present_dates[i - 1], present_dates[i]
        pair = wide[[a, b]].dropna()
        if len(pair) >= 3:
            rho = _spearman(pair[a].to_numpy(), pair[b].to_numpy())
            if rho is not None:
                autocorrs.append(rho)

    warnings: list[str] = list(data_warnings)
    if n > h:
        warnings.append(
            f"窗口 {n} 天 > 持有期 {h} 天：最早梯队在锚定日前已退出，"
            "跨日聚合实际是跨轮次比较"
        )
    elif n < h:
        warnings.append(
            f"窗口 {n} 天 < 持有期 {h} 天：只覆盖持有期的一部分，各日梯队高度重叠"
        )
    bets = math.ceil(n / h) if n else 0
    if bets <= 1 and n > 1:
        warnings.append(
            f"有效独立样本仅 {bets} 个：{n} 天窗口在 {h} 天持有期下高度重叠，"
            "不要把它当成 {n} 个独立观测".replace("{n}", str(n))
        )
    missing = [d for d in dates if d not in set(present_dates)]
    if missing:
        warnings.append(f"{len(missing)} 个交易日无推理结果: {missing}")
    if n <= _MONOTONIC_NOISE_MAX_N and monotonic_ratio > _MONOTONIC_NOISE_RATIO:
        warnings.append(
            f"窗口仅 {n} 天，{monotonic_ratio:.0%} 的股票「严格单调」—— "
            "纯随机下 N=3 时也约有 1/6 的股票偶然单调，该榜单主要是噪声，"
            "请改看 up_streak 与 trend_rho"
        )

    return {
        "anchor_date": dates[-1] if dates else None,
        "start_date": dates[0] if dates else None,
        "dates": list(dates),
        "available_dates": list(present_dates),
        "missing_dates": missing,
        "window_days": n,
        "horizon_days": horizon_days,
        "effective_independent_bets": bets,
        "signal_autocorr": _r3(float(np.mean(autocorrs))) if autocorrs else None,
        "overlap_ratio": round(max(0.0, (h - (n - 1)) / h), 6) if n else 0.0,
        "symbol_count": symbol_count,
        "top_k": top_k,
        "decay": decay,
        "lam": lam,
        "mu": mu,
        "min_coverage": min_coverage,
        "consensus_band": consensus_band,
        "side": side,
        "monotonic_up_ratio": round(monotonic_ratio, 6),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def aggregate_batch(
    panel: pd.DataFrame,
    *,
    dates: list[str],
    horizon_days: int,
    top_k: int = 20,
    decay: float = 0.85,
    lam: float = 0.5,
    mu: float = 0.1,
    min_coverage: float = 0.6,
    consensus_band: float = 0.95,
    side: str = "both",
) -> dict[str, Any]:
    """聚合多日推理面板，返回 per_symbol / groups / movers / daily / meta。

    panel 列：trade_date, symbol, fusion_score, signal_side, rk, pct, stock_name。
    `pct` 越大 = 当日分数越高（PERCENT_RANK ASC），`rk=1` 为当日最高分。
    """
    if side not in ("long", "short", "both"):
        raise ValueError(f"side 必须是 long/short/both，收到 {side!r}")
    dates = [str(d) for d in dates]

    df, data_warnings = _normalize_panel(panel, dates)
    present_di = set(df["_di"].tolist())
    present_dates = [d for i, d in enumerate(dates) if i in present_di]

    if df.empty:
        return {
            "meta": _build_meta(
                df,
                dates=dates,
                present_dates=present_dates,
                horizon_days=horizon_days,
                top_k=top_k,
                decay=decay,
                lam=lam,
                mu=mu,
                min_coverage=min_coverage,
                consensus_band=consensus_band,
                side=side,
                symbol_count=0,
                monotonic_ratio=0.0,
                data_warnings=data_warnings,
            ),
            "daily": [{"trade_date": d, "missing": True, "count": 0} for d in dates],
            "per_symbol": [],
            "groups": {},
            "movers": {},
        }

    columnar = _build_panel(df, dates)
    long_stats = _symbol_stats(
        _side_view(columnar, "long"),
        dates=dates,
        present_dates=present_dates,
        top_k=top_k,
        decay=decay,
        consensus_band=consensus_band,
    )
    short_stats = _symbol_stats(
        _side_view(columnar, "short"),
        dates=dates,
        present_dates=present_dates,
        top_k=top_k,
        decay=decay,
        consensus_band=consensus_band,
    )
    conv_long = _conviction(long_stats, lam=lam, mu=mu)
    conv_short = _conviction(short_stats, lam=lam, mu=mu)

    rows: list[dict[str, Any]] = []
    for symbol, row in long_stats.items():
        rows.append(
            {
                **row,
                "bottomk_hits": short_stats[symbol]["topk_hits"],
                "band_hits_short": short_stats[symbol]["band_hits"],
                "membership_short": short_stats[symbol]["membership"],
                "conviction_long": conv_long[symbol],
                "conviction_short": conv_short[symbol],
            }
        )
    rows.sort(key=lambda r: -r["conviction_long"])

    eligible = [r for r in rows if r["appear_days"] >= 2]
    monotonic_ratio = (
        sum(1 for r in eligible if r["is_monotonic_up"]) / len(eligible)
        if eligible
        else 0.0
    )

    consensus_pool = {
        r["symbol"] for r in sorted(rows, key=lambda r: -r["conviction_long"])[:top_k]
    }
    daily, _ = _build_daily(df, dates=dates, top_k=top_k, consensus_pool=consensus_pool)

    return {
        "meta": _build_meta(
            df,
            dates=dates,
            present_dates=present_dates,
            horizon_days=horizon_days,
            top_k=top_k,
            decay=decay,
            lam=lam,
            mu=mu,
            min_coverage=min_coverage,
            consensus_band=consensus_band,
            side=side,
            symbol_count=len(rows),
            monotonic_ratio=monotonic_ratio,
            data_warnings=data_warnings,
        ),
        "daily": daily,
        "per_symbol": rows,
        "groups": _build_groups(
            rows,
            short_stats,
            n_dates=len(dates),
            n_present=len(present_dates),
            top_k=top_k,
            min_coverage=min_coverage,
            side=side,
        ),
        "movers": _build_movers(columnar, top_k=top_k),
    }
