"""
Synthetic execution engine for simulation orders.

行情来源：本地 quantdb parquet（经 LocalMarketData），不再依赖实时行情 HTTP。
撮合规则：A股完整版（涨跌停、整手、三项费用、滑点），由 ashare_matcher 承载。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.simulation.models.order import (
    OrderStatus,
    OrderType,
    SimOrder,
)
from backend.services.trade.simulation.models.trade import SimTrade
from backend.services.trade.simulation.services.ashare_matcher import (
    MatchConfig,
    MatchResult,
    match_order,
)
from backend.services.trade.simulation.services.local_market_data import (
    DailyBar,
    LocalMarketData,
    get_local_market_data,
)
from backend.services.trade.simulation.services.simulation_manager import (
    SimulationAccountManager,
)
from backend.services.trade.trade_config import settings
from backend.shared.trade_account_cache import write_trade_account_cache

logger = logging.getLogger(__name__)


class ExecutionResult:
    def __init__(
        self,
        *,
        success: bool,
        price: float = 0.0,
        quantity: float = 0.0,
        commission: float = 0.0,
        stamp_duty: float = 0.0,
        transfer_fee: float = 0.0,
        total_fee: float = 0.0,
        price_source: str | None = None,
        message: str = "",
    ):
        self.success = success
        self.price = price
        self.quantity = quantity
        self.commission = commission
        self.stamp_duty = stamp_duty
        self.transfer_fee = transfer_fee
        self.total_fee = total_fee
        self.price_source = price_source
        self.message = message


@dataclass
class MarketSnapshot:
    price: float
    price_source: str
    limit_up: bool = False
    limit_down: bool = False
    suspended: bool = False


def _match_to_exec(mr: MatchResult, price_source: str) -> ExecutionResult:
    if mr.success:
        return ExecutionResult(
            success=True,
            price=mr.fill_price,
            quantity=mr.fill_quantity,
            commission=mr.commission,
            stamp_duty=mr.stamp_duty,
            transfer_fee=mr.transfer_fee,
            total_fee=mr.total_fee,
            price_source=price_source,
        )
    return ExecutionResult(success=False, message=mr.reason)


class SimulationExecutionEngine:
    def __init__(
        self,
        db: AsyncSession,
        manager: SimulationAccountManager,
        market_data: LocalMarketData | None = None,
        match_config: MatchConfig | None = None,
    ):
        self.db = db
        self.manager = manager
        self._market_data = market_data or get_local_market_data()
        self._match_config = match_config or MatchConfig()

    async def execute_order(self, order: SimOrder) -> ExecutionResult:
        side = str(order.side.value).lower()
        trade_date = datetime.now().date()
        bar = self._market_data.get_bar(order.symbol, trade_date)

        if bar is None:
            return ExecutionResult(
                success=False, message="NO_MARKET_DATA",
            )

        # T+1 可卖量
        available_volume: float | None = None
        if side == "sell":
            account = await self.manager.get_account(
                user_id=order.user_id, tenant_id=order.tenant_id,
            )
            if account:
                pos = (account.get("positions") or {}).get(order.symbol)
                if pos:
                    vol = float(pos.get("volume", 0))
                    avail = pos.get("available_volume")
                    available_volume = vol if avail is None else float(avail)

        mr = match_order(
            side=side,
            quantity=int(order.quantity),
            bar=bar,
            cfg=self._match_config,
            available_volume=available_volume,
        )
        result = _match_to_exec(mr, price_source=f"local_{self._match_config.price_mode}")

        if not result.success:
            return result

        # 限价单检查
        if order.order_type == OrderType.LIMIT:
            if order.price is None or order.price <= 0:
                return ExecutionResult(success=False, message="Limit price required")
            if side == "buy" and result.price > float(order.price):
                return ExecutionResult(success=False, message="Limit price not reachable")
            if side == "sell" and result.price < float(order.price):
                return ExecutionResult(success=False, message="Limit price not reachable")
            result.price = round(float(order.price), 4)
            result.price_source = "limit_price"

        # 账户余额更新
        gross = result.quantity * result.price
        if side == "buy":
            delta_cash = -(gross + result.total_fee)
            delta_volume = result.quantity
        else:
            delta_cash = gross - result.total_fee
            delta_volume = -result.quantity

        update = await self.manager.update_balance(
            user_id=order.user_id,
            symbol=order.symbol,
            delta_cash=delta_cash,
            delta_volume=delta_volume,
            price=result.price,
            tenant_id=order.tenant_id,
        )
        if not update.get("success"):
            reason = update.get("reason", "BALANCE_UPDATE_FAILED")
            if reason == "INSUFFICIENT_CASH":
                return ExecutionResult(success=False, message="Insufficient cash for buy order")
            if reason == "INSUFFICIENT_HOLDINGS":
                return ExecutionResult(success=False, message="Insufficient holdings for sell order")
            if reason == "INSUFFICIENT_AVAILABLE_VOLUME":
                return ExecutionResult(success=False, message="Insufficient available volume (T+1)")
            return ExecutionResult(success=False, message=f"Balance update failed: {reason}")

        return result

    async def apply_filled(self, order: SimOrder, result: ExecutionResult) -> SimTrade:
        trade_value = result.quantity * result.price
        trade = SimTrade(
            order_id=order.order_id,
            tenant_id=order.tenant_id,
            user_id=order.user_id,
            portfolio_id=order.portfolio_id,
            symbol=order.symbol,
            side=order.side,
            quantity=result.quantity,
            price=result.price,
            trade_value=trade_value,
            commission=result.commission,
            stamp_duty=result.stamp_duty,
            transfer_fee=result.transfer_fee,
            total_fee=result.total_fee,
            executed_at=datetime.now(),
            price_source=result.price_source,
        )
        self.db.add(trade)

        order.status = OrderStatus.FILLED
        order.submitted_at = order.submitted_at or datetime.now()
        order.filled_at = datetime.now()
        order.filled_quantity = result.quantity
        order.average_price = result.price
        order.filled_value = trade_value
        order.commission = result.commission
        order.order_value = order.quantity * (order.price or 0)
        order.total_fee = result.total_fee
        order.execution_model = "ashare_matcher"
        order.price_source = result.price_source

        await self.db.commit()
        await self.db.refresh(order)
        await self.db.refresh(trade)
        await self._sync_trade_account(order.tenant_id, order.user_id)
        return trade

    async def mark_rejected(self, order: SimOrder, message: str):
        order.status = OrderStatus.REJECTED
        order.submitted_at = order.submitted_at or datetime.now()
        order.remarks = f"Execution rejected: {message}"
        await self.db.commit()
        await self.db.refresh(order)

    async def _sync_trade_account(self, tenant_id: str, user_id: int):
        if not self.manager.redis.client:
            return
        account = await self.manager.get_account(user_id, tenant_id=tenant_id)
        if not account:
            return
        payload = dict(account)
        payload.setdefault("timestamp", datetime.now().isoformat())
        write_trade_account_cache(self.manager.redis, tenant_id, user_id, payload)
