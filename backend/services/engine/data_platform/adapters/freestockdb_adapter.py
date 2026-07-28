"""
free-stockdb 数据源适配器
========================

封装 free-stockdb HTTP API (http://host:7899)，提供：
- 日线 K 线（前复权/后复权/不复权）
- 申万行业 + 概念板块映射
- 复权因子
- 分钟 K 线（1/5/15/30/60 min）

free-stockdb 是开源本地量化数据引擎，数据以 LevelDB + Zstd 存储，
通过 HTTP API (cmd=get/keys/vals/len) 或 Python SDK (stockdb.pyd) 访问。

配置：环境变量 FREE_STOCKDB_HOST，默认 192.168.31.27:7899
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote

import pandas as pd
import requests

from backend.services.engine.data_platform.base import (
    DataUnavailable,
    InvalidFieldRequest,
    OfflineDataSourceAdapter,
)

logger = logging.getLogger(__name__)

_DEFAULT_HOST = os.getenv("FREE_STOCKDB_HOST", "192.168.31.27:7899")


def _api_url(cmd: str, t: str, limit: Optional[int] = None) -> str:
    base = f"http://{_DEFAULT_HOST}"
    params = f"cmd={cmd}&t={quote(t)}"
    if limit is not None:
        params += f"&limit={limit}"
    return f"{base}/?{params}"


def _api_get(cmd: str, t: str, limit: Optional[int] = None, timeout: int = 30) -> Any:
    url = _api_url(cmd, t, limit)
    resp = requests.get(url, timeout=timeout)
    if resp.status_code != 200:
        raise DataUnavailable(f"free-stockdb HTTP {resp.status_code}: {url}")
    return resp.json()


def _to_fsd_code(symbol: str) -> str:
    """SH600036 / 600036.SH -> 600519 纯数字格式（free-stockdb 使用纯数字代码）"""
    s = symbol.strip().upper()
    if "." in s:
        return s.split(".", 1)[0]
    if s.startswith("SH") or s.startswith("SZ") or s.startswith("BJ"):
        return s[2:]
    return s


def _from_fsd_code(code: str) -> str:
    """600519 -> SH600519 / 000001 -> SZ000001 (内部前缀格式)"""
    c = code.strip()
    if c.startswith("6") or c.startswith("9"):
        return f"SH{c}"
    if c.startswith("0") or c.startswith("3") or c.startswith("2"):
        return f"SZ{c}"
    if c.startswith("4") or c.startswith("8"):
        return f"BJ{c}"
    return c


class FreeStockDBAdapter(OfflineDataSourceAdapter):
    """free-stockdb HTTP API 适配器 — 开源本地量化数据引擎。"""

    name = "freestockdb"
    markets = ["A"]
    fields = {
        "daily_kline",
        "minute_kline",
        "adj_factor",
        "sector",
        "stock_list",
    }

    def fetch_daily(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        fsd_code = _to_fsd_code(symbol)
        t = f"日k:{fsd_code}:*"
        try:
            raw = _api_get("vals", t, limit=8000)
        except Exception as exc:
            raise DataUnavailable(f"free-stockdb 日k failed for {symbol}: {exc}") from exc

        if not raw:
            raise DataUnavailable(f"free-stockdb empty for {symbol}")

        df = pd.DataFrame(raw)
        df["trade_date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d").dt.date
        df = df[df["trade_date"] >= start]
        if end:
            df = df[df["trade_date"] <= end]

        if adjust == "qfq":
            df = self._apply_qfq(df, fsd_code)
        elif adjust == "hfq":
            df = self._apply_hfq(df, fsd_code)

        df["symbol"] = _from_fsd_code(fsd_code)
        df["adj_factor"] = df.get("cum", 1.0)
        df["source"] = self.name
        return df

    def fetch_field(
        self,
        field: str,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        if field == "adj_factor":
            return self._fetch_adj_factor(_to_fsd_code(symbol))
        if field == "sector":
            return self._fetch_sectors()
        if field == "stock_list":
            return self._fetch_stock_list()
        if field == "minute_kline":
            freq = kwargs.get("frequency", "1m")
            return self._fetch_minute(symbol, freq, start, end)
        raise InvalidFieldRequest(f"free-stockdb: field={field} not implemented")

    def fetch_meta(self, market: str) -> pd.DataFrame:
        return self._fetch_stock_list()

    # ---- 复权因子 ----
    def _fetch_adj_factor(self, fsd_code: str) -> pd.DataFrame:
        t = f"复权:{fsd_code}:*"
        raw = _api_get("keys", t, limit=500)
        if not raw:
            raise DataUnavailable(f"free-stockdb adj_factor empty for {fsd_code}")

        records = []
        for key in raw:
            parts = key.split(":")
            if len(parts) >= 3:
                dt = parts[2]
                data = _api_get("get", key)
                if data and isinstance(data, dict):
                    records.append({
                        "date": dt,
                        "div": data.get("div", 0),
                        "give": data.get("give", 0),
                        "trans": data.get("trans", 0),
                        "mult": data.get("mult", 1),
                        "cum": data.get("cum", 1),
                    })

        df = pd.DataFrame(records)
        df["trade_date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce").dt.date
        df["symbol"] = _from_fsd_code(fsd_code)
        df["source"] = self.name
        return df

    # ---- 前复权 / 后复权 ----
    def _apply_qfq(self, df: pd.DataFrame, fsd_code: str) -> pd.DataFrame:
        """前复权：用 cum 因子调整 OHLCV。"""
        adj_df = self._fetch_adj_factor(fsd_code)
        if adj_df.empty:
            return df
        # 最新 cum 作为基准
        latest_cum = adj_df["cum"].max()
        for col in ("open", "high", "low", "close", "pre_close"):
            if col in df.columns:
                factor = df["trade_date"].map(
                    lambda d: self._find_cum(adj_df, d, latest_cum)
                )
                df[col] = df[col] * factor
        if "volume" in df.columns:
            df["volume"] = df["volume"] * df["trade_date"].map(
                lambda d: self._find_cum(adj_df, d, latest_cum)
            )
        return df

    def _apply_hfq(self, df: pd.DataFrame, fsd_code: str) -> pd.DataFrame:
        """后复权：用 cum 因子直接乘。"""
        adj_df = self._fetch_adj_factor(fsd_code)
        if adj_df.empty:
            return df
        for col in ("open", "high", "low", "close", "pre_close"):
            if col in df.columns:
                factor = df["trade_date"].map(
                    lambda d: self._find_cum_raw(adj_df, d)
                )
                df[col] = df[col] * factor
        return df

    def _find_cum(self, adj_df: pd.DataFrame, d: date, latest_cum: float) -> float:
        """前复权因子 = latest_cum / cum_on_date。"""
        match = adj_df[adj_df["trade_date"] <= d]
        if match.empty:
            return latest_cum
        cum = match.iloc[-1]["cum"]
        return latest_cum / cum if cum > 0 else 1.0

    def _find_cum_raw(self, adj_df: pd.DataFrame, d: date) -> float:
        """后复权因子 = cum_on_date。"""
        match = adj_df[adj_df["trade_date"] <= d]
        if match.empty:
            return 1.0
        return match.iloc[-1]["cum"]

    # ---- 板块 ----
    def _fetch_sectors(self) -> pd.DataFrame:
        t = "板块:*"
        raw = _api_get("vals", t, limit=5000)
        if not raw:
            raise DataUnavailable("free-stockdb sectors empty")
        df = pd.DataFrame(raw)
        df["source"] = self.name
        return df

    # ---- 股票列表（从日线数据推断） ----
    def _fetch_stock_list(self) -> pd.DataFrame:
        t = "日k:*:*"
        raw = _api_get("keys", t, limit=10)
        if not raw:
            raise DataUnavailable("free-stockdb stock_list empty")
        # 从日线 key 中提取唯一代码
        codes = set()
        for key in raw:
            parts = key.split(":")
            if len(parts) >= 2:
                codes.add(parts[1])
        # 扩展扫描
        t2 = "日k:*"
        raw2 = _api_get("vals", t2, limit=20)
        if raw2:
            for item in raw2:
                if "code" in item:
                    codes.add(item["code"])
                if "name" in item:
                    codes.add(item.get("code", ""))

        df = pd.DataFrame([{"symbol": _from_fsd_code(c), "code": c} for c in sorted(codes)])
        df["market"] = "A"
        df["source"] = self.name
        return df

    # ---- 分钟线 ----
    def _fetch_minute(
        self,
        symbol: str,
        frequency: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> pd.DataFrame:
        fsd_code = _to_fsd_code(symbol)
        t = f"分钟k:{fsd_code}:*"
        raw = _api_get("vals", t, limit=50000)
        if not raw:
            raise DataUnavailable(f"free-stockdb 分钟k empty for {symbol}")

        df = pd.DataFrame(raw)
        if "date" in df.columns:
            df["trade_date"] = pd.to_datetime(
                df["date"].astype(str), format="%Y%m%d%H%M%S", errors="coerce"
            ).dt.date
        if start:
            df = df[df["trade_date"] >= start]
        if end:
            df = df[df["trade_date"] <= end]

        df["symbol"] = _from_fsd_code(fsd_code)
        df["source"] = self.name
        return df


def register() -> bool:
    """运行时按需调用；返回是否成功注册。"""
    try:
        resp = requests.get(f"http://{_DEFAULT_HOST}/?cmd=len&t=日k:600519:*", timeout=5)
        if resp.status_code != 200:
            logger.info("free-stockdb 不可达，跳过注册")
            return False
    except Exception:
        logger.info("free-stockdb 连接失败，跳过 FreeStockDBAdapter 注册")
        return False

    from backend.services.engine.data_platform.registry import get_registry
    get_registry().register(FreeStockDBAdapter, name=FreeStockDBAdapter.name)
    logger.info("FreeStockDBAdapter 注册成功 (host=%s)", _DEFAULT_HOST)
    return True
