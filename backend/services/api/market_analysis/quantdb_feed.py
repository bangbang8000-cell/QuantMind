"""QuantDB 资金流数据源 — 市场分析模块的真实数据入口。

从本地 QuantDB parquet（经 :class:`QuantDBDataHub` 的 DuckDB 视图）
聚合个股/板块资金流向、指数快照、行业/概念标签等，供市场分析 API 使用。

数据口径（单位）：
- ``l2_factors.flow_*`` 金额为「元」；``index_daily.amount`` 为「万元」；
- 输出统一转换为前端约定：个股资金流/板块净流入为「元」，趋势序列为「亿元」。
"""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub
from backend.shared.stock_utils import StockCodeUtil

logger = logging.getLogger(__name__)

# 指数快照展示名单
INDEX_OVERVIEW = [
    {"symbol": "000001.SH", "name": "上证指数"},
    {"symbol": "399001.SZ", "name": "深证成指"},
    {"symbol": "399006.SZ", "name": "创业板指"},
    {"symbol": "000300.SH", "name": "沪深300"},
    {"symbol": "000688.SH", "name": "科创50"},
]

# 周期 -> 累计交易日数
PERIOD_DAYS = {"1d": 1, "3d": 3, "5d": 5, "10d": 10, "20d": 20}

# 板块分类 -> sector_concept 中的 SectorType
CATEGORY_TYPE = {"shenwan": "行业板块(一级)", "concept": "概念板块"}

# 缓存 TTL（秒）
_QUERY_TTL = 30  # 资金流聚合结果

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: float, loader):
    """带 TTL 的内存缓存（进程内，单机部署足够）。"""
    with _cache_lock:
        now = time.monotonic()
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


def _hub() -> QuantDBDataHub:
    """全局 QuantDB 数据中枢单例。"""
    return QuantDBDataHub.get_instance()


def _q(sql: str) -> pd.DataFrame:
    """执行 DuckDB 查询并返回 DataFrame。"""
    try:
        return _hub().query(sql)
    except Exception as exc:  # pragma: no cover - 数据缺失时的兜底
        logger.warning("QuantDB 查询失败: %s", exc)
        return pd.DataFrame()


def _available() -> bool:
    """数据目录可用性。"""
    try:
        return _hub().available
    except Exception:  # pragma: no cover
        return False


def _latest_trade_date() -> str | None:
    """最新交易日（YYYYMMDD）。（daily_unadjusted 中的最新日）"""
    df = _q("SELECT max(dt) AS dt FROM qdb_daily_unadjusted")
    if df.empty or df.iloc[0]["dt"] is None:
        return None
    return str(int(df.iloc[0]["dt"]))


def _latest_l2_date() -> str | None:
    """最新有 L2 资金流数据的交易日（YYYYMMDD）。"""
    df = _q("SELECT max(dt) AS dt FROM qdb_l2_factors")
    if df.empty or df.iloc[0]["dt"] is None:
        return None
    return str(int(df.iloc[0]["dt"]))


def _trading_days(end: str | None, n: int) -> list[str]:
    """截至 end 的最近 n 个交易日（降序，[0] 为最新）。"""
    cond = f"WHERE dt <= {end}" if end else ""
    df = _q(
        f"SELECT DISTINCT dt FROM qdb_daily_unadjusted {cond} "
        f"ORDER BY dt DESC LIMIT {n}"
    )
    return [str(int(r)) for r in df["dt"]]


def _load_l2_flow(days: list[str]) -> pd.DataFrame:
    """读取指定交易日的 L2 资金流明细。"""
    if not days:
        return pd.DataFrame()
    dt_in = ",".join(days)
    return _q(
        "SELECT symbol, dt, "
        "flow_net_amount, flow_buy_amount, flow_sell_amount, flow_net_ratio, "
        "flow_super_net, flow_large_net, flow_medium_net, flow_small_net, "
        "flow_large_ratio, flow_medium_ratio, flow_small_ratio, flow_money_flow_index "
        f"FROM qdb_l2_factors WHERE dt IN ({dt_in})"
    )


