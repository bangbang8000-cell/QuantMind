import logging
from typing import List, Optional

from ..core.trade_plan import Order, TradePlan
from ..core.types import Side

log = logging.getLogger(__name__)


def signal_to_order(stock_code: str, side: str, volume: int,
                    price: Optional[float] = None,
                    stop_loss_pct: Optional[float] = None,
                    take_profit_pct: Optional[float] = None,
                    trailing_stop_pct: Optional[float] = None) -> Order:
    """把 QuandMind 的买卖信号转换为订单."""
    if side not in (Side.BUY.value, Side.SELL.value):
        raise ValueError(f"非法方向: {side}")
    if volume <= 0:
        raise ValueError(f"非法数量: {volume}")
    if not stock_code:
        raise ValueError("缺少股票代码")
    return Order(
        stock_code=stock_code, side=side, volume=volume,
        price=price, price_type=0 if price else 1,
        order_type="limit" if price else "market",
        stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
        trailing_stop_pct=trailing_stop_pct,
    )


def build_plan(signals: List[dict], account: str = "", account_type: str = "stock",
               source: str = "quandmind") -> TradePlan:
    """从信号列表构建 TradePlan. signals 元素: {code, side, volume, price?, sl?, tp?, trail?}"""
    orders = []
    for s in signals:
        orders.append(signal_to_order(
            s["code"], s["side"], s["volume"],
            price=s.get("price"),
            stop_loss_pct=s.get("sl"),
            take_profit_pct=s.get("tp"),
            trailing_stop_pct=s.get("trail")))
    import time
    return TradePlan(plan_id=f"plan_{int(time.time())}_{id(orders) % 10000}",
                     orders=orders, account=account, account_type=account_type,
                     source=source)
