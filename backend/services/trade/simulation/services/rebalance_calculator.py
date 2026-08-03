"""
Rebalance Calculator - 调仓计算器
支持 TopK 筛选、多种权重模式、涨跌停过滤、先卖后买逻辑
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.services.trade.simulation.services.signal_loader import SignalScore

logger = logging.getLogger(__name__)


class WeightMode(str, Enum):
    """权重模式"""
    EQUAL = "equal"  # 等权
    SCORE_WEIGHTED = "score_weighted"  # 按 score 加权
    CUSTOM = "custom"  # 自定义权重


@dataclass
class StrategyConfig:
    """策略配置"""
    topk: int = 10
    weight_mode: WeightMode = WeightMode.EQUAL
    custom_weights: dict[str, float] = field(default_factory=dict)
    min_score: float = 0.0
    max_position_pct: float = 0.15  # 单只股票最大仓位比例
    lot_size: int = 100  # 最小交易单位

    # ── 以下为 R2 新增，默认值保持既有行为，实盘路径不受影响 ──
    # 是否启用 min_score 过滤。历史上 min_score 字段存在但从未被读取（死配置），
    # 直接启用会改变实盘选股结果，故用开关显式 opt-in。
    enable_min_score: bool = False
    # 权重被 max_position_pct 砍削后是否重新归一。
    # 关闭时 topk=5 + 等权 → 每只 0.2 砍到 0.15 → 仅投 75%，25% 永久空仓。
    renormalize_weights: bool = False
    # 买单是否按 score 降序生成。关闭时遍历 set()，现金不足时拒单对象随机不可复现。
    deterministic_buy_order: bool = False
    # 持仓中但已跌出目标的标的：即使跌停也生成卖单（由撮合层拒绝并留下记录）。
    # 关闭时跌停持仓在计算阶段就被静默丢弃，"该割的割不掉"且无痕迹。
    force_exit_on_limit_down: bool = False


@dataclass
class Quote:
    """行情数据"""
    symbol: str
    current_price: float
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_suspended: bool = False
    pre_close: float | None = None


@dataclass
class Order:
    """交易指令"""
    symbol: str
    side: str  # "BUY" | "SELL"
    quantity: int
    price: float
    reason: str = ""


@dataclass
class SimulationAccount:
    """模拟账户快照"""
    cash: float
    total_asset: float
    positions: dict[str, dict[str, Any]]


class RebalanceCalculator:
    """
    调仓计算器：
    1. 根据 signal score 排序，取 TopK
    2. 计算目标权重（支持多种模式）
    3. 计算目标持仓金额 → 目标股数
    4. 剔除涨跌停标的
    5. 计算买卖指令（先卖后买）
    """

    def calculate(
        self,
        signals: list[SignalScore],
        strategy: StrategyConfig,
        quotes: dict[str, Quote],
        account: SimulationAccount,
    ) -> list[Order]:
        """
        计算调仓指令。

        Args:
            signals: 信号列表
            strategy: 策略配置
            quotes: 行情数据 {symbol: Quote}
            account: 当前账户状态

        Returns:
            交易指令列表（先卖后买）
        """
        if not signals:
            logger.info("RebalanceCalculator: 无信号，跳过调仓")
            return []

        # 0. min_score 过滤（opt-in，见 StrategyConfig.enable_min_score）
        if strategy.enable_min_score:
            before = len(signals)
            signals = [s for s in signals if s.score >= strategy.min_score]
            if before != len(signals):
                logger.info(
                    "RebalanceCalculator: min_score=%.6f 过滤 %d → %d",
                    strategy.min_score, before, len(signals),
                )
            if not signals:
                logger.info("RebalanceCalculator: min_score 过滤后无信号")
                return []

        # 1. 剔除涨跌停、停牌标的
        tradable_signals = self._filter_tradable(signals, quotes)
        if not tradable_signals:
            logger.info("RebalanceCalculator: 无可交易标的，跳过调仓")
            return []

        # 2. TopK 筛选
        topk_signals = sorted(
            tradable_signals,
            key=lambda x: x.score,
            reverse=True,
        )[: strategy.topk]

        # 3. 计算目标权重
        weights = self._calc_weights(topk_signals, strategy)

        # 4. 计算目标持仓
        target_positions = self._calc_target_positions(
            topk_signals, weights, quotes, account, strategy
        )

        # 5. 生成调仓指令（先卖后买）
        # score_order 用于买单确定性排序；force_exit 让跌停持仓也能生成卖单
        orders = self._generate_orders(
            account.positions,
            target_positions,
            quotes,
            score_order=[s.symbol for s in topk_signals]
            if strategy.deterministic_buy_order
            else None,
            force_exit_on_limit_down=strategy.force_exit_on_limit_down,
        )

        logger.info(
            "RebalanceCalculator: 生成 %d 条指令, 卖出=%d 买入=%d",
            len(orders),
            sum(1 for o in orders if o.side == "SELL"),
            sum(1 for o in orders if o.side == "BUY"),
        )
        return orders

    def _filter_tradable(
        self,
        signals: list[SignalScore],
        quotes: dict[str, Quote],
    ) -> list[SignalScore]:
        """剔除不可交易标的。

        按信号方向分别过滤：
        - 买入信号：跳过涨停、停牌
        - 卖出信号：跳过跌停、停牌
        - 无方向信号：跳过涨跌停、停牌（保守策略）
        """
        tradable = []
        for sig in signals:
            quote = quotes.get(sig.symbol)
            if not quote:
                logger.debug("RebalanceCalculator: %s 无行情数据，跳过", sig.symbol)
                continue
            if quote.is_suspended:
                logger.debug("RebalanceCalculator: %s 停牌，跳过", sig.symbol)
                continue
            if quote.current_price <= 0:
                logger.debug("RebalanceCalculator: %s 价格无效，跳过", sig.symbol)
                continue

            side = getattr(sig, "side", None)
            if side == "BUY" or side == "buy":
                if quote.is_limit_up:
                    logger.debug("RebalanceCalculator: %s 涨停，买入跳过", sig.symbol)
                    continue
            elif side == "SELL" or side == "sell":
                if quote.is_limit_down:
                    logger.debug("RebalanceCalculator: %s 跌停，卖出跳过", sig.symbol)
                    continue
            else:
                if quote.is_limit_up or quote.is_limit_down:
                    logger.debug(
                        "RebalanceCalculator: %s 涨跌停（up=%s down=%s），跳过",
                        sig.symbol,
                        quote.is_limit_up,
                        quote.is_limit_down,
                    )
                    continue
            tradable.append(sig)
        return tradable

    def _calc_weights(
        self,
        signals: list[SignalScore],
        strategy: StrategyConfig,
    ) -> dict[str, float]:
        """计算目标权重"""
        if not signals:
            return {}

        if strategy.weight_mode == WeightMode.CUSTOM and strategy.custom_weights:
            return strategy.custom_weights

        if strategy.weight_mode == WeightMode.EQUAL:
            weight = 1.0 / len(signals)
            return {sig.symbol: weight for sig in signals}

        if strategy.weight_mode == WeightMode.SCORE_WEIGHTED:
            total_score = sum(sig.score for sig in signals)
            if total_score <= 0:
                weight = 1.0 / len(signals)
                return {sig.symbol: weight for sig in signals}
            return {
                sig.symbol: sig.score / total_score
                for sig in signals
            }

        # 默认等权
        weight = 1.0 / len(signals)
        return {sig.symbol: weight for sig in signals}

    def _calc_target_positions(
        self,
        signals: list[SignalScore],
        weights: dict[str, float],
        quotes: dict[str, Quote],
        account: SimulationAccount,
        strategy: StrategyConfig,
    ) -> dict[str, int]:
        """计算目标持仓股数"""
        target_positions = {}
        total_asset = account.total_asset

        # bug 6 fix: max_position_pct 与 topk 冲突时的处理。
        # 例：topk=5 等权 → 每只 0.2，被 cap=0.15 砍削后总和 0.75 → 25% 永久空仓。
        # n * cap < 1 说明单票上限与持仓数在数学上无法同时满足，此时以「投满」
        # 为优先，把 cap 放宽到 1/n —— 否则用户设了 topk=5 却永远只有 75% 仓位，
        # 且没有任何提示。cap 仍对个别超配标的（score_weighted 下）生效。
        cap = strategy.max_position_pct
        if strategy.renormalize_weights and weights:
            n = len(weights)
            if n > 0 and n * cap < 1.0:
                relaxed = 1.0 / n
                logger.info(
                    "RebalanceCalculator: max_position_pct=%.4f 与 topk=%d 冲突"
                    "（上限合计 %.2f < 1），放宽单票上限至 %.4f 以避免资金闲置",
                    cap, n, n * cap, relaxed,
                )
                cap = relaxed
            weights = self._waterfill_weights(weights, cap)

        for sig in signals:
            weight = weights.get(sig.symbol, 0)
            if weight <= 0:
                continue

            # 单只股票最大仓位限制
            effective_weight = min(weight, cap)
            target_value = total_asset * effective_weight

            quote = quotes.get(sig.symbol)
            if not quote or quote.current_price <= 0:
                continue

            # 计算目标股数（向下取整到整手）
            raw_quantity = target_value / quote.current_price
            lot_quantity = self._floor_to_lot(raw_quantity, strategy.lot_size)

            if lot_quantity > 0:
                target_positions[sig.symbol] = lot_quantity

        return target_positions

    @staticmethod
    def _waterfill_weights(
        weights: dict[str, float],
        cap: float,
        max_rounds: int = 32,
    ) -> dict[str, float]:
        """把超过 cap 的权重溢出量重新分配给未触顶标的，保持总和不变。

        调用方需保证 len(weights) * cap >= 总和，否则全部触顶后溢出量无处安放
        （_calc_target_positions 通过放宽 cap 到 1/n 来保证这一点）。
        """
        total = sum(weights.values())
        if total <= 0:
            return weights
        n = len(weights)
        if n * cap <= total:
            # 容量确实不足（调用方未放宽 cap），全部触顶
            return dict.fromkeys(weights, cap)

        out = dict(weights)
        for _ in range(max_rounds):
            overflow = 0.0
            free: list[str] = []
            for sym, w in out.items():
                if w > cap:
                    overflow += w - cap
                    out[sym] = cap
                elif w < cap:
                    free.append(sym)
            if overflow <= 1e-12 or not free:
                break
            share = overflow / len(free)
            for sym in free:
                out[sym] += share
        return out

    def _floor_to_lot(self, quantity: float, lot_size: int = 100) -> int:
        """向下取整到整手"""
        if quantity <= 0:
            return 0
        return int(quantity // lot_size) * lot_size

    def _generate_orders(
        self,
        current_positions: dict[str, dict[str, Any]],
        target_positions: dict[str, int],
        quotes: dict[str, Quote],
        score_order: list[str] | None = None,
        force_exit_on_limit_down: bool = False,
    ) -> list[Order]:
        """
        生成调仓指令（先卖后买）。

        逻辑：
        1. 先计算需要卖出的股票（当前持有但不在目标中，或目标数量小于当前）
        2. 再计算需要买入的股票（目标中有但当前没有，或目标数量大于当前）

        score_order 非空时，买单按该顺序生成（bug 5 fix：现金不足时被拒的
        是分数最低的，结果可复现）。为 None 时沿用原 set 遍历行为。

        force_exit_on_limit_down=True 时，跌停的待清仓持仓仍生成卖单
        （bug 4 fix：让撮合层显式拒绝并留下 LIMIT_DOWN 记录，而非计算阶段静默丢弃）。
        """
        sell_orders: list[Order] = []
        buy_orders: list[Order] = []

        current_symbols = sorted(current_positions.keys())

        # 需要卖出的股票
        for symbol in current_symbols:
            current_pos = current_positions.get(symbol, {})
            current_qty = int(float(current_pos.get("volume", 0) or 0))
            target_qty = target_positions.get(symbol, 0)

            if current_qty > target_qty:
                sell_qty = current_qty - target_qty
                # T+1: 可卖量钳制
                available = current_pos.get("available_volume")
                if available is not None:
                    sell_qty = min(sell_qty, int(float(available)))
                quote = quotes.get(symbol)
                price = quote.current_price if quote else 0

                # bug 4 fix: 跌停持仓也下单，交由撮合层拒绝以留下痕迹
                if sell_qty > 0 and price <= 0 and force_exit_on_limit_down:
                    pre = current_pos.get("price") or current_pos.get("cost")
                    if pre:
                        price = float(pre)

                if sell_qty > 0 and price > 0:
                    sell_orders.append(Order(
                        symbol=symbol,
                        side="SELL",
                        quantity=sell_qty,
                        price=price,
                        reason=f"调仓卖出: 当前{current_qty} → 目标{target_qty}",
                    ))

        # 需要买入的股票 —— 按 score 降序保证可复现
        if score_order:
            buy_symbols = [s for s in score_order if s in target_positions]
        else:
            buy_symbols = list(target_positions.keys())

        for symbol in buy_symbols:
            target_qty = target_positions.get(symbol, 0)
            current_pos = current_positions.get(symbol, {})
            current_qty = int(float(current_pos.get("volume", 0) or 0))

            if target_qty > current_qty:
                buy_qty = target_qty - current_qty
                quote = quotes.get(symbol)
                price = quote.current_price if quote else 0

                if buy_qty > 0 and price > 0:
                    buy_orders.append(Order(
                        symbol=symbol,
                        side="BUY",
                        quantity=buy_qty,
                        price=price,
                        reason=f"调仓买入: 当前{current_qty} → 目标{target_qty}",
                    ))

        # 先卖后买
        return sell_orders + buy_orders


rebalance_calculator = RebalanceCalculator()