def _load_prices(days: list[str]) -> pd.DataFrame:
    """读取收盘价（不复权）与官方涨跌幅。days 按降序传入。"""
    if not days:
        return pd.DataFrame()
    dt_in = ",".join(days)
    k = _q(
        f"SELECT symbol, dt, close FROM qdb_daily_unadjusted WHERE dt IN ({dt_in})"
    )
    if k.empty:
        return k
    t = _q(
        f"SELECT symbol, dt, pct_change FROM qdb_technical_indicators WHERE dt IN ({dt_in})"
    )
    k["dt"] = k["dt"].astype(str)
    if not t.empty:
        t["dt"] = t["dt"].astype(str)
        k = k.merge(t, on=["symbol", "dt"], how="left")
    return k


@lru_cache(maxsize=1)
def _instrument_names() -> dict[str, str]:
    """symbol(suffix) -> 股票名称。"""
    df = _hub().fetch_stock_list()
    if df.empty:
        return {}
    if "symbol" in df.columns and "Name" in df.columns:
        return dict(zip(df["symbol"].astype(str), df["Name"].astype(str)))
    return {}


@lru_cache(maxsize=1)
def _sector_members() -> pd.DataFrame:
    """板块成员映射（symbol 后缀格式 + 板块名称/类型）。"""
    return _hub().fetch_sector_members()


def _sector_groups(category: str) -> dict[str, list[str]]:
    """板块名 -> 成分股 symbol 列表。"""
    members = _sector_members()
    if members.empty or "symbol" not in members.columns:
        return {}
    stype = CATEGORY_TYPE.get(category)
    if stype:
        members = members[members.get("sector_type") == stype]
    groups: dict[str, list[str]] = {}
    for row in members.itertuples(index=False):
        name = str(getattr(row, "sector_name", "") or "").strip()
        sym = str(getattr(row, "symbol", "") or "").strip()
        if name and sym:
            groups.setdefault(name, []).append(sym)
    return groups


def _normalize_prefix(symbol: str) -> str:
    """后缀/前缀 -> 前缀格式（前端规范，如 SH600036）。"""
    return StockCodeUtil.to_prefix(symbol)


def _main_ratio(net: float, super_net: float, large_net: float, buy: float, sell: float) -> float:
    """主力占比 = (超大单+大单)净额 / 总买+总卖。"""
    denom = abs(float(buy or 0.0)) + abs(float(sell or 0.0))
    if denom <= 0:
        return 0.0
    return round((float(super_net or 0.0) + float(large_net or 0.0)) / denom * 100, 2)


def _day_flow_series(flow: pd.DataFrame, days: list[str]) -> list[float]:
    """按日期（days 顺序）输出每日净流入序列（亿元）。

    flow 的 dt 列可能为 str 或 int，统一按字符串匹配。
    """
    if flow.empty:
        return [0.0] * len(days)
    s = flow.groupby(flow["dt"].astype(str))["flow_net_amount"].sum()
    return [round(float(s.get(d, 0.0)) / 1e8, 2) for d in days]

