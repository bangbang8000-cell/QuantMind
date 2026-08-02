"""模拟盘撮合拒单测试：涨跌停、停牌、T+1 可卖量。

行情来源已从实时 HTTP 改为本地 quantdb（LocalMarketData），撮合规则
由 ashare_matcher 承载，因此这里注入假的 DailyBar 而非假的行情快照。
"""

from datetime import date

import pytest

from backend.services.trade.simulation.models.order import OrderSide, OrderType, SimOrder
from backend.services.trade.simulation.services.execution_engine import (
    SimulationExecutionEngine,
)
from backend.services.trade.simulation.services.local_market_data import DailyBar


class _FakeManager:
    def __init__(self, positions: dict | None = None):
        self.called = False
        self._positions = positions or {}

    async def get_account(self, **_kwargs):
        return {"positions": self._positions}

    async def update_balance(self, **_kwargs):
        self.called = True
        return {"success": True}


class _FakeDb:
    async def execute(self, *args, **kwargs):
        raise AssertionError("db.execute should not be called in these tests")


class _FakeMarketData:
    """只回放单个 DailyBar 的行情替身。"""

    def __init__(self, bar: DailyBar | None):
        self._bar = bar

    def get_bar(self, _symbol: str, _trade_date: date) -> DailyBar | None:
        return self._bar


def _bar(
    *,
    close: float = 10.0,
    limit_up: float = 11.0,
    limit_down: float = 9.0,
    suspended: bool = False,
) -> DailyBar:
    return DailyBar(
        symbol="600000.SH",
        trade_date=date(2026, 7, 30),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0 if suspended else 1_000_000,
        amount=0 if suspended else 10_000_000,
        vwap=close,
        pre_close=10.0,
        limit_up=limit_up,
        limit_down=limit_down,
        is_st=False,
        suspended=suspended,
    )


def _make_order(side: OrderSide, quantity: float = 100.0) -> SimOrder:
    return SimOrder(
        tenant_id="default",
        user_id=1001,
        portfolio_id=0,
        symbol="SH600000",
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
    )


def _engine(bar: DailyBar | None, manager: _FakeManager) -> SimulationExecutionEngine:
    return SimulationExecutionEngine(
        _FakeDb(), manager, market_data=_FakeMarketData(bar)
    )


@pytest.mark.asyncio
async def test_execute_order_blocks_buy_when_limit_up():
    manager = _FakeManager()
    engine = _engine(_bar(close=11.0, limit_up=11.0), manager)

    result = await engine.execute_order(_make_order(OrderSide.BUY))

    assert result.success is False
    assert result.message == "LIMIT_UP"
    assert manager.called is False


@pytest.mark.asyncio
async def test_execute_order_blocks_sell_when_limit_down():
    manager = _FakeManager({"SH600000": {"volume": 100, "available_volume": 100}})
    engine = _engine(_bar(close=9.0, limit_down=9.0), manager)

    result = await engine.execute_order(_make_order(OrderSide.SELL))

    assert result.success is False
    assert result.message == "LIMIT_DOWN"
    assert manager.called is False


@pytest.mark.asyncio
async def test_execute_order_blocks_when_suspended():
    manager = _FakeManager()
    engine = _engine(_bar(suspended=True), manager)

    result = await engine.execute_order(_make_order(OrderSide.BUY))

    assert result.success is False
    assert result.message == "SUSPENDED"
    assert manager.called is False


@pytest.mark.asyncio
async def test_execute_order_blocks_when_no_market_data():
    """本地无当日 bar 时必须拒单，绝不能虚构价格成交。"""
    manager = _FakeManager()
    engine = _engine(None, manager)

    result = await engine.execute_order(_make_order(OrderSide.BUY))

    assert result.success is False
    assert result.message == "NO_MARKET_DATA"
    assert manager.called is False


@pytest.mark.asyncio
async def test_execute_order_blocks_sell_exceeding_available_volume():
    """T+1：当日买入的部分不可卖。"""
    manager = _FakeManager({"SH600000": {"volume": 500, "available_volume": 100}})
    engine = _engine(_bar(), manager)

    result = await engine.execute_order(_make_order(OrderSide.SELL, quantity=300.0))

    assert result.success is False
    assert "INSUFFICIENT_AVAILABLE_VOLUME" in result.message
    assert manager.called is False


@pytest.mark.asyncio
async def test_execute_order_fills_and_charges_all_fees():
    manager = _FakeManager()
    engine = _engine(_bar(), manager)

    result = await engine.execute_order(_make_order(OrderSide.BUY))

    assert result.success is True
    assert result.quantity == 100
    assert result.commission > 0
    assert result.stamp_duty == 0.0  # 买入不收印花税
    assert result.transfer_fee > 0
    assert result.total_fee == result.commission + result.transfer_fee
    assert manager.called is True
