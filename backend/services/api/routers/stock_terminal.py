"""个股终端（Stock Terminal）后端接口

P1 范围：
1. GET /list      股票列表（SH/SZ/BJ 分类 + 行业过滤 + 检索 + 分页）
2. GET /industries 行业列表（过滤下拉用）
3. GET /profile   个股概况聚合（详情 + 估值 + 宽基归属 + 概念板块）

数据全部来自本地 QuantDB parquet（instrument_detail / technical_indicators /
valuation / index_weights / sector_concept），无外部依赖。

K 线数据复用既有 /api/v1/market/kline 与 /api/v1/market/index-kline，
本模块不重复实现。
"""

from __future__ import annotations

import math
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.services.api.user_app.middleware.auth import get_current_user
from backend.shared.database_manager_v2 import get_session
from backend.shared.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/stock-terminal", tags=["StockTerminal"])

# 数据目录（与 quantdb_hub 同源，直接复用其解析逻辑避免双配置）
_DATA_DIR: Path | None = None


def _quantdb_dir() -> Path:
    global _DATA_DIR
    if _DATA_DIR is None:
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        _DATA_DIR = Path(QuantDBDataHub.get_instance().data_dir)
    return _DATA_DIR


# ---------------------------------------------------------------------------
# 内部数据层（进程内缓存，TTL 5 分钟；数据日频更新，缓存按交易日粒度足够）
# ---------------------------------------------------------------------------

_UNIVERSE_TTL = 300.0
_universe_cache: dict[str, Any] = {"df": None, "ts": 0.0, "trade_date": ""}
_concept_cache: dict[str, Any] = {"ts": 0.0, "symbol_map": {}}

# 概念板块展示上限：单只股票概念过多时截断（板块成员表全市场概念归属）
_MAX_CONCEPTS = 24


def _classify_board(symbol: str) -> str:
    """按代码归类市场板块：SH 主板/科创板、SZ 主板/创业板、BJ 北交所。"""
    code = symbol.split(".")[0]
    if symbol.endswith(".SH"):
        if code.startswith("68"):
            return "科创板"
        return "沪市主板"
    if symbol.endswith(".SZ"):
        if code.startswith("30"):
            return "创业板"
        return "深市主板"
    if symbol.endswith(".BJ"):
        return "北交所"
    return "其他"


def _exchange_of(symbol: str) -> str:
    if symbol.endswith(".SH"):
        return "SH"
    if symbol.endswith(".SZ"):
        return "SZ"
    if symbol.endswith(".BJ"):
        return "BJ"
    return ""


def _latest_partition(base: Path) -> Path | None:
    """取 Hive 分区数据集的最新 dt 分区文件。"""
    if not base.exists():
        return None
    parts = sorted(p for p in base.glob("dt=*") if (p / "data.parquet").exists())
    if not parts:
        return None
    return parts[-1] / "data.parquet"


