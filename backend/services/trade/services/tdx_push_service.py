"""
TdxPushService - QuantMind ↔ 通达信 双向推送服务

推送 (Q→T): 选股信号写板块 / 预警信号 / 文本消息 / 策略源码 / 交易下单
拉取 (T→Q): 账户资产 / 持仓明细 / 当日委托 / 单笔委托状态 / 盈亏计算

所有请求经 Windows 桥 (TDX_BRIDGE_URL:8550) 转发到通达信客户端。
受 ENABLE_TDX_PUSH 开关控制, 未配置 token 时安全降级不报错。
"""
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

TDX_BRIDGE_URL = os.getenv("TDX_BRIDGE_URL", "http://192.168.31.39:8550")
TDX_BRIDGE_TOKEN = os.getenv("TDX_BRIDGE_TOKEN", "")
TIMEOUT = 10.0


class TdxPushError(Exception):
    """通达信推送失败"""


class TdxPushService:
    def __init__(self, bridge_url: str = "", bridge_token: str = ""):
        self.bridge_url = str(bridge_url or TDX_BRIDGE_URL).rstrip("/")
        self.bridge_token = str(bridge_token or TDX_BRIDGE_TOKEN).strip()
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.bridge_url) and bool(self.bridge_token)

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.bridge_token}",
        }

    async def _client_http(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=TIMEOUT)
        return self._client

    async def _post(self, path: str, payload: dict) -> dict:
        if not self.enabled:
            logger.warning("[TdxPush] TDX_BRIDGE_URL/TOKEN 未配置, 跳过 %s", path)
            raise TdxPushError("TDX_BRIDGE_URL/TOKEN 未配置")
        client = await self._client_http()
        resp = await client.post(
            f"{self.bridge_url}{path}", json=payload, headers=self._headers())
        if resp.status_code != 200:
            raise TdxPushError(f"桥返回 HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    # ============ 推送 (Q→T) ============

    async def push_signals_to_block(self, stocks: list, block_code: str = "",
                                    block_name: str = "QuantMind今日选股",
                                    show: bool = True) -> dict:
        """把选股结果写入通达信自定义板块."""
        return await self._post("/api/v1/push/block", {
            "block_code": block_code, "stocks": stocks, "show": show})

    async def push_warnings(self, signals: list[dict]) -> dict:
        """推送买卖预警信号 (通达信支持双击闪电下单).

        signals 元素: {symbol, side(buy/sell), price, close, volume, reason}
        """
        stock_list = [s.get("symbol", "") for s in signals]
        bs_map = {"buy": "0", "sell": "1"}
        return await self._post("/api/v1/push/warnings", {
            "stock_list": stock_list,
            "price_list": [str(s.get("price", "0")) for s in signals],
            "close_list": [str(s.get("close", "0")) for s in signals],
            "volum_list": [str(s.get("volume", "0")) for s in signals],
            "bs_flag_list": [bs_map.get(str(s.get("side", "")).lower(), "2") for s in signals],
            "warn_type_list": ["1"] * len(signals),
            "reason_list": [s.get("reason", "")[:25] for s in signals],
            "count": len(signals),
        })

    async def push_message(self, msg: str) -> dict:
        """推送文本消息到通达信界面."""
        return await self._post("/api/v1/push/message", {"msg": msg})

    async def push_source(self, py_code: str, handle_type: int = 0) -> dict:
        """推送策略源码到通达信云回测平台."""
        return await self._post("/api/v1/push/source", {
            "py_code": py_code, "handle_type": handle_type})

    async def place_order(self, stock_code: str, side: str, volume: int,
                          price: Optional[float] = None,
                          price_type: Optional[int] = None,
                          plan_id: str = "") -> dict:
        """通过桥下单到通达信."""
        order = {
            "stock_code": stock_code,
            "side": side,
            "volume": volume,
            "order_type": "limit" if price else "market",
            "price_type": price_type if price_type is not None else (0 if price else 1),
            "price": price,
        }
        return await self._post("/api/v1/plans/execute", {
            "plan_id": plan_id or f"qm_{int(__import__('time').time())}",
            "orders": [order],
        })

    # ============ 拉取 (T→Q) ============

    async def pull_account(self) -> dict:
        """拉取通达信账户资产."""
        data = await self._post("/api/v1/account/query", {})
        return data.get("asset", {})

    async def pull_positions(self) -> list:
        """拉取通达信持仓明细."""
        data = await self._post("/api/v1/account/query", {})
        return data.get("positions", [])

    async def pull_orders(self, stock_code: str = "") -> list:
        """拉取通达信当日委托."""
        data = await self._post("/api/v1/orders/query", {"stock_code": stock_code})
        return data.get("orders", [])

    async def pull_order_status(self, wtbh: str) -> dict:
        """按委托编号查单笔委托状态."""
        orders = await self.pull_orders()
        for o in orders:
            if str(o.get("order_id", "")) == str(wtbh):
                return o
        return {}

    async def pull_pnl(self) -> dict:
        """拉取账户并计算盈亏.

        返回: {total_asset, cash, market_value, balance, positions, pnl_by_pos, total_pnl}
        """
        data = await self._post("/api/v1/account/query", {})
        asset = data.get("asset", {})
        positions = data.get("positions", [])
        pnl_list = []
        total_pnl = 0.0
        for p in positions:
            cost = float(p.get("cost_price", 0) or 0)
            # 成本价 x 总持仓 与 持仓市值 的差
            market_value = float(p.get("market_value", 0) or 0)
            pnl = market_value - cost * float(p.get("total_volume", 0) or 0)
            pnl_list.append({"stock_code": p.get("stock_code", ""),
                             "cost_price": cost,
                             "volume": p.get("total_volume", 0),
                             "market_value": market_value,
                             "pnl": round(pnl, 2)})
            total_pnl += pnl
        return {
            "total_asset": asset.get("asset", 0),
            "cash": asset.get("cash", 0),
            "market_value": asset.get("market_value", 0),
            "balance": asset.get("balance", 0),
            "positions": pnl_list,
            "total_pnl": round(total_pnl, 2),
        }

    async def check_order_success(self, wtbh: str) -> dict:
        """检查下单是否成功.

        返回: {wtbh, status_code, status_text, filled, all_filled}
          status_code: 0无效/1未成交/2部分成交/3全部成交/4部分撤/5全撤
        """
        order = await self.pull_order_status(wtbh)
        if not order:
            return {"wtbh": wtbh, "status_code": -1, "status_text": "未找到", "filled": False}
        code = int(order.get("status", -1))
        status_map = {0: "无效单", 1: "未成交", 2: "部分成交", 3: "全部成交",
                      4: "部分成交部分撤单", 5: "全部撤单"}
        filled = code in (2, 3)
        return {
            "wtbh": wtbh,
            "status_code": code,
            "status_text": status_map.get(code, "未知"),
            "filled": filled,
            "all_filled": code == 3,
            "filled_price": order.get("filled_price", 0),
            "filled_volume": order.get("filled_volume", 0),
        }


# 全局单例
tdx_pusher = TdxPushService()
