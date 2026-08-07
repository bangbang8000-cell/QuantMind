"""
eltdx 数据源 — 直接连接通达信行情服务器获取实时数据

eltdx 通过逆向工程还原了通达信 TDX 行情协议，
无需 Windows 客户端、无需通达信登录，纯 Python 实现。

安装: pip install eltdx
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .data_source import DataSourceAdapter

logger = logging.getLogger(__name__)

# 同步 eltdx 需要在线程池中执行
from eltdx import TdxClient, KlinePeriod
from eltdx.protocol.unit import is_a_share_entry


class EltdxDataSource(DataSourceAdapter):
    """通达信 eltdx 数据源 — 直接连接 TDX 行情服务器"""

    # eltdx 支持的 K 线周期映射
    _KLINE_PERIOD_MAP: dict[str, str] = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "60m",
        "1d": "day",
        "1w": "week",
        "1mo": "month",
        "1mon": "month",
        "quarter": "quarter",
        "year": "year",
    }

    def __init__(
        self,
        *,
        hosts: list[str] | None = None,
        pool_size: int = 2,
        timeout: float = 8.0,
        probe_hosts: bool = True,
    ):
        self._hosts = hosts
        self._pool_size = pool_size
        self._timeout = timeout
        self._probe_hosts = probe_hosts
        self._client: TdxClient | None = None
        self._lock = asyncio.Lock()

    def _get_client(self) -> TdxClient:
        """懒初始化 eltdx 客户端（线程安全）"""
        if self._client is None:
            kwargs = {
                "pool_size": self._pool_size,
                "timeout": self._timeout,
                "probe_hosts": self._probe_hosts,
            }
            if self._hosts:
                kwargs["hosts"] = self._hosts
            self._client = TdxClient(**kwargs)
        return self._client

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        将 QuantMind 内部 symbol 转为 eltdx 格式 (带市场前缀)

        000001  → sz000001
        sh600000 → sh600000  (已是正确格式)
        600000.SH → sh600000
        """
        s = symbol.strip().lower()

        # 已是 sh/sz/bj 前缀格式
        if s.startswith(("sh", "sz", "bj")):
            return s

        # {code}.{market} 格式
        if "." in s:
            code, market = s.split(".", 1)
            market = market.upper()
            prefix = "sh" if market == "SH" else ("sz" if market == "SZ" else "bj")
            return f"{prefix}{code}"

        # 纯数字代码，按首位推断市场
        if s.startswith("6") or s.startswith("9"):
            return f"sh{s}"
        elif s.startswith(("0", "2", "3")):
            return f"sz{s}"
        elif s.startswith(("4", "8")):
            return f"bj{s}"
        else:
            return f"sh{s}"

    # ------------------------------------------------------------------ #
    #  实时行情
    # ------------------------------------------------------------------ #

    async def fetch_quote(self, symbol: str) -> dict[str, Any] | None:
        """获取实时行情快照"""
        try:
            client = self._get_client()
            eltdx_symbol = self._normalize_symbol(symbol)

            quotes = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_quote(eltdx_symbol)
            )

            if not quotes:
                logger.warning(f"[eltdx] No quote returned for {eltdx_symbol}")
                return None

            q = quotes[0]

            # Quote.rate 是涨跌幅百分比（通达信协议直接返回）
            rate = q.rate if q.rate is not None else 0.0
            current_price = q.last_price
            pre_close = q.last_close_price

            change = current_price - pre_close if pre_close else 0.0
            change_percent = (change / pre_close * 100) if pre_close > 0 else 0.0

            # 成交量：eltdx total_hand 单位是"手"，转为"股"
            volume = q.total_hand * 100

            result = {
                "symbol": symbol,
                "timestamp": q.server_time if q.server_time else datetime.now(timezone.utc),
                "current_price": current_price,
                "open_price": q.open_price,
                "high_price": q.high_price,
                "low_price": q.low_price,
                "pre_close": pre_close,
                "volume": volume,
                "amount": q.amount,
                "change": round(change, 4),
                "change_percent": round(change_percent, 2) if change_percent else round(rate, 2),
                "data_source": "eltdx",
            }

            # Bid 1-5
            buy_levels = sorted(
                [lv for lv in q.buy_levels if lv.buy],
                key=lambda lv: lv.price,
                reverse=True,
            )[:5]
            for i in range(5):
                if i < len(buy_levels):
                    result[f"bid{i+1}_price"] = buy_levels[i].price
                    result[f"bid{i+1}_volume"] = buy_levels[i].number * 100
                else:
                    result[f"bid{i+1}_price"] = 0.0
                    result[f"bid{i+1}_volume"] = 0

            # Ask 1-5
            sell_levels = sorted(
                [lv for lv in q.sell_levels if not lv.buy],
                key=lambda lv: lv.price,
            )[:5]
            for i in range(5):
                if i < len(sell_levels):
                    result[f"ask{i+1}_price"] = sell_levels[i].price
                    result[f"ask{i+1}_volume"] = sell_levels[i].number * 100
                else:
                    result[f"ask{i+1}_price"] = 0.0
                    result[f"ask{i+1}_volume"] = 0

            return result

        except Exception as e:
            logger.error(f"[eltdx] Error fetching quote for {symbol}: {e}")
            return None

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
        try:
            client = self._get_client()
            eltdx_symbol = self._normalize_symbol(symbol)
            period = self._KLINE_PERIOD_MAP.get(interval)

            if not period:
                logger.warning(f"[eltdx] Unsupported interval: {interval}")
                return []

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_kline(period, eltdx_symbol, count=limit),
            )

            if not response or not response.items:
                return []

            output = []
            prev_close = None
            for item in response.items:
                ts = item.time
                if start_time and ts < start_time:
                    continue
                if end_time and ts > end_time:
                    continue

                # last_close_price 可能为 None，用前一根的 close 做 prev_close
                close_price = item.close_price
                baseline = item.last_close_price if item.last_close_price else prev_close
                change = (close_price - baseline) if baseline else None
                change_percent = (change / baseline * 100) if baseline and change is not None else None

                output.append({
                    "symbol": symbol,
                    "interval": interval,
                    "timestamp": ts,
                    "open_price": item.open_price,
                    "high_price": item.high_price,
                    "low_price": item.low_price,
                    "close_price": close_price,
                    "volume": item.volume * 100,  # 手 → 股
                    "amount": item.amount,
                    "change": round(change, 4) if change is not None else None,
                    "change_percent": round(change_percent, 4) if change_percent is not None else None,
                    "turnover_rate": None,
                    "data_source": "eltdx",
                })
                prev_close = close_price

            output.sort(key=lambda x: x["timestamp"])
            return output[-limit:]

        except Exception as e:
            logger.error(f"[eltdx] Error fetching kline for {symbol} {interval}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  标的列表
    # ------------------------------------------------------------------ #

    async def fetch_symbols(self, market: str | None = None) -> list[dict[str, Any]]:
        """获取 A 股交易标的列表"""
        try:
            client = self._get_client()
            exchanges = []

            if market:
                m = market.lower()
                if m in ("sh", "sz", "bj"):
                    exchanges.append(m)
                else:
                    exchanges = ["sh", "sz", "bj"]
            else:
                exchanges = ["sh", "sz", "bj"]

            result = []
            for ex in exchanges:
                items = await asyncio.get_event_loop().run_in_executor(
                    None, lambda e=ex: client.get_codes_all(e)
                )
                for item in items:
                    if is_a_share_entry(item.full_code):
                        result.append({
                            "symbol": item.full_code,
                            "code": item.code,
                            "market": ex.upper(),
                            "name": item.name,
                        })

            logger.info(f"[eltdx] Fetched {len(result)} A-share symbols")
            return result

        except Exception as e:
            logger.error(f"[eltdx] Error fetching symbols: {e}")
            return []
