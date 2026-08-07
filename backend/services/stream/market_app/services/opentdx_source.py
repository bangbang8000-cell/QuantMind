"""
opentdx 数据源 — 直接连接通达信行情服务器获取实时数据

项目: https://github.com/LisonEvf/opentdx

与 eltdx 的差异:
- opentdx 使用 MAC 协议，自动选服，连接更稳定
- opentdx vol 单位已是"股"，eltdx 是"手"需 ×100
- opentdx 使用 opentdx.tdxClient.TdxClient，上下文管理器自动管理连接
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .data_source import DataSourceAdapter

logger = logging.getLogger(__name__)


class OpentdxDataSource(DataSourceAdapter):
    """通达信 opentdx 数据源 — 通过 MAC 协议连接 TDX 行情服务器"""

    _KLINE_PERIOD_MAP: dict[str, Any] = {}

    def __init__(self):
        self._client = None
        self._lock = asyncio.Lock()

    def _get_market_and_code(self, symbol: str) -> tuple:
        """
        将 QuantMind symbol 转为 (MARKET, code) 元组

        SH600000 → (MARKET.SH, '600000')
        SZ000001 → (MARKET.SZ, '000001')
        BJ430047 → (MARKET.BJ, '430047')
        600000.SH → (MARKET.SH, '600000')
        """
        from opentdx.const import MARKET

        s = symbol.strip().upper()

        # 前缀格式: SH600000
        if s.startswith(("SH", "SZ", "BJ")):
            market_str = s[:2]
            code = s[2:]
            market = MARKET.SH if market_str == "SH" else (MARKET.SZ if market_str == "SZ" else MARKET.BJ)
            return market, code

        # 后缀格式: 600000.SH
        if "." in s:
            code, market_str = s.split(".", 1)
            market = MARKET.SH if market_str == "SH" else (MARKET.SZ if market_str == "SZ" else MARKET.BJ)
            return market, code

        # 纯数字，按首位推断
        if s.startswith(("6", "9")):
            return MARKET.SH, s
        elif s.startswith(("0", "2", "3")):
            return MARKET.SZ, s
        elif s.startswith(("4", "8")):
            return MARKET.BJ, s

        return MARKET.SH, s

    def _get_client(self):
        """懒初始化 opentdx 客户端"""
        if self._client is None:
            from opentdx.tdxClient import TdxClient
            self._client = TdxClient()
        return self._client

    # ------------------------------------------------------------------ #
    #  实时行情
    # ------------------------------------------------------------------ #

    async def fetch_quote(self, symbol: str) -> dict[str, Any] | None:
        """获取实时行情快照"""
        quotes = await self.fetch_quotes([symbol])
        return quotes[0] if quotes else None

    async def fetch_quotes(self, symbols: list[str]) -> list[dict[str, Any]]:
        """批量获取实时行情快照"""
        if not symbols:
            return []

        try:
            client = self._get_client()
            code_list = [self._get_market_and_code(s) for s in symbols]

            # opentdx 是同步 API，需在线程池中执行
            loop = asyncio.get_event_loop()
            quotes = await loop.run_in_executor(
                None,
                lambda: client.stock_quotes(code_list),
            )

            results = []
            now_ts = datetime.now(timezone.utc)

            for q in quotes:
                code = q.get("code", "")
                market_obj = q.get("market")

                # 还原原始 symbol 格式
                if market_obj is not None:
                    market_str = "SH" if market_obj.value == 1 else ("SZ" if market_obj.value == 0 else "BJ")
                else:
                    market_str = "SH" if code.startswith(("6", "9")) else "SZ"
                symbol_out = f"{market_str}{code}"

                pre_close = q.get("pre_close") or 0.0
                close = q.get("close") or 0.0
                change = close - pre_close if pre_close > 0 else 0.0
                change_pct = (change / pre_close * 100) if pre_close > 0 else 0.0

                results.append({
                    "symbol": symbol_out,
                    "timestamp": now_ts,
                    "current_price": close,
                    "open_price": q.get("open"),
                    "high_price": q.get("high"),
                    "low_price": q.get("low"),
                    "pre_close": pre_close,
                    "volume": q.get("vol", 0),  # opentdx 单位已是"股"
                    "amount": q.get("amount"),
                    "change": round(change, 4),
                    "change_percent": round(change_pct, 2),
                    "data_source": "opentdx",
                    "is_stale": False,
                })

            return results

        except Exception as e:
            logger.error(f"[opentdx] fetch_quotes failed: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  K 线
    # ------------------------------------------------------------------ #

    async def fetch_kline(
        self,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取 K 线历史"""
        from opentdx.const import ADJUST, PERIOD

        period_map = {
            "1m": PERIOD.MIN_1,
            "5m": PERIOD.MIN_5,
            "15m": PERIOD.MIN_15,
            "30m": PERIOD.MIN_30,
            "1h": PERIOD.MIN_60,
            "1d": PERIOD.DAILY,
            "1w": PERIOD.WEEKLY,
            "1mo": PERIOD.MONTHLY,
            "1mon": PERIOD.MONTHLY,
        }

        period = period_map.get(interval.lower())
        if period is None:
            logger.warning(f"[opentdx] Unsupported interval: {interval}")
            return []

        try:
            client = self._get_client()
            market, code = self._get_market_and_code(symbol)

            loop = asyncio.get_event_loop()
            bars = await loop.run_in_executor(
                None,
                lambda: client.stock_kline(market, code, period, count=limit),
            )

            if not bars:
                return []

            output = []
            # opentdx K 线按日期倒序（最新在前），需要正序处理 preclose
            bars_sorted = sorted(bars, key=lambda b: b["datetime"])
            prev_close = None

            for bar in bars_sorted:
                ts = bar["datetime"]
                if hasattr(ts, "date") and start_time:
                    if ts < start_time:
                        continue
                if hasattr(ts, "date") and end_time:
                    if ts > end_time:
                        pass  # 保留全部，最后 truncate

                close_price = bar.get("close")
                baseline = prev_close
                change = (close_price - baseline) if baseline else None
                change_pct = (change / baseline * 100) if baseline and change is not None else None

                output.append({
                    "symbol": symbol,
                    "interval": interval,
                    "timestamp": ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
                    "open_price": bar.get("open"),
                    "high_price": bar.get("high"),
                    "low_price": bar.get("low"),
                    "close_price": close_price,
                    "volume": bar.get("vol"),  # opentdx 单位已是"股"
                    "amount": bar.get("amount"),
                    "change": round(change, 4) if change is not None else None,
                    "change_percent": round(change_pct, 4) if change_pct is not None else None,
                    "turnover_rate": bar.get("turnover"),
                    "data_source": "opentdx",
                })
                prev_close = close_price

            # 返回最近 limit 条
            return output[-limit:]

        except Exception as e:
            logger.error(f"[opentdx] Error fetching kline for {symbol} {interval}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  标的列表
    # ------------------------------------------------------------------ #

    async def fetch_symbols(self, market: str | None = None) -> list[dict[str, Any]]:
        """获取 A 股交易标的列表"""
        from opentdx.const import MARKET

        try:
            client = self._get_client()
            markets = []

            if market:
                m = market.lower()
                if m == "sh":
                    markets.append(MARKET.SH)
                elif m == "sz":
                    markets.append(MARKET.SZ)
                elif m == "bj":
                    markets.append(MARKET.BJ)
                else:
                    markets = [MARKET.SH, MARKET.SZ, MARKET.BJ]
            else:
                markets = [MARKET.SH, MARKET.SZ, MARKET.BJ]

            result = []
            loop = asyncio.get_event_loop()

            for mkt in markets:
                items = await loop.run_in_executor(
                    None,
                    lambda m=mkt: client.stock_list(m),
                )
                for item in items:
                    market_str = "SH" if mkt.value == 1 else ("SZ" if mkt.value == 0 else "BJ")
                    result.append({
                        "symbol": f"{market_str}{item['code']}",
                        "code": item["code"],
                        "market": market_str,
                        "name": item.get("name", ""),
                    })

            logger.info(f"[opentdx] Fetched {len(result)} A-share symbols")
            return result

        except Exception as e:
            logger.error(f"[opentdx] Error fetching symbols: {e}")
            return []