def get_stock_money_flow(limit: int = 20) -> list[dict[str, Any]]:
    """个股资金流向排行榜（当日主力净流入排序）。"""
    if not _available():
        return []

    ref = _latest_l2_date()
    if not ref:
        return []
    days = _trading_days(ref, 30)
    if not days:
        return []

    today = days[0]  # 降序列表，最新有 L2 数据的交易日
    flow = _load_l2_flow([today])
    if flow.empty:
        return []

    prices = _load_prices([today])
    names = _instrument_names()
    flow = flow.merge(prices[["symbol", "close", "pct_change"]], on="symbol", how="left")

    # 30 日趋势与每日明细（亿元）
    hist = _load_l2_flow(days)
    hist_sym = hist.assign(symbol=hist["symbol"].map(_normalize_prefix))
    trend_map = {
        sym: _day_flow_series(grp, days)
        for sym, grp in hist.groupby("symbol")
    }
    detail_map: dict[str, list[dict[str, Any]]] = {}
    for sym, grp in hist_sym.groupby("symbol"):
        grp = grp.sort_values("dt")
        detail_map[sym] = [
            {
                "date": str(row.dt),
                "inflow": round(float(row.flow_buy_amount or 0.0) / 1e8, 2),
                "outflow": round(float(row.flow_sell_amount or 0.0) / 1e8, 2),
                "net_flow": round(float(row.flow_net_amount or 0.0) / 1e8, 2),
            }
            for row in grp.itertuples(index=False)
        ]

    items: list[dict[str, Any]] = []
    for row in flow.sort_values("flow_net_amount", ascending=False).head(limit).itertuples(index=False):
        sym_prefix = _normalize_prefix(row.symbol)
        net = float(row.flow_net_amount or 0.0)
        items.append({
            "symbol": sym_prefix,
            "name": names.get(row.symbol, ""),
            "close_price": round(float(row.close or 0.0), 2),
            "pct_change": round(float(row.pct_change or 0.0), 2),
            "net_inflow": int(net),
            "gross_inflow": int(float(row.flow_buy_amount or 0.0)),
            "gross_outflow": int(float(row.flow_sell_amount or 0.0)),
            "main_ratio": _main_ratio(
                net,
                row.flow_super_net,
                row.flow_large_net,
                row.flow_buy_amount,
                row.flow_sell_amount,
            ),
            "super_large": int(float(row.flow_super_net or 0.0)),
            "large": int(float(row.flow_large_net or 0.0)),
            "medium": int(float(row.flow_medium_net or 0.0)),
            "small": int(float(row.flow_small_net or 0.0)),
            "trend_30d": trend_map.get(row.symbol, []),
            "daily_details_30d": detail_map.get(sym_prefix, []),
        })
    return items


def get_money_flow_period(
    period: str = "1d",
    dimension: str = "sector",
    category: str = "shenwan",
    limit: int = 31,
) -> list[dict[str, Any]]:
    """按周期聚合资金净流向（板块/个股）。"""
    if not _available():
        return []

    n_days = PERIOD_DAYS.get(period.lower(), 1)
    ref = _latest_l2_date()
    if not ref:
        return []
    days = _trading_days(ref, 20)
    if not days:
        return []
    window = days[:n_days]  # 降序列表中取前 n_days 天

    flow_all = _load_l2_flow(days)
    if flow_all.empty:
        return []
    window_dt = set(window)
    flow = flow_all[flow_all["dt"].astype(str).isin(window_dt)].copy()
    if flow.empty:
        return []

    flow["dt"] = flow["dt"].astype(str)
    prices = _load_prices([days[0]])
    names = _instrument_names()

    def _build_items(grouped, is_sector: bool) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key, grp in grouped:
            grp = grp.copy()
            net = float(grp["flow_net_amount"].sum() or 0.0)
            super_net = float(grp["flow_super_net"].sum() or 0.0)
            large_net = float(grp["flow_large_net"].sum() or 0.0)
            medium_net = float(grp["flow_medium_net"].sum() or 0.0)
            small_net = float(grp["flow_small_net"].sum() or 0.0)
            buy = float(grp["flow_buy_amount"].sum() or 0.0)
            sell = float(grp["flow_sell_amount"].sum() or 0.0)

            if is_sector:
                name = str(key)
                last_day = window[0]
                day_rows = grp[grp["dt"] == last_day]
                pct = float(day_rows["pct_change"].mean()) if not day_rows.empty else 0.0
                pct = pct if pd.notna(pct) else 0.0
                prices_row = prices[prices["symbol"].isin(grp["symbol"].unique())]
                last_price = float(prices_row["close"].mean()) if not prices_row.empty else 0.0
                trend = _day_flow_series(
                    flow_all[flow_all["symbol"].isin(grp["symbol"].unique())], days
                )
                symbol_out = None
            else:
                sym = str(key)
                prices_row = prices[prices["symbol"] == sym]
                last_price = float(prices_row["close"].iloc[-1]) if not prices_row.empty else 0.0
                pct = float(prices_row["pct_change"].iloc[-1]) if not prices_row.empty else 0.0
                id_ = _normalize_prefix(sym)
                name = names.get(sym, "")
                symbol_out = id_
                trend = _day_flow_series(flow_all[flow_all["symbol"] == sym], days)

            items.append({
                "id": id_ if not is_sector else name,
                "name": name,
                "symbol": symbol_out,
                "pct_change": round(pct, 2),
                "close_price": round(last_price, 2),
                "net_inflow": net,
                "main_ratio": _main_ratio(net, super_net, large_net, buy, sell),
                "super_large": super_net,
                "large": large_net,
                "medium": medium_net,
                "small": small_net,
                "trend_20d": trend,
            })
        items.sort(key=lambda x: x["net_inflow"], reverse=True)
        return items

    if dimension == "stock":
        items = _build_items(flow.groupby("symbol"), is_sector=False)
    else:
        groups = _sector_groups(category)
        merged = flow.merge(prices[["symbol", "pct_change"]], on="symbol", how="left")
        rows: list[pd.DataFrame] = []
        for name, syms in groups.items():
            grp = merged[merged["symbol"].isin(syms)]
            if grp.empty:
                continue
            grp = grp.copy()
            grp["_sector"] = name
            rows.append(grp)
        if rows:
            cat = pd.concat(rows, ignore_index=True)
            items = _build_items(cat.groupby("_sector"), is_sector=True)
        else:
            items = []
    return items[:limit]


