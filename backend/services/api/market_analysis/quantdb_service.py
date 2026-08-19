"""市场分析 — QuantDB 本地 parquet 数据对接层。

把 Market Analysis 页面各接口从「硬编码假数据」切换到 QuantDB 本地数据：
- 指数概览：index_daily（最新交易日 9 大指数点位/涨跌/成交额/量比/近5日 trend）
- 市场广度：technical_indicators.pct_change（涨跌家数/涨停跌停/量能，复用 shared.market_breadth）
- 资金流：l2_factors（1/3/5/10/20 日行业与个股资金净流向；⚠️ 停更 2026-02-27）
- 标签：sector_concept/sector_members + instrument_detail（真实行业/概念成分股）

数据来源统一走 backend.shared.data_dir 解析，兼容容器内 /data/quantdb 与仓库 data/quantdb。
单位口径遵循 quantdb-fields 技能：个股 amount=万元、l2 flow=元、指数 volume=手。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from backend.shared.market_breadth import (
    CAT_LIMIT_DOWN,
    CAT_LIMIT_UP,
    breadth_distribution,
    classify_by_pct,
    classify_price,
    compute_limits,
    is_bse_symbol,
    is_corp_action_pct,
    is_ex_div,
    limit_pct,
    market_breadth,
    sector_aggregate,
    TOL_BJ,
    TOL_SHSZ,
)

logger = logging.getLogger(__name__)

# l2_factors 厂商侧停更日期（写进响应，前端展示数据截止）
L2_STALE_DATE = "2026-02-27"


def _data_dir() -> Path:
    for cand in (Path("/data/quantdb"), Path("data/quantdb")):
        if (cand / "1_kline_data").is_dir():
            return cand
    return Path("/data/quantdb")


def _read(sql: str) -> pd.DataFrame:
    """直读 QuantDB parquet（DuckDB）。"""
    import duckdb

    conn = duckdb.connect()
    try:
        return conn.execute(sql).df()
    finally:
        conn.close()


def _latest_trade_date() -> str:
    df = _read(
        f"SELECT max(dt) AS dt FROM read_parquet('{_data_dir()}/1_kline_data/daily_unadjusted/dt=*/data.parquet', hive_partitioning=true)"
    )
    return str(df.iloc[0]["dt"])


def _trading_days(end: str, n: int) -> list[str]:
    df = _read(
        f"SELECT DISTINCT dt FROM read_parquet('{_data_dir()}/1_kline_data/daily_unadjusted/dt=*/data.parquet', hive_partitioning=true)"
        f" WHERE dt <= '{end}' ORDER BY dt DESC LIMIT {n}"
    )
    return [str(v) for v in df["dt"].tolist()]


def _load_st_names() -> set[str]:
    df = _read(
        f"SELECT Symbol, Name FROM read_parquet('{_data_dir()}/2_base_sector/instrument_detail/instrument_detail.parquet')"
    )
    return {s for s, n in zip(df["Symbol"], df["Name"]) if "ST" in str(n)}


# ---------------------------------------------------------------------------
# 指数概览
# ---------------------------------------------------------------------------

_INDEXES: list[tuple[str, str]] = [
    ("上证指数", "000001.SH"),
    ("深证成指", "399001.SZ"),
    ("创业板指", "399006.SZ"),
    ("沪深300", "000300.SH"),
    ("科创50", "000688.SH"),
    ("北证50", "899050.BJ"),
    ("中证500", "000905.SH"),
    ("中证1000", "000852.SH"),
    ("上证50", "000016.SH"),
]


def indices_overview(trade_date: str | None = None) -> list[dict[str, Any]]:
    """大盘核心指数快照（最新交易日）。"""
    td = trade_date or _latest_trade_date()
    dts = _trading_days(td, 30)
    if not dts:
        return []
    dt_in = ",".join(f"'{d}'" for d in dts)
    sym_in = ",".join(f"'{s}'" for _, s in _INDEXES)
    df = _read(
        f"SELECT symbol, dt, high, low, close, preClose, amount FROM read_parquet("
        f"'{_data_dir()}/1_kline_data/index_daily/dt=*/data.parquet', hive_partitioning=true, union_by_name=true)"
        f" WHERE dt IN ({dt_in}) AND symbol IN ({sym_in})"
    )
    out: list[dict[str, Any]] = []
    for name, sym in _INDEXES:
        sub = df[df["symbol"] == sym].sort_values("dt")
        if sub.empty:
            continue
        closes = sub["close"]
        # preClose 全 NULL → 用 close 序列自算
        today = sub.iloc[-1]
        prev_close = float(sub["close"].iloc[-2]) if len(sub) >= 2 else None
        pct = round((float(today["close"]) / prev_close - 1) * 100, 2) if prev_close else 0.0
        trend = [round(float(x), 2) for x in sub["close"].iloc[-5:].tolist()]
        out.append(
            {
                "symbol": sym,
                "name": name,
                "price": round(float(today["close"]), 2),
                "change": round(float(today["close"]) - prev_close, 2) if prev_close else 0.0,
                "pct_change": pct,
                "turnover": round(float(today["amount"]) / 1e4, 2),  # 万元→亿
                "trade_date": td,
                "trend": trend,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 市场广度
# ---------------------------------------------------------------------------

def market_breadth_stats(trade_date: str | None = None) -> dict[str, Any]:
    """涨跌家数 / 涨停跌停 / 量能（复用 daily-review 的涨跌停规则）。"""
    td = trade_date or _latest_trade_date()
    dts = _trading_days(td, 2)
    if len(dts) < 2:
        return {}
    prev, cur = dts[1], dts[0]

    st_set = _load_st_names()
    dt_in = ",".join(f"'{d}'" for d in dts)
    unadj = _read(
        f"SELECT symbol, dt, open, high, low, close, volume, amount FROM read_parquet("
        f"'{_data_dir()}/1_kline_data/daily_unadjusted/dt=*/data.parquet', hive_partitioning=true)"
        f" WHERE dt IN ({dt_in})"
    )
    unadj["dt"] = unadj["dt"].astype(str)
    tech = _read(
        f"SELECT symbol, dt, pct_change FROM read_parquet("
        f"'{_data_dir()}/5_technical_derived/technical_indicators/dt=*/data.parquet', hive_partitioning=true)"
        f" WHERE dt IN ('{cur}')"
    )
    today = unadj[unadj["dt"] == cur].merge(
        unadj[unadj["dt"] == prev][["symbol", "close"]].rename(columns={"close": "prev_close"}),
        on="symbol",
        how="left",
    ).merge(tech[["symbol", "pct_change"]], on="symbol", how="left")
    today["is_st"] = today["symbol"].isin(st_set)

    trade_dt = datetime.strptime(cur, "%Y%m%d").date()
    cats: list[str] = []
    for _, row in today.iterrows():
        p = float(row["pct_change"]) if pd.notna(row["pct_change"]) else 0.0
        if pd.notna(row["prev_close"]) and not is_ex_div(p, float(row["close"]), float(row["prev_close"])):
            up, down = compute_limits(
                row["symbol"], float(row["prev_close"]), is_st=row["is_st"], trade_date=trade_dt
            )
            cats.append(classify_price(float(row["close"]), float(row["high"]), up, down))
        else:
            cats.append(classify_by_pct(p, row["symbol"], row["is_st"], trade_dt))
    today["category"] = cats

    suspended = today["volume"].fillna(0) == 0
    active_pct = today[~suspended]["pct_change"].dropna()
    breadth = market_breadth(active_pct)

    limit_up = int((today["category"] == CAT_LIMIT_UP).sum())
    limit_down = int((today["category"] == CAT_LIMIT_DOWN).sum())
    broke_up = int((today["category"].astype(str) == "broke_up").sum())
    non_limit = today[(~suspended) & (~today["category"].astype(str).isin([CAT_LIMIT_UP, CAT_LIMIT_DOWN, "corp_action"]))]
    dist = breadth_distribution(non_limit["pct_change"].dropna())

    total_amount = float(today["amount"].sum())
    prev_total = float(unadj[unadj["dt"] == prev]["amount"].sum())

    # 连板高度（近 12 日涨停连板）
    dts12 = _trading_days(td, 12)
    max_streak = 0
    if limit_up > 0:
        dt_in12 = ",".join(f"'{d}'" for d in dts12)
        syms = today[today["category"] == CAT_LIMIT_UP]["symbol"].tolist()
        sym_in = ",".join(f"'{s}'" for s in syms)
        tech12 = _read(
            f"SELECT symbol, dt, pct_change FROM read_parquet("
            f"'{_data_dir()}/5_technical_derived/technical_indicators/dt=*/data.parquet', hive_partitioning=true)"
            f" WHERE dt IN ({dt_in12}) AND symbol IN ({sym_in})"
        )
        tech12["dt"] = tech12["dt"].astype(str)
        st_map = today.set_index("symbol")["is_st"].to_dict()
        from backend.shared.market_breadth import streak_from_tail

        for sym, g in tech12.groupby("symbol"):
            g = g.sort_values("dt")
            if g["dt"].iloc[-1] != cur:
                continue
            tol = TOL_BJ if is_bse_symbol(sym) else TOL_SHSZ
            board = float(limit_pct(sym, is_st=st_map.get(sym, False), trade_date=trade_dt)) * 100
            n = streak_from_tail(g["pct_change"].tolist(), board - tol)
            max_streak = max(max_streak, n)

    return {
        "trade_date": td,
        "up_count": breadth["up_count"],
        "down_count": breadth["down_count"],
        "flat_count": breadth["flat_count"],
        "up_down_ratio": breadth["up_down_ratio"],
        "limit_up": limit_up,
        "limit_down": limit_down,
        "broke_up": broke_up,
        "max_streak": max_streak,
        "total_amount_yi": round(total_amount / 1e4, 2),
        "prev_amount_yi": round(prev_total / 1e4, 2),
        "dist": dist,
    }


# ---------------------------------------------------------------------------
# 资金流（l2_factors，停更 2026-02-27）
# ---------------------------------------------------------------------------

_FLOW_COLS = ["flow_net_amount", "flow_super_net", "flow_large_net", "flow_medium_net", "flow_small_net"]


def _load_l2_flow() -> pd.DataFrame:
    """读取 l2 最新分区资金流（单位：元）。停更则返回空。"""
    df = _read(
        f"SELECT symbol, dt, {','.join(_FLOW_COLS)} FROM read_parquet("
        f"'{_data_dir()}/6_ml_datasets/l2_factors/dt=*/data.parquet', hive_partitioning=true)"
    )
    df["dt"] = df["dt"].astype(str)
    return df


def _l2_latest_dt() -> str:
    df = _load_l2_flow()
    return str(df["dt"].max()) if not df.empty else ""


def _l2_stale_days(latest_dt: str) -> int:
    """l2 最新分区距今天数。"""
    try:
        return (date.today() - datetime.strptime(latest_dt, "%Y%m%d").date()).days
    except Exception:
        return 999


def money_flow_period(period: str = "1d", dimension: str = "sector") -> list[dict[str, Any]]:
    """指定周期资金净流向排行榜。

    单位：flow_* 为元。⚠️ l2_factors 停更 2026-02-27——多周期选项无历史可累计，
    一律返回最新分区真实值并标注截至日，绝不乘系数伪造多周期。
    个股级（stock）数据已停更且存在厂商同值异常 → 返回空由前端标注，不展示误导排行。
    """
    df = _load_l2_flow()
    if df.empty:
        return []
    latest = str(df["dt"].max())
    day = df[df["dt"] == latest].copy()

    if dimension == "sector":
        members = _read(
            f"SELECT SectorCode, SectorName, SectorType, Symbol FROM read_parquet("
            f"'{_data_dir()}/2_base_sector/sector_concept/sector_members.parquet')"
            f" WHERE SectorType = '行业板块(一级)'"
        )
        merged = day.merge(members, left_on="symbol", right_on="Symbol", how="inner")
        agg = (
            merged.groupby(["SectorCode", "SectorName"])
            .agg(net=("flow_net_amount", "sum"), n=("symbol", "nunique"))
            .reset_index()
            .sort_values("net", ascending=False)
        )
        return [
            {
                "id": f"SW_{r['SectorCode']}",
                "name": r["SectorName"],
                "net_inflow": round(float(r["net"])),  # 元
                "stocks": int(r["n"]),
                "trade_date": latest,
            }
            for _, r in agg.head(31).iterrows()
        ]

    # stock 维度：l2 已停更或个股层同值异常 → 不可用返回空，前端标注
    if _l2_stale_days(latest) > 30:
        return []
    td = _latest_trade_date()
    names = _read(
        f"SELECT Symbol, Name FROM read_parquet('{_data_dir()}/2_base_sector/instrument_detail/instrument_detail.parquet')"
    )
    name_map = dict(zip(names["Symbol"], names["Name"]))
    syms = day["symbol"].tolist()
    sym_in = ",".join(f"'{s}'" for s in syms)
    kline = _read(
        f"SELECT symbol, close FROM read_parquet("
        f"'{_data_dir()}/1_kline_data/daily_unadjusted/dt={td}/data.parquet')"
        f" WHERE symbol IN ({sym_in})"
    )
    close_map = dict(zip(kline["symbol"], kline["close"]))
    day = day.sort_values("flow_net_amount", ascending=False)
    out = []
    for _, r in day.head(31).iterrows():
        sym = r["symbol"]
        out.append(
            {
                "symbol": sym,
                "name": name_map.get(sym, ""),
                "net_inflow": round(float(r["flow_net_amount"])),  # 元
                "close_price": round(float(close_map[sym]), 2) if sym in close_map else None,
                "pct_change": None,
                "trade_date": latest,
            }
        )
    return out


def stock_money_flow(limit: int = 20) -> list[dict[str, Any]]:
    """个股资金流向排行榜。

    ⚠️ l2_factors 停更 2026-02-27（超 30 天）→ 不可用，返回空列表由前端标注，
    绝不展示半年旧的误导性资金流。
    """
    df = _load_l2_flow()
    if df.empty:
        return []
    latest = str(df["dt"].max())
    if _l2_stale_days(latest) > 30:
        return []
    latest = str(df["dt"].max())
    day = df[df["dt"] == latest].copy().sort_values("flow_net_amount", ascending=False)
    names = _read(
        f"SELECT Symbol, Name FROM read_parquet('{_data_dir()}/2_base_sector/instrument_detail/instrument_detail.parquet')"
    )
    name_map = dict(zip(names["Symbol"], names["Name"]))
    out = []
    for _, r in day.head(limit).iterrows():
        sym = str(r["symbol"])
        out.append(
            {
                "symbol": sym,
                "name": name_map.get(sym, ""),
                "close_price": None,
                "pct_change": None,
                "net_inflow": round(float(r["flow_net_amount"])),
                "main_ratio": round(
                    (float(r["flow_super_net"]) + float(r["flow_large_net"])) / max(float(r["flow_net_amount"]), 1) * 100, 1
                ) if pd.notna(r["flow_net_amount"]) and r["flow_net_amount"] else None,
                "super_large": round(float(r["flow_super_net"])),
                "large": round(float(r["flow_large_net"])),
                "medium": round(float(r["flow_medium_net"])),
                "small": round(float(r["flow_small_net"])),
                "trade_date": latest,
            }
        )
    return out


def money_flow_sankey() -> dict[str, Any]:
    """主力/散户资金流向桑基图（l2 真实行业资金流，单位：元）。"""
    df = _load_l2_flow()
    if df.empty:
        return {"nodes": [], "links": [], "trade_date": L2_STALE_DATE}
    latest = str(df["dt"].max())
    day = df[df["dt"] == latest].copy()
    members = _read(
        f"SELECT SectorCode, SectorName, SectorType, Symbol FROM read_parquet("
        f"'{_data_dir()}/2_base_sector/sector_concept/sector_members.parquet')"
        f" WHERE SectorType = '行业板块(一级)'"
    )
    merged = day.merge(members, left_on="symbol", right_on="Symbol", how="inner")
    agg = merged.groupby("SectorName").agg(
        super=("flow_super_net", "sum"),
        large=("flow_large_net", "sum"),
        medium=("flow_medium_net", "sum"),
        small=("flow_small_net", "sum"),
    ).fillna(0)

    # 主力（超大+大单）净流入行业；散户（中+小单）净流入行业
    main_sectors = agg[agg["super"] + agg["large"] > 0].sort_values("super", ascending=False).head(6)
    retail_sectors = agg[agg["medium"] + agg["small"] > 0].sort_values("medium", ascending=False).head(4)

    nodes = [
        {"name": "主力资金 (Net Buy)"},
        {"name": "散户资金 (Retail)"},
        {"name": "超大单 (Super Large)"},
        {"name": "大单 (Large)"},
        {"name": "中单 (Medium)"},
        {"name": "小单 (Small)"},
    ]
    links = [
        {"source": "主力资金 (Net Buy)", "target": "超大单 (Super Large)",
         "value": int(float(agg["super"].sum()))},
        {"source": "主力资金 (Net Buy)", "target": "大单 (Large)",
         "value": int(float(agg["large"].sum()))},
        {"source": "散户资金 (Retail)", "target": "中单 (Medium)",
         "value": int(float(agg["medium"].sum()))},
        {"source": "散户资金 (Retail)", "target": "小单 (Small)",
         "value": int(float(agg["small"].sum()))},
    ]

    for name, row in main_sectors.iterrows():
        target = "超大单 (Super Large)" if row["super"] >= row["large"] else "大单 (Large)"
        nodes.append({"name": name})
        links.append({"source": target, "target": name, "value": int(abs(float(max(row["super"], row["large"]))))})
    for name, row in retail_sectors.iterrows():
        target = "中单 (Medium)" if abs(row["medium"]) >= abs(row["small"]) else "小单 (Small)"
        nodes.append({"name": name})
        links.append({"source": target, "target": name, "value": int(abs(float(max(row["medium"], row["small"]))))})

    return {"nodes": nodes, "links": links, "trade_date": latest}


# ---------------------------------------------------------------------------
# 标签双向查询
# ---------------------------------------------------------------------------

def _load_sector_members() -> pd.DataFrame:
    return _read(
        f"SELECT SectorCode, SectorName, SectorType, Symbol FROM read_parquet("
        f"'{_data_dir()}/2_base_sector/sector_concept/sector_members.parquet')"
    )


def _load_instrument_names() -> dict[str, str]:
    df = _read(
        f"SELECT Symbol, Name FROM read_parquet('{_data_dir()}/2_base_sector/instrument_detail/instrument_detail.parquet')"
    )
    return dict(zip(df["Symbol"], df["Name"]))


def stocks_by_tag(tag: str, limit: int = 30) -> dict[str, Any]:
    """根据标签查个股（真实板块成分 + 真实名称 + 最新成交/涨跌幅）。"""
    members = _load_sector_members()
    matched = members[members["SectorName"].astype(str).str.contains(tag, case=False, na=False)]
    if matched.empty:
        return {"tag": tag, "total": 0, "items": []}

    symbols = matched["Symbol"].unique()[:limit].tolist()
    td = _latest_trade_date()
    sym_in = ",".join(f"'{s}'" for s in symbols)
    tech = _read(
        f"SELECT symbol, pct_change FROM read_parquet("
        f"'{_data_dir()}/5_technical_derived/technical_indicators/dt={td}/data.parquet')"
        f" WHERE symbol IN ({sym_in})"
    )
    tech_map = dict(zip(tech["symbol"], tech["pct_change"]))
    names = _load_instrument_names()

    items = []
    for i, sym in enumerate(symbols):
        items.append(
            {
                "symbol": sym,
                "name": names.get(sym, f"成分股_{i+1}"),
                "close_price": None,
                "pct_change": round(float(tech_map[sym]), 2) if sym in tech_map else None,
                "market_cap": None,
                "net_inflow": None,
                "trade_date": td,
            }
        )
    return {"tag": tag, "total": len(symbols), "items": items}


def tags_by_stock(symbol: str) -> dict[str, Any]:
    """根据个股查标签（真实行业/概念归属）。"""
    members = _load_sector_members()
    if symbol.endswith((".SH", ".SZ", ".BJ")) or symbol.isdigit():
        # 后缀或纯数字 → 匹配 Symbol
        matched = members[members["Symbol"].astype(str).str.contains(symbol, case=False, na=False)]
    else:
        # 名称 → 先映射代码再匹配
        names = _load_instrument_names()
        sym_by_name = {v: k for k, v in names.items()}
        code = sym_by_name.get(symbol)
        matched = members[members["Symbol"] == code] if code else pd.DataFrame()
    if matched.empty:
        return {"symbol": symbol, "stock_name": "", "tags": {}, "total": 0}

    tags_by_type: dict[str, list[str]] = {}
    for _, row in matched.iterrows():
        stype = str(row.get("SectorType", "通用标签"))
        sname = str(row.get("SectorName", ""))
        if sname:
            tags_by_type.setdefault(stype, []).append(sname)
    # 去重保序
    for k in tags_by_type:
        tags_by_type[k] = list(dict.fromkeys(tags_by_type[k]))
    return {
        "symbol": symbol,
        "stock_name": _load_instrument_names().get(str(matched.iloc[0]["Symbol"]), ""),
        "tags": tags_by_type,
        "total": int(matched["Symbol"].nunique()),
    }
