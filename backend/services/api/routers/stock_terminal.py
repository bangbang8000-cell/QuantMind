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