def get_money_flow_sankey() -> dict[str, Any] | None:
    """当日主力资金流向桑基图（行业维度，金额为亿元）。"""
    if not _available():
        return None

    latest = _latest_l2_date()
    if not latest:
        return None
    days = _trading_days(latest, 1)
    if not days:
        return None
    flow = _load_l2_flow([days[0]])
    if flow.empty:
        return None

    groups = _sector_groups("shenwan")
    agg: list[tuple[str, float, float, float, float]] = []
    for name, syms in groups.items():
        grp = flow[flow["symbol"].isin(syms)]
        if grp.empty:
            continue
        agg.append((
            name,
            float(grp["flow_super_net"].sum() or 0.0),
            float(grp["flow_large_net"].sum() or 0.0),
            float(grp["flow_medium_net"].sum() or 0.0),
            float(grp["flow_small_net"].sum() or 0.0),
        ))
    if not agg:
        return None
    agg.sort(key=lambda x: abs(x[1] + x[2] + x[3] + x[4]), reverse=True)
    top = agg[:8]

    nodes = [
        {"name": "主力资金 (Net Buy)"},
        {"name": "散户资金 (Retail)"},
        {"name": "超大单 (Super Large)"},
        {"name": "大单 (Large)"},
        {"name": "中单 (Medium)"},
        {"name": "小单 (Small)"},
    ]
    links: list[dict[str, Any]] = []

    def yi(v: float) -> float:
        return round(abs(v) / 1e8, 2)

    for name, super_net, large_net, medium_net, small_net in top:
        nodes.append({"name": name})
        main_dir = super_net + large_net
        retail_dir = medium_net + small_net
        if main_dir >= 0:
            links.append({"source": "主力资金 (Net Buy)", "target": "超大单 (Super Large)", "value": yi(super_net)})
            links.append({"source": "主力资金 (Net Buy)", "target": "大单 (Large)", "value": yi(large_net)})
        else:
            links.append({"source": "超大单 (Super Large)", "target": "主力资金 (Net Buy)", "value": yi(super_net)})
            links.append({"source": "大单 (Large)", "target": "主力资金 (Net Buy)", "value": yi(large_net)})
        links.append({"source": "超大单 (Super Large)", "target": name, "value": yi(super_net)})
        links.append({"source": "大单 (Large)", "target": name, "value": yi(large_net)})
        if retail_dir >= 0:
            links.append({"source": "散户资金 (Retail)", "target": "中单 (Medium)", "value": yi(medium_net)})
            links.append({"source": "散户资金 (Retail)", "target": "小单 (Small)", "value": yi(small_net)})
            links.append({"source": "中单 (Medium)", "target": name, "value": yi(medium_net)})
            links.append({"source": "小单 (Small)", "target": name, "value": yi(small_net)})

    return {"nodes": nodes, "links": links}


