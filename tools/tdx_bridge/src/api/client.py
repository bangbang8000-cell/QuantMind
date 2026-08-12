import asyncio
import logging
from typing import List, Optional

from ..channel.channel_manager import ChannelManager
from ..channel.file_sync import FileSyncChannel
from ..channel.http_client import HttpBridgeClient, HttpBridgeError
from ..core.trade_plan import Order, TradePlan
from ..core.types import Side

log = logging.getLogger(__name__)


class TradingClient:
    """QuandMind 策略调用的高层交易 API. 同步接口, 内部用 asyncio 驱动双通道."""

    def __init__(self, http_client: HttpBridgeClient,
                 file_sync: FileSyncChannel,
                 mode: str = "auto",
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 health_interval: float = 10.0):
        self.channels = ChannelManager(http_client, file_sync, mode,
                                       max_retries, retry_delay, health_interval)
        self._loop = None

    def _run(self, coro):
        """在事件循环中运行协程. 若当前线程无循环则临时创建."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # 已在异步上下文: 由调用方 await
            return coro
        try:
            return asyncio.run(coro)
        except RuntimeError:
            # 已有 loop (如 Jupyter), 用 run_coroutine_threadsafe
            new_loop = asyncio.new_event_loop()
            return new_loop.run_until_complete(coro)

    # ---- 计划提交 ----

    def submit_plan(self, orders: List[Order], account: str = "",
                    account_type: str = "stock", source: str = "",
                    timeout_seconds: int = 300) -> dict:
        plan = TradePlan(plan_id=self._new_plan_id(), orders=orders,
                         account=account, account_type=account_type,
                         source=source, timeout_seconds=timeout_seconds)
        return self._run(self.channels.send_plan(plan))

    def buy(self, stock_code: str, volume: int, price: Optional[float] = None,
            price_type: int = 0, account: str = "", account_type: str = "stock",
            stop_loss_pct: Optional[float] = None,
            take_profit_pct: Optional[float] = None,
            trailing_stop_pct: Optional[float] = None) -> dict:
        order = Order(stock_code=stock_code, side=Side.BUY.value, volume=volume,
                      price=price, price_type=price_type,
                      order_type="limit" if price else "market",
                      stop_loss_pct=stop_loss_pct,
                      take_profit_pct=take_profit_pct,
                      trailing_stop_pct=trailing_stop_pct)
        return self.submit_plan([order], account, account_type)

    def sell(self, stock_code: str, volume: int, price: Optional[float] = None,
             price_type: int = 1, account: str = "", account_type: str = "stock") -> dict:
        order = Order(stock_code=stock_code, side=Side.SELL.value, volume=volume,
                      price=price, price_type=price_type,
                      order_type="limit" if price else "market")
        return self.submit_plan([order], account, account_type)

    # ---- 账户查询 ----

    def query_account(self, account: str = "", account_type: str = "stock") -> dict:
        return self._run(self._query_account_async(account, account_type))

    async def _query_account_async(self, account: str, account_type: str) -> dict:
        try:
            return self.channels.http.query_account(account, account_type)
        except HttpBridgeError as e:
            if e.retryable:
                return self.channels.http.query_account(account, account_type)
            raise

    def query_orders(self, account: str = "", account_type: str = "stock",
                     stock_code: str = "") -> dict:
        return self._run(self._query_orders_async(account, account_type, stock_code))

    async def _query_orders_async(self, account: str, account_type: str, stock_code: str) -> dict:
        return self.channels.http.query_orders(account, account_type, stock_code)

    def cancel_order(self, order_id: str, stock_code: str = "",
                     account: str = "", account_type: str = "stock") -> dict:
        return self._run(self._cancel_async(order_id, stock_code, account, account_type))

    async def _cancel_async(self, order_id: str, stock_code: str,
                            account: str, account_type: str) -> dict:
        return self.channels.http.cancel_order(account, account_type, stock_code, order_id)

    # ---- 止损配置 ----

    def configure_sltp(self, items: List[dict], account: str = "",
                       account_type: str = "stock") -> dict:
        return self._run(self._configure_sltp_async(items, account, account_type))

    async def _configure_sltp_async(self, items, account, account_type) -> dict:
        return self.channels.http.configure_sltp(items)

    def sltp_state(self) -> dict:
        return self._run(self._sltp_state_async())

    async def _sltp_state_async(self) -> dict:
        return self.channels.http.sltp_state()

    # ---- 工具 ----

    @staticmethod
    def _new_plan_id() -> str:
        import time
        return f"plan_{int(time.time())}_{id(object()) % 10000}"


def build_client(config, mode: str = "auto") -> TradingClient:
    """从 Config 构建客户端. 供策略代码使用."""
    http = HttpBridgeClient(
        config.get("channels.http.host", ""),
        config.get("channels.http.port", 8550),
        config.token(),
        timeout=config.get("channels.http.timeout_seconds", 30.0))
    fs = FileSyncChannel(config.get("channels.file_sync.shared_dir", ""))
    return TradingClient(http, fs, mode=mode)
