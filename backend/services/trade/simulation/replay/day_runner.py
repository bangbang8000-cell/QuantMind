"""单个模拟交易日的推演引擎。

刻意不复用 SimulationEngine.run_cycle —— 那条路径带着活盘专属副作用
（策略生命周期、通知推送、trade_account_cache 同步），回放不该触发。
这里只做组合：SignalLoader + RebalanceCalculator + match_order + LocalMarketData。

单日执行顺序（顺序本身是语义的一部分，不要随意调换）：
  1. 载入行情
  2. T+1 解锁（把昨日买入变为今日可卖）
  3. 止损扫描（先止损再按信号调仓，否则该割的仓位可能被当成"目标持仓"留下）
  4. 信号 → 目标持仓 → 交易指令
  5. 撮合（先卖后买，腾出现金）
  6. 收盘估值 + 写净值快照
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.simulation.models.order import (
    OrderSide,
    OrderStatus,
    OrderType,
)
from backend.services.trade.simulation.models.replay import (
    OrderOrigin,
    ReplayEquitySnapshot,
    ReplayOrder,
    ReplayTrade,
)
from backend.services.trade.simulation.replay.account import ReplayAccountManager
from backend.services.trade.simulation.services.ashare_matcher import (
    MatchConfig,
    compute_fees,
    match_order,
)
from backend.services.trade.simulation.services.local_market_data import (
    DailyBar,
    LocalMarketData,
    get_local_market_data,
)
from backend.services.trade.simulation.services.rebalance_calculator import (
    Order,
    Quote,
    RebalanceCalculator,
    SimulationAccount,
    StrategyConfig,
    WeightMode,
)
from backend.services.trade.simulation.replay.signal_generator import (
    ReplaySignalLoader,
    replay_signal_loader,
)

logger = logging.getLogger(__name__)


@dataclass
class DayResult:
    trade_date: date
    signal_count: int = 0
    filled: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    stop_loss_fills: list[dict[str, Any]] = field(default_factory=list)
    account: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    # 当日已实现盈亏合计（所有卖出之和），用于写入 equity snapshot
    realized_pnl_today: float = 0.0
    error: str | None = None


def _compute_holding_days(first_buy_date: Any, sell_date: date) -> int | None:
    """持有天数（自然日）。first_buy_date 为 ISO 字符串或 None。"""
    if not first_buy_date:
        return None
    try:
        if isinstance(first_buy_date, str):
            fbd = date.fromisoformat(first_buy_date[:10])
        elif isinstance(first_buy_date, date):
            fbd = first_buy_date
        else:
            return None
    except (ValueError, TypeError):
        return None
    delta = (sell_date - fbd).days
    return delta if delta >= 0 else None


def resolve_stop_fill_price(bar: DailyBar, stop_price: float) -> float:
    """止损成交价。

    触发条件用当日最低价，但**成交价不能好于当日实际能成交的价格**：
    跳空开盘时 open 已经低于 stop，按 stop 成交等于卖在一个当天不存在的价位
    （实测 2026-07-28 有 60 只跳空，最差 301512.SZ 前收 39.82 / 开 27.39），
    会让回放净值系统性偏高。故取 min(stop, open)，再受跌停价钳制。
    """
    price = min(stop_price, bar.open) if bar.open > 0 else stop_price
    if bar.limit_down > 0:
        price = max(price, bar.limit_down)
    return round(price, 4)


class ReplayDayRunner:
    def __init__(
        self,
        market_data: LocalMarketData | None = None,
        loader: ReplaySignalLoader | None = None,
        match_config: MatchConfig | None = None,
    ):
        self._market_data = market_data or get_local_market_data()
        self._loader = loader or replay_signal_loader
        # 回放按开盘价撮合：信号是昨收后算出来的，次日开盘才可交易
        self._cfg = match_config or MatchConfig(price_mode="open")
        self._calculator = RebalanceCalculator()

    async def run_day(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        tenant_id: str,
        user_id: str,
        accounts: ReplayAccountManager,
        strategy_params: dict[str, Any] | None = None,
        stop_loss_pct: float | None = None,
        approved_orders: list[dict[str, Any]] | None = None,
        initial_cash: float = 0.0,
    ) -> DayResult:
        result = DayResult(trade_date=trade_date)

        account_data = await accounts.get()
        if not account_data:
            result.error = "回放账户不存在"
            return result

        # 2. T+1 解锁：昨日买入的今日可卖
        await accounts.unlock()
        account_data = await accounts.get() or {}

        held = list((account_data.get("positions") or {}).keys())
        signals = await self._loader.load_signals_for_date(
            db=db,
            session_id=session_id,
            trade_date=trade_date,
        )
        result.signal_count = len(signals)

        wanted = sorted(set(held) | {s.symbol for s in signals})
        bars = self._market_data.load_date(trade_date, symbols=wanted) if wanted else {}

        # 3. 止损扫描
        if stop_loss_pct and stop_loss_pct > 0:
            await self._run_stop_loss(
                db, session_id, trade_date, accounts, bars, stop_loss_pct, result
            )
            account_data = await accounts.get() or {}

        # 4. 信号 → 交易指令
        orders = self._build_orders(
            signals=signals,
            bars=bars,
            account_data=account_data,
            strategy_params=strategy_params or {},
            approved_orders=approved_orders,
        )

        # 5. 撮合：先卖后买
        for order in sorted(orders, key=lambda o: 0 if o.side == "SELL" else 1):
            await self._execute(
                db,
                session_id,
                trade_date,
                accounts,
                bars,
                order,
                result,
                origin=OrderOrigin.MANUAL
                if approved_orders is not None
                else OrderOrigin.SIGNAL,
            )

        # 6. 收盘估值 + 快照
        account_data = await accounts.get() or {}
        result.account = await self._mark_to_market(accounts, account_data, bars)
        result.snapshot = await self._write_snapshot(
            db,
            session_id,
            trade_date,
            result.account,
            initial_cash=initial_cash,
            realized_pnl_today=result.realized_pnl_today,
        )
        return result

    # ------------------------------------------------------------------

    async def _run_stop_loss(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        accounts: ReplayAccountManager,
        bars: dict[str, DailyBar],
        stop_loss_pct: float,
        result: DayResult,
    ) -> None:
        account_data = await accounts.get() or {}
        for symbol, pos in list((account_data.get("positions") or {}).items()):
            bar = bars.get(symbol)
            if bar is None or bar.suspended:
                continue
            cost = float(pos.get("cost") or 0.0)
            if cost <= 0:
                continue
            stop_price = cost * (1.0 - stop_loss_pct)
            if bar.low > stop_price:
                continue

            avail = pos.get("available_volume")
            qty = int(float(pos.get("volume", 0)) if avail is None else float(avail))
            if qty <= 0:
                continue

            fill_price = resolve_stop_fill_price(bar, stop_price)
            if fill_price <= 0:
                continue
            commission, stamp_duty, transfer_fee, total_fee = compute_fees(
                qty, fill_price, "sell", self._cfg
            )
            gross = qty * fill_price
            update = await accounts.apply_fill(
                symbol=symbol,
                delta_cash=gross - total_fee,
                delta_volume=-qty,
                price=fill_price,
            )
            if not update.get("success"):
                result.rejected.append(
                    {
                        "symbol": symbol,
                        "side": "SELL",
                        "origin": "stop_loss",
                        "reason": update.get("reason", "BALANCE_UPDATE_FAILED"),
                    }
                )
                continue

            realized = await self._persist_fill(
                db,
                session_id,
                trade_date,
                symbol,
                OrderSide.SELL,
                OrderOrigin.STOP_LOSS,
                qty,
                fill_price,
                commission,
                stamp_duty,
                transfer_fee,
                total_fee,
                price_source="stop_loss",
                avg_cost_before=cost,
                holding_days=_compute_holding_days(
                    pos.get("first_buy_date"), trade_date
                ),
            )
            result.realized_pnl_today += realized
            result.stop_loss_fills.append(
                {
                    "symbol": symbol,
                    "quantity": qty,
                    "price": fill_price,
                    "stop_price": round(stop_price, 4),
                    "total_fee": round(total_fee, 2),
                    "realized_pnl": round(realized, 2),
                    "avg_cost": round(cost, 4),
                    "gap_down": bar.open < stop_price,
                }
            )

    def _build_orders(
        self,
        signals: list,
        bars: dict[str, DailyBar],
        account_data: dict[str, Any],
        strategy_params: dict[str, Any],
        approved_orders: list[dict[str, Any]] | None,
    ) -> list[Order]:
        # 手动模式：只执行用户勾选的委托
        if approved_orders is not None:
            out = []
            for item in approved_orders:
                symbol = str(item.get("symbol") or "").upper()
                bar = bars.get(symbol)
                if bar is None:
                    continue
                out.append(
                    Order(
                        symbol=symbol,
                        side=str(item.get("side") or "BUY").upper(),
                        quantity=int(item.get("quantity") or 0),
                        price=bar.open or bar.close,
                        reason="manual",
                    )
                )
            return out

        if not signals:
            return []

        quotes = {
            sym: Quote(
                symbol=sym,
                current_price=bar.open or bar.close,
                is_limit_up=(bar.close >= bar.limit_up)
                if math.isfinite(bar.limit_up)
                else False,
                is_limit_down=(bar.close <= bar.limit_down)
                if bar.limit_down > 0
                else False,
                is_suspended=bar.suspended,
                pre_close=bar.pre_close if bar.pre_close > 0 else None,
            )
            for sym, bar in bars.items()
        }
        config = StrategyConfig(
            topk=int(strategy_params.get("topk", 10)),
            weight_mode=WeightMode(strategy_params.get("weight_mode", "equal")),
            custom_weights=strategy_params.get("custom_weights", {}) or {},
            min_score=float(strategy_params.get("min_score", 0.0)),
            max_position_pct=float(strategy_params.get("max_position_pct", 0.15)),
            lot_size=int(strategy_params.get("lot_size", 100)),
        )
        account = SimulationAccount(
            cash=float(account_data.get("cash", 0)),
            total_asset=float(account_data.get("total_asset", 0)),
            positions=account_data.get("positions", {}) or {},
        )
        return self._calculator.calculate(
            signals=signals, strategy=config, quotes=quotes, account=account
        )

    async def _execute(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        accounts: ReplayAccountManager,
        bars: dict[str, DailyBar],
        order: Order,
        result: DayResult,
        origin: OrderOrigin,
    ) -> None:
        bar = bars.get(order.symbol)
        if bar is None:
            result.rejected.append(
                {
                    "symbol": order.symbol,
                    "side": order.side,
                    "reason": "NO_MARKET_DATA",
                }
            )
            return

        side = order.side.lower()
        available_volume = None
        # 卖出前抓取移动加权成本与首次买入日 —— apply_fill 之后 Lua 可能删掉持仓
        avg_cost_before: float | None = None
        holding_days: int | None = None
        if side == "sell":
            account_data = await accounts.get() or {}
            pos = (account_data.get("positions") or {}).get(order.symbol)
            if pos:
                avail = pos.get("available_volume")
                available_volume = (
                    float(pos.get("volume", 0)) if avail is None else float(avail)
                )
                cost = float(pos.get("cost") or 0.0)
                avg_cost_before = cost if cost > 0 else None
                holding_days = _compute_holding_days(pos.get("first_buy_date"), trade_date)

        mr = match_order(
            side=side,
            quantity=int(order.quantity),
            bar=bar,
            cfg=self._cfg,
            available_volume=available_volume,
        )
        if not mr.success:
            result.rejected.append(
                {
                    "symbol": order.symbol,
                    "side": order.side,
                    "reason": mr.reason,
                }
            )
            await self._persist_rejected(
                db, session_id, trade_date, order, origin, mr.reason
            )
            return

        gross = mr.fill_quantity * mr.fill_price
        if side == "buy":
            delta_cash, delta_volume = -(gross + mr.total_fee), mr.fill_quantity
        else:
            delta_cash, delta_volume = gross - mr.total_fee, -mr.fill_quantity

        update = await accounts.apply_fill(
            symbol=order.symbol,
            delta_cash=delta_cash,
            delta_volume=delta_volume,
            price=mr.fill_price,
        )
        if not update.get("success"):
            reason = update.get("reason", "BALANCE_UPDATE_FAILED")
            result.rejected.append(
                {
                    "symbol": order.symbol,
                    "side": order.side,
                    "reason": reason,
                }
            )
            await self._persist_rejected(
                db, session_id, trade_date, order, origin, reason
            )
            return

        realized = await self._persist_fill(
            db,
            session_id,
            trade_date,
            order.symbol,
            OrderSide.BUY if side == "buy" else OrderSide.SELL,
            origin,
            mr.fill_quantity,
            mr.fill_price,
            mr.commission,
            mr.stamp_duty,
            mr.transfer_fee,
            mr.total_fee,
            price_source=f"local_{self._cfg.price_mode}",
            avg_cost_before=avg_cost_before,
            holding_days=holding_days,
        )
        result.realized_pnl_today += realized
        # 买入后记录首次买入日，供后续卖出算持有天数
        if side == "buy":
            await self._stamp_first_buy_date(accounts, order.symbol, trade_date)
        result.filled.append(
            {
                "symbol": order.symbol,
                "side": order.side,
                "quantity": mr.fill_quantity,
                "price": mr.fill_price,
                "total_fee": round(mr.total_fee, 2),
                "realized_pnl": round(realized, 2) if side == "sell" else None,
                "avg_cost": round(avg_cost_before, 4) if avg_cost_before else None,
                "holding_days": holding_days,
                "reason": order.reason,
            }
        )

    async def _stamp_first_buy_date(
        self,
        accounts: ReplayAccountManager,
        symbol: str,
        trade_date: date,
    ) -> None:
        """买入后在持仓上打首次买入日戳（已有则不覆盖）。

        Lua 只维护 volume/available_volume/cost/price/market_value，
        first_buy_date 是回放侧扩展字段，用整体回写方式落到 Redis。
        """
        account_data = await accounts.get()
        if not account_data:
            return
        pos = (account_data.get("positions") or {}).get(symbol)
        if not pos or pos.get("first_buy_date"):
            return
        pos["first_buy_date"] = trade_date.isoformat()
        accounts.write(account_data)

    async def _persist_fill(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        symbol: str,
        side: OrderSide,
        origin: OrderOrigin,
        quantity: float,
        price: float,
        commission: float,
        stamp_duty: float,
        transfer_fee: float,
        total_fee: float,
        price_source: str,
        avg_cost_before: float | None = None,
        holding_days: int | None = None,
    ) -> float:
        """落库委托 + 成交，返回本笔已实现盈亏（买入返回 0.0）。

        avg_cost_before 必须由调用方在 apply_fill **之前**抓取 —— Lua 在
        volume<=0.0001 时会删掉整个持仓 dict，清仓后 cost 永久丢失。
        """
        order_row = ReplayOrder(
            session_id=session_id,
            trade_date=trade_date,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            origin=origin,
            quantity=quantity,
            filled_quantity=quantity,
            price=price,
            average_price=price,
            filled_value=quantity * price,
            total_fee=total_fee,
            price_source=price_source,
        )
        db.add(order_row)
        await db.flush()

        # 已实现盈亏仅在卖出时产生：(卖价 - 移动加权成本) × 数量 - 全部费用
        realized_pnl: float | None = None
        if side == OrderSide.SELL and avg_cost_before is not None and avg_cost_before > 0:
            realized_pnl = (price - avg_cost_before) * quantity - total_fee

        db.add(
            ReplayTrade(
                session_id=session_id,
                order_id=order_row.order_id,
                trade_date=trade_date,
                symbol=symbol,
                side=side,
                origin=origin,
                quantity=quantity,
                price=price,
                trade_value=quantity * price,
                commission=commission,
                stamp_duty=stamp_duty,
                transfer_fee=transfer_fee,
                total_fee=total_fee,
                price_source=price_source,
                avg_cost_before=avg_cost_before,
                realized_pnl=realized_pnl,
                holding_days=holding_days,
            )
        )
        return realized_pnl or 0.0

    async def _persist_rejected(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        order: Order,
        origin: OrderOrigin,
        reason: str,
    ) -> None:
        db.add(
            ReplayOrder(
                session_id=session_id,
                trade_date=trade_date,
                symbol=order.symbol,
                side=OrderSide.BUY if order.side.lower() == "buy" else OrderSide.SELL,
                order_type=OrderType.MARKET,
                status=OrderStatus.REJECTED,
                origin=origin,
                quantity=order.quantity,
                price=order.price,
                reject_reason=reason[:200],
            )
        )

    async def _mark_to_market(
        self,
        accounts: ReplayAccountManager,
        account_data: dict[str, Any],
        bars: dict[str, DailyBar],
    ) -> dict[str, Any]:
        """按当日收盘价重估持仓市值。

        Lua 里的 total_asset 只用最后成交价，收盘估值必须在这里补一次，
        否则净值曲线反映的是"最后一次交易时的价格"而不是当日收盘。
        """
        positions = account_data.get("positions") or {}
        market_value = 0.0
        for symbol, pos in positions.items():
            bar = bars.get(symbol)
            close = (
                bar.close if bar and bar.close > 0 else float(pos.get("price") or 0.0)
            )
            volume = float(pos.get("volume") or 0.0)
            pos["price"] = close
            pos["market_value"] = close * volume
            market_value += close * volume

        cash = float(account_data.get("cash") or 0.0)
        account_data["market_value"] = market_value
        account_data["total_asset"] = cash + market_value
        accounts.write(account_data)
        return account_data

    async def _write_snapshot(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trade_date: date,
        account: dict[str, Any],
        initial_cash: float = 0.0,
        realized_pnl_today: float = 0.0,
    ) -> dict[str, Any]:
        prev = (
            (
                await db.execute(
                    select(ReplayEquitySnapshot)
                    .where(ReplayEquitySnapshot.session_id == session_id)
                    .order_by(ReplayEquitySnapshot.trade_date.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

        total_asset = float(account.get("total_asset") or 0.0)
        positions = account.get("positions") or {}

        if prev:
            day_pnl = total_asset - float(prev.total_asset)
        else:
            # bug 1 fix: 首日以 initial_cash 为基准，正确计入买入手续费和当日涨跌
            day_pnl = total_asset - initial_cash

        # 已实现盈亏累计 = 上一日累计 + 当日已实现
        realized_pnl_cum = (float(prev.realized_pnl_cum) + realized_pnl_today) if prev else realized_pnl_today

        # 浮动盈亏 = Σ (收盘价 - 成本价) × 持仓量
        unrealized_pnl = 0.0
        for _sym, pos in positions.items():
            cost = float(pos.get("cost") or 0.0)
            vol = float(pos.get("volume") or 0.0)
            price = float(pos.get("price") or 0.0)
            if cost > 0 and vol > 0:
                unrealized_pnl += (price - cost) * vol

        existing = (
            (
                await db.execute(
                    select(ReplayEquitySnapshot).where(
                        ReplayEquitySnapshot.session_id == session_id,
                        ReplayEquitySnapshot.trade_date == trade_date,
                    )
                )
            )
            .scalars()
            .first()
        )

        row = existing or ReplayEquitySnapshot(
            session_id=session_id, trade_date=trade_date
        )
        row.cash = float(account.get("cash") or 0.0)
        row.market_value = float(account.get("market_value") or 0.0)
        row.total_asset = total_asset
        row.day_pnl = day_pnl
        row.cum_pnl = (float(prev.cum_pnl) + day_pnl) if prev else day_pnl
        row.realized_pnl_cum = realized_pnl_cum
        row.unrealized_pnl = unrealized_pnl
        row.position_count = len(positions)
        row.positions = positions
        if existing is None:
            db.add(row)

        return {
            "trade_date": trade_date.isoformat(),
            "cash": row.cash,
            "market_value": row.market_value,
            "total_asset": row.total_asset,
            "day_pnl": row.day_pnl,
            "cum_pnl": row.cum_pnl,
            "realized_pnl_cum": row.realized_pnl_cum,
            "unrealized_pnl": row.unrealized_pnl,
            "position_count": row.position_count,
        }