def _safe_f(v: Any) -> float | None:
    """NaN/inf -> None，保证 JSON 可序列化。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _load_universe() -> tuple[pd.DataFrame, str]:
    """全市场快照：instrument_detail + 最新 technical_indicators(close/pct_change)。"""
    now = time.time()
    cached = _universe_cache["df"]
    if cached is not None and now - _universe_cache["ts"] < _UNIVERSE_TTL:
        return cached, _universe_cache["trade_date"]

    d = _quantdb_dir()
    detail_file = d / "2_base_sector" / "instrument_detail" / "instrument_detail.parquet"
    if not detail_file.exists():
        raise HTTPException(status_code=503, detail="本地 instrument_detail 数据缺失")

    detail_cols = [
        "Symbol", "Name", "rs_hyname", "Zsz", "Ltsz", "DynaPE", "PB_MRQ",
        "StaffNum", "MainBusiness", "IPO_Price", "ZTPrice", "DTPrice",
        "RZRQ", "HSGT", "STGP", "IsHKGP", "J_zgb", "FreeLtgb", "BetaValue",
        "BelongHS300",
    ]
    raw = pd.read_parquet(detail_file)
    keep = [c for c in detail_cols if c in raw.columns]
    df = raw[keep].copy()

    # 最新收盘/涨跌幅（technical_indicators 最新分区，全市场一次读三列）
    ti_file = _latest_partition(d / "5_technical_derived" / "technical_indicators")
    trade_date = ""
    if ti_file is not None:
        ti = pd.read_parquet(ti_file, columns=["symbol", "close", "pct_change"])
        trade_date = ti_file.parent.name.replace("dt=", "")
        df = df.merge(ti, left_on="Symbol", right_on="symbol", how="left").drop(
            columns=["symbol"], errors="ignore"
        )
    for col in ("close", "pct_change"):
        if col not in df.columns:
            df[col] = float("nan")

    df["board"] = df["Symbol"].map(_classify_board)
    df["exchange"] = df["Symbol"].map(_exchange_of)

    _universe_cache.update({"df": df, "ts": now, "trade_date": trade_date})
    return df, trade_date


_INDEX_NAMES = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "000016.SH": "上证50",
    "000688.SH": "科创50",
    "399006.SZ": "创业板指",
    "000906.SH": "中证800",
}


def _index_membership(symbol: str) -> list[dict[str, Any]]:
    """查询个股归属的宽基指数（7 个指数权重文件逐一匹配）。"""
    out: list[dict[str, Any]] = []
    d = _quantdb_dir()
    weights_dir = d / "2_base_sector" / "index_weights"
    if not weights_dir.exists():
        return out
    for file in sorted(weights_dir.glob("*.parquet")):
        code = file.stem
        if code == "index_weights" or code not in _INDEX_NAMES:
            continue
        try:
            w = pd.read_parquet(file)
        except Exception as exc:  # noqa: BLE001
            logger.warning("read index weights %s failed: %s", file.name, exc)
            continue
        sym_col = "Symbol" if "Symbol" in w.columns else "symbol"
        row = w[w[sym_col] == symbol]
        if not row.empty:
            weight = _safe_f(row.iloc[0].get("Weight"))
            out.append({
                "index_code": code,
                "index_name": _INDEX_NAMES[code],
                "weight": weight,
            })
    return out


def _concepts_of(symbol: str) -> list[str]:
    """个股概念板块列表（sector_members 按 Symbol 反查，缓存 symbol->concepts 全表）。"""
    now = time.time()
    if now - _concept_cache["ts"] < _UNIVERSE_TTL and _concept_cache["symbol_map"]:
        return _concept_cache["symbol_map"].get(symbol, [])[:_MAX_CONCEPTS]

    d = _quantdb_dir()
    f = d / "2_base_sector" / "sector_concept" / "sector_members.parquet"
    if not f.exists():
        return []
    try:
        sm = pd.read_parquet(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read sector_members failed: %s", exc)
        return []
    sym_col = "Symbol" if "Symbol" in sm.columns else "symbol"
    name_col = "SectorName" if "SectorName" in sm.columns else "sector_name"
    sm = sm[[sym_col, name_col]].dropna()
    symbol_map: dict[str, list[str]] = {}
    for sym, name in zip(sm[sym_col], sm[name_col]):
        symbol_map.setdefault(sym, []).append(str(name))
    _concept_cache.update({"ts": now, "symbol_map": symbol_map})
    return symbol_map.get(symbol, [])[:_MAX_CONCEPTS]


def _norm_dividend(v: Any) -> float | None:
    """valuation.dividend_rate 口径归一为百分数（<=1 视为小数）。"""
    f = _safe_f(v)
    if f is None:
        return None
    return round(f * 100, 2) if 0 < f <= 1 else round(f, 2)


def _flag(v: Any) -> bool:
    """标量 '1'/'0'/1/0/None -> bool（profile 中 r.get() 返回标量，不能用 Series.fillna）。"""
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# P2: 财务报表 + 通用时序（估值/筹码资金/两融/情绪/股东）
# ---------------------------------------------------------------------------

from datetime import date as _date, timedelta as _timedelta  # noqa: E402

import re as _re

_SYMBOL_RE = _re.compile(r"^\d{6}\.(SH|SZ|BJ)$")

# 财务三表 + 每股指标 关键字段（单位: 元；输出统一转亿元）
_INCOME_COLS = {
    "revenue": "营业收入", "total_operating_cost": "营业成本",
    "oper_profit": "营业利润", "net_profit_excl_min_int_inc": "归母净利润",
    "research_expenses": "研发费用", "sale_expense": "销售费用",
    "inc_tax": "所得税",
}
_BALANCE_COLS = {
    "tot_assets": "总资产", "tot_liab": "总负债", "total_equity": "股东权益",
    "cash_equivalents": "货币资金", "inventories": "存货",
    "total_current_assets": "流动资产", "accounts_payable": "应付账款",
    "shortterm_loan": "短期借款",
}
_CASHFLOW_COLS = {
    "net_cash_flows_oper_act": "经营现金流净额",
    "net_cash_flows_inv_act": "投资现金流净额",
    "net_cash_flows_fnc_act": "筹资现金流净额",
}
_PERSHARE_COLS = {
    "equity_roe": "ROE(%)", "gross_profit": "毛利率(%)", "net_profit": "净利率(%)",
    "inc_revenue_rate": "营收增速(%)", "inc_net_profit_rate": "净利增速(%)",
    "s_fa_eps_basic": "EPS(元)", "s_fa_bps": "每股净资产(元)",
    "sales_cash_flow": "销售现金流比",
}

# /series 时序组: (DuckDB 视图, 输出列)
_SERIES_GROUPS: dict[str, tuple[str, list[str]]] = {
    "valuation": ("qdb_valuation", [
        "pe_ttm", "pb", "ps_ttm", "dividend_rate", "total_mv", "float_mv",
    ]),
    "margin": ("qdb_margin_trading", [
        "finance_balance", "finance_net", "finance_buy", "finance_repay",
    ]),
    "chip": ("qdb_l1_factors", [
        "chip_profit_ratio_20", "chip_profit_ratio_60", "chip_concentration_20",
        "chip_cost_90_width",
    ]),
    "flow": ("qdb_l2_factors", [
        "flow_net_amount", "flow_super_net", "flow_large_net", "flow_net_ratio",
    ]),
    "sentiment": ("qdb_market_sentiment", [
        "buy_pressure", "sell_pressure", "liquidity_score", "am_pm_trend",
        "volume_concentration",
    ]),
    "technical": ("qdb_technical_indicators", [
        "rsi_6", "rsi_14", "macd_dif", "macd_dea", "macd_hist",
        "vol_std_20", "vol_atr_14", "beta_20",
    ]),
}


def _read_symbol_parquet(ds: str, symbol: str) -> pd.DataFrame:
    """读 3_financial_data 下单标的平铺 parquet（小文件，直接读）。"""
    f = _quantdb_dir() / "3_financial_data" / ds / f"{symbol}.parquet"
    if not f.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read %s/%s failed: %s", ds, symbol, exc)
        return pd.DataFrame()


def _fin_records(df: pd.DataFrame, cols: dict[str, str], limit: int, yi: bool) -> list[dict]:
    """财务表 -> {period, items:{中文名: 亿元/原值}} 按报告期倒序。"""
    if df.empty:
        return []
    df = df.sort_values("m_timetag", ascending=False).head(limit)
    out: list[dict] = []
    for _, r in df.iterrows():
        items: dict[str, float | None] = {}
        for col, label in cols.items():
            v = _safe_f(r.get(col))
            if v is not None and yi:
                v = round(v / 1e8, 2)  # 元 -> 亿元
            items[label] = v
        out.append({"period": str(r.get("m_timetag") or "")[:8], "items": items})
    return out


@router.get("/dividends")
async def stock_dividends(
    symbol: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")
    df = _read_symbol_parquet("dividend_factors", sym)
    if df.empty:
        return {"success": True, "data": {"items": []}}
    df = df.sort_values("time", ascending=False).head(40)
    items = [
        {
            "date": str(r.get("time"))[:10],
            "interest": _safe_f(r.get("interest")),       # 每股派息(元)
            "stock_bonus": _safe_f(r.get("stockBonus")),  # 送股比例
            "stock_gift": _safe_f(r.get("stockGift")),    # 转增比例
            "gugai": _safe_f(r.get("gugai")),             # 股改? / 除权
            "dr": _safe_f(r.get("dr")),                   # 除权系数
        }
        for _, r in df.iterrows()
    ]
    return {"success": True, "data": {"items": items}}


@router.get("/tags")
async def stock_tags(
    symbol: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """个股命中标签 + 命中的组合预设。"""
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")

    import asyncio

    def _run() -> tuple[list[dict], list[dict]]:
        from backend.services.engine.data_platform import tag_rules

        return tag_rules.match_tags_for_symbol(sym), tag_rules.preset_matched(sym)

    try:
        tags, presets = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tag match %s failed: %s", sym, exc)
        tags, presets = [], []
    return {"success": True, "data": {"tags": tags, "presets": presets}}


@router.get("/tags/{tag_id}/stocks")
async def tag_stocks(
    tag_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """标签同类股票（按 sort_key 排序 TopN）。"""
    _ = current_user

    import asyncio

    def _run() -> list[dict]:
        from backend.services.engine.data_platform import tag_rules

        return tag_rules.stocks_for_tag(tag_id, limit=limit)

    try:
        items = await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("tag stocks %s failed: %s", tag_id, exc)
        items = []
    return {"success": True, "data": {"items": items}}


@router.get("/presets")
async def list_presets(current_user: dict = Depends(get_current_user)):
    _ = current_user
    return {"success": True, "data": {"presets": [
        {"id": p["id"], "name": p["name"], "logic": p["logic"], "tags": p["tags"]}
        for p in __import__("backend.services.engine.data_platform.tag_rules", fromlist=["PRESETS"]).PRESETS
    ]}}


@router.get("/signal-overlay")
async def stock_signal_overlay(
    symbol: str = Query(...),
    days: int = Query(250, ge=30, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """推理分数叠加：engine_signal_scores 按 model_version 分组返回。

    同表同口径与推理中心一致。返回 {dates, series:{model_version: [{fusion, side}]}}
    """
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")
    prefix = f"{sym.split('.')[1]}{sym.split('.')[0]}"  # 600519.SH -> SH600519

    from datetime import timedelta as _td

    async with get_session() as session:
        from sqlalchemy import text as _text

        start = _date.today() - _timedelta(days=days * 2)
        rows = (
            await session.execute(
                _text(
                    "SELECT trade_date, fusion_score, signal_side, model_version "
                    "FROM engine_signal_scores "
                    "WHERE tenant_id = :tid AND symbol = :s AND trade_date >= :start "
                    "ORDER BY trade_date"
                ),
                {"tid": "default", "s": prefix, "start": start},
            )
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        mv = str(r[3] or "default")
        grouped.setdefault(mv, []).append({
            "date": str(r[0])[:10],
            "fusion": float(r[1]) if r[1] is not None else None,
            "side": str(r[2] or "HOLD"),
        })
    # 只保留最近 days 个交易日
    for mv in grouped:
        grouped[mv] = grouped[mv][-days:]
    return {"success": True, "data": {"series": grouped}}


@router.get("/chart-backtest")
async def chart_backtest(
    symbol: str = Query(...),
    buy_expr: str = Query(..., description="买入条件，如 CROSSUP(MA(CLOSE,5),MA(CLOSE,20))"),
    sell_expr: str = Query("", description="卖出条件；空=持有到结束"),
    days: int = Query(500, ge=50, le=2000),
    current_user: dict = Depends(get_current_user),
):
    """图表内简单策略回测：表达式条件 -> 次日开盘撮合（防未来函数）。

    返回: 交易点列表 {date, side, price, pnl} + 净值/胜率/回撤/年化。
    """
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")

    from datetime import timedelta as _td

    def _load() -> pd.DataFrame:
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        hub = QuantDBDataHub.get_instance()
        end = _date.today()
        start = end - _td(days=int(days * 1.6))
        df = hub.fetch_daily_kline(sym, start, end)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values("trade_date").tail(days).reset_index(drop=True)

    def _run() -> dict:
        from backend.services.engine.data_platform import expr_engine as ee

        df = _load()
        if df.empty:
            raise ValueError("无 K 线数据")
        ohlcv = df.rename(columns={"trade_date": "date"})[["date", "open", "high", "low", "close", "volume"]]
        ctx = ee.build_context(ohlcv)
        buy_sig = ee.eval_bool_expr(ee.compile_expr(buy_expr), ctx)
        sell_sig = ee.eval_bool_expr(ee.compile_expr(sell_expr), ctx) if sell_expr.strip() else None

        n = len(ohlcv)
        trades: list[dict] = []
        position = 0.0          # 持仓股数（满仓=资金/价，用1股基线）
        cash = 100000.0
        entry_price = 0.0
        entry_date = ""
        buy_signaled = False

        # 次日开盘成交，防未来函数
        for i in range(1, n):
            date = ohlcv["date"].iloc[i]
            open_p = float(ohlcv["open"].iloc[i])
            if position == 0:
                if buy_sig.iloc[i - 1]:
                    shares = cash / open_p
                    cash -= shares * open_p * 1.00025
                    position = shares
                    entry_price = open_p
                    entry_date = date
                    trades.append({"date": str(date)[:10], "side": "BUY", "price": round(open_p, 2),
                                   "pnl": None, "signal_date": str(ohlcv["date"].iloc[i - 1])[:10]})
                    buy_signaled = True
            else:
                sell_now = sell_sig is not None and sell_sig.iloc[i - 1]
                # 若持有中且已无买入信号且超过20根，强制止盈/止损为下一个卖出信号
                if sell_now:
                    cash += position * open_p * (1 - 0.0013)  # 卖出费+印花税
                    pnl = (open_p - entry_price) / entry_price * 100
                    trades.append({"date": str(date)[:10], "side": "SELL", "price": round(open_p, 2),
                                   "pnl": round(pnl, 2), "signal_date": str(ohlcv["date"].iloc[i - 1])[:10]})
                    position = 0.0
                    entry_price = 0.0

        # 期末市值
        final_close = float(ohlcv["close"].iloc[-1])
        if position > 0:
            cash += position * final_close
            trades.append({"date": str(ohlcv["date"].iloc[-1])[:10], "side": "CLOSE",
                           "price": round(final_close, 2), "pnl": round((final_close - entry_price) / entry_price * 100, 2),
                           "signal_date": str(ohlcv["date"].iloc[-1])[:10]})

        total_ret = (cash - 100000.0) / 100000.0 * 100
        # 基准：买入持有
        base_ret = (float(ohlcv["close"].iloc[-1]) - float(ohlcv["open"].iloc[0])) / float(ohlcv["open"].iloc[0]) * 100

        sells = [t for t in trades if t["side"] == "SELL"]
        wins = [t for t in sells if (t["pnl"] or 0) > 0]
        # 净值曲线：按日模拟（重建持仓历史）
        hist_pos = 0.0
        hist_cash = 100000.0
        hist_entry = 0.0
        equity = []
        for i in range(n):
            if i > 0:
                if hist_pos == 0 and buy_sig.iloc[i - 1]:
                    hist_pos = hist_cash / float(ohlcv["open"].iloc[i])
                    hist_cash -= hist_pos * float(ohlcv["open"].iloc[i]) * 1.00025
                    hist_entry = float(ohlcv["open"].iloc[i])
                elif hist_pos > 0 and sell_sig is not None and sell_sig.iloc[i - 1]:
                    hist_cash += hist_pos * float(ohlcv["open"].iloc[i]) * (1 - 0.0013)
                    hist_pos = 0.0
            equity.append(hist_cash + hist_pos * float(ohlcv["close"].iloc[i]))
        peak = -1e18
        max_dd = 0.0
        for e in equity:
            peak = max(peak, e)
            if peak > 0:
                max_dd = max(max_dd, (peak - e) / peak * 100)

        return {
            "trades": trades,
            "total_return": round(total_ret, 2),
            "buy_hold_return": round(base_ret, 2),
            "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None,
            "trade_count": len(sells),
            "max_drawdown": round(max_dd, 2),
            "points": [
                {"date": str(ohlcv["date"].iloc[i]), "close": round(float(ohlcv["close"].iloc[i]), 2),
                 "equity": round(eq, 2)}
                for i, eq in enumerate(equity)
            ],
        }

    import asyncio

    try:
        result = await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("chart-backtest %s failed: %s", sym, exc)
        raise HTTPException(status_code=500, detail=f"回测失败: {exc}")
    return {"success": True, "data": result}


@router.get("/minute")
async def stock_minute_kline(
    symbol: str = Query(...),
    freq: str = Query("min5", description="min5 / min1"),
    days: int = Query(10, ge=1, le=30),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")

    def _run() -> pd.DataFrame:
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        subdir = "min1_kline" if freq == "min1" else "min5_kline"
        f = _quantdb_dir() / "1_kline_data" / subdir / f"{sym}.parquet"
        if not f.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("read %s/%s failed: %s", subdir, sym, exc)
            return pd.DataFrame()

    import asyncio

    df = await asyncio.to_thread(_run)
    if df.empty:
        return {"success": True, "data": {"items": [], "available": False}}
    df = df.sort_values("time").tail(days * 48)
    items = [
        {
            "date": str(r.get("time"))[:16].replace(" ", " "),
            "open": _safe_f(r.get("open")),
            "high": _safe_f(r.get("high")),
            "low": _safe_f(r.get("low")),
            "close": _safe_f(r.get("close")),
            "volume": _safe_f(r.get("volume")),
            "amount": _safe_f(r.get("amount")),
        }
        for _, r in df.iterrows()
    ]
    return {"success": True, "data": {"items": items, "available": True}}


@router.get("/financials")
async def stock_financials(
    symbol: str = Query(..., description="600519.SH"),
    limit: int = Query(8, ge=2, le=20),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")

    income = _read_symbol_parquet("income", sym)
    balance = _read_symbol_parquet("balance", sym)
    cashflow = _read_symbol_parquet("cashflow", sym)
    pershare = _read_symbol_parquet("pershare_index", sym)

    periods = (
        sorted(
            {str(v)[:8] for v in pershare.get("m_timetag", [])}
            | {str(v)[:8] for v in income.get("m_timetag", [])},
            reverse=True,
        )[:limit]
        if (not pershare.empty or not income.empty)
        else []
    )
    return {
        "success": True,
        "data": {
            "symbol": sym,
            "periods": periods,
            "income": _fin_records(income, _INCOME_COLS, limit, yi=True),
            "balance": _fin_records(balance, _BALANCE_COLS, limit, yi=True),
            "cashflow": _fin_records(cashflow, _CASHFLOW_COLS, limit, yi=True),
            "per_share": _fin_records(pershare, _PERSHARE_COLS, limit, yi=False),
        },
    }


@router.get("/series")
async def stock_series(
    symbol: str = Query(...),
    group: str = Query(..., description="valuation/margin/chip/flow/sentiment/technical/holders"),
    years: int = Query(3, ge=1, le=10),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    sym = symbol.upper().strip()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"非法代码 {sym}")

    # 股东户数: 平铺小文件, endDate 为报告期
    if group == "holders":
        hn = _read_symbol_parquet("holder_num", sym)
        if hn.empty:
            return {"success": True, "data": {"dates": [], "columns": {}}}
        hn = hn.sort_values("endDate")
        return {
            "success": True,
            "data": {
                "dates": [str(v)[:10] for v in hn["endDate"]],
                "columns": {"holder_num": [_safe_f(v) for v in hn["shareholder"]]},
            },
        }

    spec = _SERIES_GROUPS.get(group)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"未知时序组 {group}")
    view, cols = spec
    # dt 为整数 YYYYMMDD
    start_dt = (_date.today() - _timedelta(days=years * 366)).strftime("%Y%m%d")
    col_list = ", ".join(cols)
    sql = (
        f"SELECT dt, {col_list} FROM {view} "
        f"WHERE symbol = '{sym}' AND dt >= {start_dt} ORDER BY dt"
    )

    def _run() -> pd.DataFrame:
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        try:
            return QuantDBDataHub.get_instance().query(sql)
        except Exception as exc:  # noqa: BLE001
            logger.warning("series query %s %s failed: %s", group, sym, exc)
            return pd.DataFrame()

    import asyncio

    df = await asyncio.to_thread(_run)
    if df.empty:
        return {"success": True, "data": {"dates": [], "columns": {}}}
    dates = [str(v)[:10] for v in df["dt"]]
    columns = {c: [_safe_f(v) for v in df[c]] for c in cols if c in df.columns}
    return {"success": True, "data": {"dates": dates, "columns": columns}}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@router.get("/list")
async def list_stocks(
    market: str = Query("ALL", description="SH / SZ / BJ / ALL"),
    industry: str | None = Query(None, description="行业名称（rs_hyname）"),
    q: str | None = Query(None, description="代码/名称模糊检索"),
    only_st: bool = Query(False, description="仅 ST 股"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=10, le=300),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    df, trade_date = _load_universe()

    m = market.upper()
    if m in ("SH", "SZ", "BJ"):
        df = df[df["exchange"] == m]
    if industry:
        df = df[df["rs_hyname"] == industry]
    if q and q.strip():
        kw = q.strip()
        df = df[df["Symbol"].str.contains(kw) | df["Name"].astype(str).str.contains(kw)]
    if only_st and "STGP" in df.columns:
        df = df[pd.to_numeric(df["STGP"], errors="coerce").fillna(0) > 0]

    total = len(df)
    start = (page - 1) * page_size
    rows = df.iloc[start : start + page_size]

    def _item(r: pd.Series) -> dict[str, Any]:
        return {
            "symbol": r.get("Symbol"),
            "name": r.get("Name"),
            "board": r.get("board"),
            "industry": r.get("rs_hyname") or None,
            "close": _safe_f(r.get("close")),
            "pct_change": _safe_f(r.get("pct_change")),
            "total_mv": _safe_f(r.get("Zsz")),      # 亿元
            "float_mv": _safe_f(r.get("Ltsz")),     # 亿元
            "pe": _safe_f(r.get("DynaPE")),
            "pb": _safe_f(r.get("PB_MRQ")),
            "is_st": bool(pd.to_numeric(r.get("STGP"), errors="coerce").fillna(0) > 0)
            if "STGP" in r.index else False,
        }

    return {
        "success": True,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "trade_date": trade_date,
            "items": [_item(r) for _, r in rows.iterrows()],
        },
    }


@router.get("/industries")
async def list_industries(current_user: dict = Depends(get_current_user)):
    _ = current_user
    df, _ = _load_universe()
    names = sorted(x for x in df["rs_hyname"].dropna().astype(str).unique() if x.strip())
    return {"success": True, "data": {"industries": names}}


@router.get("/profile")
async def stock_profile(
    symbol: str = Query(..., description="600519.SH"),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    sym = symbol.upper().strip()
    df, trade_date = _load_universe()
    hits = df[df["Symbol"] == sym]
    if hits.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {sym}")
    r = hits.iloc[0]

    def _g(col: str) -> Any:
        v = r.get(col)
        if pd.isna(v):
            return None
        return v

    # 估值最新快照（pe_ttm/pb/ps/dividend_rate/float_mv 口径与列表的 DynaPE 互补）
    valuation: dict[str, Any] = {}
    dividend_yield: float | None = None
    d = _quantdb_dir()
    v_file = _latest_partition(d / "5_technical_derived" / "valuation")
    if v_file is not None:
        try:
            vdf = pd.read_parquet(v_file)
            sym_col = "symbol" if "symbol" in vdf.columns else "Symbol"
            vrow = vdf[vdf[sym_col] == sym]
            if not vrow.empty:
                vr = vrow.iloc[0]
                for col in ("pe_ttm", "pe_static", "pb", "ps_ttm",
                            "dividend_rate", "total_mv", "float_mv", "net_profit_ttm",
                            "revenue_ttm", "equity"):
                    valuation[col] = _safe_f(vr.get(col))
                dividend_yield = _norm_dividend(vr.get("dividend_rate"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("read valuation for %s failed: %s", sym, exc)

    _idx = _index_membership(sym)
    _concepts = _concepts_of(sym)

    profile = {
        "symbol": sym,
        "name": _g("Name"),
        "board": _g("board"),
        "industry": _g("rs_hyname"),
        "trade_date": trade_date,
        "close": _safe_f(r.get("close")),
        "pct_change": _safe_f(r.get("pct_change")),
        "total_mv": _safe_f(r.get("Zsz")),       # 亿元
        "float_mv": _safe_f(r.get("Ltsz")),      # 亿元
        "total_share": _safe_f(r.get("J_zgb")),  # 万股
        "free_float_share": _safe_f(r.get("FreeLtgb")),
        "pe_dynamic": _safe_f(r.get("DynaPE")),
        "pb": _safe_f(r.get("PB_MRQ")),
        "dividend_yield": dividend_yield,
        "beta": _safe_f(r.get("BetaValue")),
        "staff_num": _safe_f(r.get("StaffNum")),
        "main_business": _g("MainBusiness"),
        "ipo_price": _safe_f(r.get("IPO_Price")),
        "limit_up_price": _safe_f(r.get("ZTPrice")),
        "limit_down_price": _safe_f(r.get("DTPrice")),
        "flags": {
            "hs300": _flag(r.get("BelongHS300")),
            "marginable": _flag(r.get("RZRQ")),
            "sh_hk_connect": _flag(r.get("HSGT")),
            "is_st": _flag(r.get("STGP")),
            "is_hk_listed": _flag(r.get("IsHKGP")),
        },
        "valuation": valuation,
        "index_membership": _idx,
        "concepts": _concepts,
    }
    return {"success": True, "data": profile}
