"""
Broker Client - 抽象 Broker 接口，支持模拟和真实交易

提供统一的下单接口，隔离 trading_engine 与具体 Broker 实现。
"""

import abc
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from backend.services.trade.services.simulation_manager import (
        SimulationAccountManager,
    )

from sqlalchemy import text

from backend.shared.auth import get_internal_call_secret
from backend.shared.database_manager_v2 import get_session

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
    Fetches real market prices for execution.
    """

    COMMISSION_RATE = 0.0003  # 0.03% commission

    def __init__(
        self,
        simulation_manager: "SimulationAccountManager",
        market_url: str = "http://stream-gateway:8003",
    ):
        self.simulation_manager = simulation_manager
        self.market_url = market_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if not text:
            return False
        return text in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _is_price_near(price: float, limit_price: float | None, tolerance: float = 0.0015) -> bool:
        if limit_price is None or limit_price <= 0 or price <= 0:
            return False
        return abs(price - limit_price) / max(limit_price, 1e-6) <= tolerance

    async def _get_market_snapshot(self, symbol: str) -> MarketQuoteSnapshot:
        # Level 1: 实时行情
        try:
            client = await self._get_client()
            headers = {"X-Internal-Call": get_internal_call_secret()}
            resp = await client.get(f"{self.market_url}/api/v1/quotes/{symbol}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                px = self._as_float(data.get("current_price") or data.get("last_price"))
                if px and px > 0:
                    limit_up = self._as_bool(data.get("is_limit_up"))
                    limit_down = self._as_bool(data.get("is_limit_down"))
                    suspended = self._as_bool(data.get("suspended") or data.get("is_suspended"))
                    limit_up_price = self._as_float(data.get("limit_up_today"))
                    limit_down_price = self._as_float(data.get("limit_down_today"))
                    if not limit_up and self._is_price_near(px, limit_up_price):
                        limit_up = True
                    if not limit_down and self._is_price_near(px, limit_down_price):
                        limit_down = True

                    pre_close = self._as_float(data.get("pre_close") or data.get("close_price"))
                    ask1_volume = self._as_int(data.get("ask1_volume"))
                    bid1_volume = self._as_int(data.get("bid1_volume"))
                    if pre_close and pre_close > 0:
                        change_ratio = (px - pre_close) / pre_close
                        if not limit_up and ask1_volume is not None and ask1_volume <= 0 and change_ratio >= 0.095:
                            limit_up = True
                        if not limit_down and bid1_volume is not None and bid1_volume <= 0 and change_ratio <= -0.095:
                            limit_down = True

                    return MarketQuoteSnapshot(
                        price=px,
                        limit_up=limit_up,
                        limit_down=limit_down,
                        suspended=suspended,
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch real-time price for {symbol}: {e}")

        # Level 2: 数据库兜底 (L2 Fallback)
        try:
            async with get_session(read_only=True) as session:
                query_with_limits = text("""
                    SELECT close, adj_factor, limit_up_today, limit_down_today, volume
                    FROM stock_daily_latest
                    WHERE symbol = :symbol
                    ORDER BY trade_date DESC LIMIT 1
                """)
                try:
                    result = await session.execute(query_with_limits, {"symbol": symbol})
                    row = result.fetchone()
                    if row:
                        hfq_close = float(row[0])
                        adj_factor = float(row[1] or 1.0)
                        price = hfq_close / adj_factor if adj_factor > 0 else hfq_close
                        logger.info("[PaperTrading] Fallback to DB nominal price for %s: %s", symbol, price)
                        return MarketQuoteSnapshot(
                            price=price,
                            limit_up=self._is_price_near(price, self._as_float(row[2])),
                            limit_down=self._is_price_near(price, self._as_float(row[3])),
                            suspended=(self._as_float(row[4]) or 0.0) <= 0.0,
                        )
                except Exception:
                    query_legacy = text("""
                        SELECT close, adj_factor
                        FROM stock_daily_latest
                        WHERE symbol = :symbol
                        ORDER BY trade_date DESC LIMIT 1
                    """)
                    result = await session.execute(query_legacy, {"symbol": symbol})
                    row = result.fetchone()
                    if row:
                        hfq_close = float(row[0])
                        adj_factor = float(row[1] or 1.0)
                        price = hfq_close / adj_factor if adj_factor > 0 else hfq_close
                        logger.info("[PaperTrading] Fallback to DB legacy nominal price for %s: %s", symbol, price)
                        return MarketQuoteSnapshot(price=price)
        except Exception as e:
            logger.error(f"[PaperTrading] Database fallback failed for {symbol}: {e}")

        # Level 3: 最终保底
        return MarketQuoteSnapshot(price=100.0 + random.uniform(-1, 1))

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

