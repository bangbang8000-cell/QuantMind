"""
Broker Client - 抽象 Broker 接口，支持模拟和真实交易

提供统一的下单接口，隔离 trading_engine 与具体 Broker 实现。
"""

import abc
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.services.trade.services.simulation_manager import (
        SimulationAccountManager,
    )

logger = logging.getLogger(__name__)


class BrokerResult:
    """Broker 执行结果"""

    def __init__(
        self,
        success: bool,
        filled_price: float = 0.0,
        filled_quantity: float = 0.0,
        commission: float = 0.0,
        exchange_order_id: str = "",
        message: str = "",
    ):
        self.success = success
        self.filled_price = filled_price
        self.filled_quantity = filled_quantity
        self.commission = commission
        self.exchange_order_id = exchange_order_id
        self.message = message




@dataclass
class MarketQuoteSnapshot:
    price: float
    limit_up: bool = False
    limit_down: bool = False
    suspended: bool = False

class BaseBroker(abc.ABC):
    """Broker 抽象基类"""

    @abc.abstractmethod
    async def place_order(
        self,
        user_id: int,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: float | None = None,
        tenant_id: str = "default",
    ) -> BrokerResult:
        """下单"""
        ...

    @abc.abstractmethod
    async def query_account(
        self, user_id: str, tenant_id: str = "default"
    ) -> dict[str, Any]:
        """查询账户信息"""
        ...

    @abc.abstractmethod
    async def cancel_order(self, exchange_order_id: str, **kwargs) -> bool:
        """撤单"""
        ...

    @abc.abstractmethod
    async def query_quote(self, symbol: str) -> dict[str, Any]:
        """查询行情"""
        ...


class PaperTradingBroker(BaseBroker):
    """
    Paper Trading Broker with internal state management via Redis.
    行情来自本地 quantdb parquet（LocalMarketData）。
    """

    COMMISSION_RATE = 0.0003  # 0.03% commission

    def __init__(
        self,
        simulation_manager: "SimulationAccountManager",
        market_url: str = "http://stream-gateway:8003",
    ):
        self.simulation_manager = simulation_manager
        self.market_url = market_url

    async def _get_market_snapshot(self, symbol: str) -> MarketQuoteSnapshot:
        """从本地 quantdb parquet 取行情快照。

        取不到行情时 price=0 且 suspended=True，由 place_order 拒单——不编造价格。
        """
        from backend.services.trade.simulation.services.local_market_data import (
            get_local_market_data,
        )

        market = get_local_market_data()
        trade_date = market.latest_trade_date()
        if trade_date is None:
            logger.error("[PaperTrading] 本地行情数据不可用，无法为 %s 定价", symbol)
            return MarketQuoteSnapshot(price=0.0, suspended=True)

        bar = market.get_bar(symbol, trade_date)
        if bar is None or bar.close <= 0:
            logger.warning(
                "[PaperTrading] 本地行情缺少 %s @ %s，按停牌处理", symbol, trade_date
            )
            return MarketQuoteSnapshot(price=0.0, suspended=True)

        return MarketQuoteSnapshot(
            price=bar.close,
            limit_up=math.isfinite(bar.limit_up) and bar.close >= bar.limit_up,
            limit_down=bar.limit_down > 0 and bar.close <= bar.limit_down,
            suspended=bar.suspended,
        )

    async def _get_market_price(self, symbol: str) -> float:
        """Fetch real-time price from Market Data Service with L2 DB fallback"""
        return (await self._get_market_snapshot(symbol)).price

    async def place_order(
        self,
        user_id: int,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: float | None = None,
        tenant_id: str = "default",
    ) -> BrokerResult:
        snapshot = await self._get_market_snapshot(symbol)
        market_price = snapshot.price
        exec_price = 0.0
        slippage = random.uniform(-0.0005, 0.0005)

        normalized_side = str(side or "").strip().lower()
        if snapshot.suspended:
            return BrokerResult(success=False, message="Security is suspended, cannot trade")
        if normalized_side == "buy" and snapshot.limit_up:
            return BrokerResult(success=False, message="Limit-up locked, buy order cannot be filled")
        if normalized_side == "sell" and snapshot.limit_down:
            return BrokerResult(success=False, message="Limit-down locked, sell order cannot be filled")

        if order_type == "market":
            exec_price = market_price * (1 + slippage)
        elif order_type == "limit":
            if not price:
                return BrokerResult(success=False, message="Limit price required")
            if side == "buy":
                if price >= market_price:
                    exec_price = market_price
                else:
                    return BrokerResult(
                        success=False, message="Limit price not reached"
                    )
            else:
                if price <= market_price:
                    exec_price = market_price
                else:
                    return BrokerResult(
                        success=False, message="Limit price not reached"
                    )
        else:
            return BrokerResult(
                success=False, message=f"Unsupported order type: {order_type}"
            )

        exec_price = round(exec_price, 4)
        commission = round(quantity * exec_price * self.COMMISSION_RATE, 2)
        cost_or_proceeds = quantity * exec_price

        if side == "buy":
            delta_cash = -(cost_or_proceeds + commission)
            delta_volume = quantity
        else:
            delta_cash = cost_or_proceeds - commission
            delta_volume = -quantity

        # Update State
        update_result = await self.simulation_manager.update_balance(
            user_id=user_id,
            symbol=symbol,
            delta_cash=delta_cash,
            delta_volume=delta_volume,
            price=exec_price,
            tenant_id=tenant_id,
        )

        if not update_result.get("success"):
            reason = update_result.get("reason", "BALANCE_UPDATE_FAILED")
            if reason == "INSUFFICIENT_CASH":
                message = "Insufficient cash for buy order"
            elif reason == "INSUFFICIENT_HOLDINGS":
                message = "Insufficient holdings for sell order"
            else:
                message = f"Balance update failed: {reason}"
            return BrokerResult(success=False, message=message)

        exchange_id = f"SIM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
        logger.info(
            f"[PaperTrading] User {user_id} filled {side} {quantity} {symbol} @ {exec_price}"
        )

        return BrokerResult(
            success=True,
            filled_price=exec_price,
            filled_quantity=quantity,
            commission=commission,
            exchange_order_id=exchange_id,
            message="Paper Trading Fill",
        )

    async def query_account(
        self, user_id: str, tenant_id: str = "default"
    ) -> dict[str, Any]:
        """Query account state from Redis"""
        account = await self.simulation_manager.get_account(
            int(user_id), tenant_id=tenant_id
        )
        if not account:
            return {}
        return account

    async def cancel_order(self, exchange_order_id: str) -> bool:
        return True

    async def query_quote(self, symbol: str) -> dict[str, Any]:
        """Query quote from market service"""
        price = await self._get_market_price(symbol)
        return {
            "symbol": symbol,
            "last_price": price,
            "timestamp": datetime.now().isoformat(),
        }


def create_broker(**kwargs) -> BaseBroker:
    """
    工厂方法：创建 Broker 实例。

    实盘通道（miniQMT/xtquant）已按监管要求下线，本平台只提供本地模拟撮合，
    因此始终返回 PaperTradingBroker。
    """
    from backend.services.trade.services.simulation_manager import (
        SimulationAccountManager,
    )

    redis_client = kwargs.get("redis_client")
    market_url = kwargs.get("market_url", "http://stream-gateway:8003")

    if not redis_client:
        raise ValueError("Redis Client required for Paper Trading Broker")

    sim_manager = SimulationAccountManager(redis_client)
    return PaperTradingBroker(sim_manager, market_url)