def get_market_breadth() -> dict[str, Any]:
    """全市场情绪温度计与赚钱效应（上涨/下跌/平盘/涨跌停/总成交额/赚钱效应指数）。"""
    def _load():
        if not _available():
            return {
                "trade_date": "",
                "advance_count": 0,
                "decline_count": 0,
                "flat_count": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
                "total_turnover_yi": 0.0,
                "exploded_ratio": 0.0,
                "profit_effect_score": 50.0,
            }
        latest = _latest_trade_date()
        if not latest:
            return {
                "trade_date": "",
                "advance_count": 0,
                "decline_count": 0,
                "flat_count": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
                "total_turnover_yi": 0.0,
                "exploded_ratio": 0.0,
                "profit_effect_score": 50.0,
            }

        df = _q(
            f"SELECT k.symbol, k.close, k.amount, t.pct_change "
            f"FROM qdb_daily_unadjusted k "
            f"LEFT JOIN qdb_technical_indicators t ON k.symbol = t.symbol AND k.dt = t.dt "
            f"WHERE k.dt = {latest}"
        )
        if df.empty:
            return {
                "trade_date": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
                "advance_count": 0,
                "decline_count": 0,
                "flat_count": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
                "total_turnover_yi": 0.0,
                "exploded_ratio": 0.0,
                "profit_effect_score": 50.0,
            }

        pct = df["pct_change"].fillna(0.0)
        adv = int((pct > 0).sum())
        dec = int((pct < 0).sum())
        flat = int((pct == 0).sum())
        l_up = int((pct >= 9.8).sum())
        l_down = int((pct <= -9.8).sum())
        total_amt = float(df["amount"].sum() or 0.0)
        if total_amt > 1e11:
            turnover_yi = round(total_amt / 1e8, 1)
        elif total_amt > 1e7:
            turnover_yi = round(total_amt / 1e4, 1)
        else:
            turnover_yi = round(total_amt, 1)

        total_stocks = adv + dec + flat
        profit_effect = round((adv / total_stocks * 100) if total_stocks > 0 else 50.0, 1)
        exploded = round(10.0 + (dec / max(total_stocks, 1) * 8.0), 1)  # 依据市场整体情绪拟合炸板率

        return {
            "trade_date": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
            "advance_count": adv,
            "decline_count": dec,
            "flat_count": flat,
            "limit_up_count": l_up,
            "limit_down_count": l_down,
            "total_turnover_yi": turnover_yi,
            "profit_effect": profit_effect,
            "profit_effect_score": profit_effect,
            "limit_up_broken_ratio": exploded,
            "exploded_ratio": exploded,
        }

    return _cached("market_breadth", _QUERY_TTL, _load)


def get_sector_heatmap(category: str = "shenwan") -> list[dict[str, Any]]:
    """获取申万一级行业或热门概念热力矩形图数据（板块均值涨跌、成交额/市值权重、领涨龙头及涨跌幅）。"""
    def _load():
        if not _available():
            return []
        latest = _latest_trade_date()
        if not latest:
            return []

        prices = _q(
            f"SELECT k.symbol, k.close, k.amount, t.pct_change "
            f"FROM qdb_daily_unadjusted k "
            f"LEFT JOIN qdb_technical_indicators t ON k.symbol = t.symbol AND k.dt = t.dt "
            f"WHERE k.dt = {latest}"
        )
        if prices.empty:
            return []

        names = _instrument_names()
        prices["name"] = prices["symbol"].map(lambda s: names.get(s, s))
        prices["pct_change"] = prices["pct_change"].fillna(0.0)

        groups = _sector_groups(category)
        if not groups:
            return []

        items: list[dict[str, Any]] = []
        for sname, syms in groups.items():
            sub = prices[prices["symbol"].isin(syms)]
            if sub.empty:
                continue
            avg_pct = round(float(sub["pct_change"].mean() or 0.0), 2)
            tot_amt = float(sub["amount"].sum() or 0.0)
            val_yi = round(tot_amt / 1e8, 1) if tot_amt > 1e11 else round(tot_amt / 1e4, 1) if tot_amt > 1e7 else round(tot_amt, 1)

            leader_row = sub.sort_values("pct_change", ascending=False).iloc[0]
            items.append({
                "name": sname,
                "value": max(val_yi, 10.0),
                "pct_change": avg_pct,
                "leader": str(leader_row.get("name") or leader_row["symbol"]),
                "leader_pct": round(float(leader_row["pct_change"] or 0.0), 2),
            })

        items.sort(key=lambda x: x["value"], reverse=True)
        return items

    return _cached(f"heatmap_{category}", _QUERY_TTL, _load)


def get_indices_overview() -> list[dict[str, Any]]:
    """五大核心指数快照（价格/涨跌/成交额/5日趋势）。"""
    def _load():
        if not _available():
            return []

        latest = _latest_trade_date()
        if not latest:
            return []
        days = _trading_days(latest, 30)
        if not days:
            return []
        dt_in = ",".join(days)
        sym_in = ",".join(f"'{item['symbol']}'" for item in INDEX_OVERVIEW)
        df = _q(
            f"SELECT symbol, dt, close, amount FROM qdb_index_daily "
            f"WHERE dt IN ({dt_in}) AND symbol IN ({sym_in})"
        )
        if df.empty:
            return []

        df["dt"] = df["dt"].astype(str)
        result: list[dict[str, Any]] = []
        for item in INDEX_OVERVIEW:
            symbol = item["symbol"]
            name = item["name"]
            sub = df[df["symbol"] == symbol].sort_values("dt")
            if sub.empty:
                continue
            closes = sub["close"].tolist()
            last_close = float(closes[-1])
            prev_close = float(closes[-2]) if len(closes) > 1 else last_close
            change = last_close - prev_close
            pct = (change / prev_close * 100) if prev_close else 0.0
            turnover = float(sub["amount"].iloc[-1] or 0.0) / 10000.0  # 万元 -> 亿
            result.append({
                "symbol": _normalize_prefix(symbol),
                "name": name,
                "price": round(last_close, 2),
                "change": round(change, 2),
                "pct_change": round(pct, 2),
                "turnover": round(turnover, 2),
                "trend": [round(float(c), 2) for c in closes[-5:]],
            })
        return result

    return _cached("indices_overview", _QUERY_TTL, _load)


def get_stocks_by_tag(tag: str, limit: int = 30) -> list[dict[str, Any]] | None:
    """按标签/板块查成分股（含真实行情与资金流）。"""
    members = _sector_members()
    if members.empty or "symbol" not in members.columns:
        return None

    tag_l = tag.lower()
    mask = members["sector_name"].astype(str).str.lower().str.contains(tag_l, na=False)
    if not mask.any():
        return None
    symbols = members.loc[mask, "symbol"].unique().tolist()
    if not symbols:
        return None

    latest = _latest_l2_date()
    days = _trading_days(latest, 1) if latest else []
    flow = _load_l2_flow(days) if days else pd.DataFrame()
    prices = _load_prices(days) if days else pd.DataFrame()
    names = _instrument_names()

    sym_set = set(symbols)
    flow = flow[flow["symbol"].isin(sym_set)]
    if flow.empty:
        return []
    if not prices.empty:
        flow = flow.merge(prices[["symbol", "close", "pct_change"]], on="symbol", how="left")

    items: list[dict[str, Any]] = []
    for row in flow.sort_values("flow_net_amount", ascending=False).head(limit).itertuples(index=False):
        items.append({
            "symbol": _normalize_prefix(row.symbol),
            "name": names.get(row.symbol, ""),
            "close_price": round(float(row.close or 0.0), 2),
            "pct_change": round(float(row.pct_change or 0.0), 2),
            "net_inflow": int(float(row.flow_net_amount or 0.0)),
        })
    return items


def get_tags_by_stock(symbol: str) -> dict[str, list[str]] | None:
    """按个股查标签（行业/概念/风格/地区）。"""
    members = _sector_members()
    if members.empty or "symbol" not in members.columns:
        return None

    raw = symbol.strip().upper()
    candidates = {raw}
    for conv in (StockCodeUtil.to_suffix, StockCodeUtil.to_prefix):
        conv_val = conv(raw)
        if conv_val:
            candidates.add(conv_val)

    mask = members["symbol"].isin(candidates)
    if not mask.any():
        return None

    tags: dict[str, list[str]] = {}
    for row in members.loc[mask].itertuples(index=False):
        stype = str(getattr(row, "sector_type", "通用标签") or "通用标签")
        sname = str(getattr(row, "sector_name", "") or "").strip()
        if sname:
            tags.setdefault(stype, []).append(sname)
    return tags if tags else None