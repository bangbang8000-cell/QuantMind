"""
Trade API 客户端 - 统一封装 QuantMind 模拟盘 + 实盘交易接口

所有请求走 QuantMind trade 服务 (8002)，不再直连通达信桥。
实盘通过后端 trading_engine → TdxBroker → Windows 桥 → 通达信。
使用 httpx (延迟导入), 失败返回空结构, 不抛异常 (遵循 dashboard 现有模式)。
"""
import logging
import os

logger = logging.getLogger(__name__)

TRADE_SERVICE_URL = os.getenv("TRADE_SERVICE_URL", "http://127.0.0.1:8002")

TIMEOUT = 10.0


def _client():
    """延迟导入 httpx, 避免容器缺依赖时页面整体崩溃."""
    import httpx
    return httpx


def _auth_headers(token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ============================================================
# 登录
# ============================================================

def login(api_url: str, tenant_id: str, username: str, password: str) -> str | None:
    """调用 api 网关登录, 返回 access_token; 失败返回 None."""
    try:
        resp = _client().post(
            f"{api_url}/api/v1/auth/login",
            json={"tenant_id": tenant_id, "username": username, "password": password},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("登录失败: HTTP %s", resp.status_code)
            return None
        return resp.json().get("access_token")
    except _client().HTTPError as e:
        logger.warning("登录请求异常: %s", e)
        return None


# ============================================================
# 模拟盘 API (/api/v1/simulation/*)
# ============================================================

def get_simulation_account(token: str) -> dict:
    """查模拟盘账户."""
    try:
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/simulation/account",
            headers=_auth_headers(token),
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json().get("data", {})
        if data.get("account_not_initialized"):
            return {"cash": 0.0, "total_asset": 0.0, "market_value": 0.0,
                    "positions": {}, "initial_equity": 0.0}
        return data
    except _client().HTTPError as e:
        logger.warning("查模拟账户失败: %s", e)
        return {}


def create_simulation_order(token: str, symbol: str, side: str,
                            order_type: str, quantity: float,
                            price: float | None = None) -> dict:
    """模拟盘下单."""
    payload = {
        "symbol": symbol,
        "side": side.upper(),
        "order_type": order_type.upper(),
        "quantity": quantity,
        "trading_mode": "SIMULATION",
    }
    if price:
        payload["price"] = price
    try:
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/simulation/orders",
            json=payload,
            headers=_auth_headers(token),
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"success": False, "message": f"HTTP {resp.status_code}: {detail}"}
        data = resp.json()
        return {"success": True, "data": data,
                "message": f"订单 {data.get('order_id', '')} 已提交"}
    except _client().HTTPError as e:
        logger.warning("模拟下单失败: %s", e)
        return {"success": False, "message": f"连接失败: {e}"}


def list_simulation_orders(token: str) -> list:
    """查模拟盘今日委托."""
    try:
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/simulation/orders",
            headers=_auth_headers(token),
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        return resp.json() or []
    except _client().HTTPError as e:
        logger.warning("查模拟委托失败: %s", e)
        return []


def cancel_simulation_order(token: str, order_id) -> dict:
    """撤模拟盘委托."""
    try:
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/simulation/orders/{order_id}/cancel",
            headers=_auth_headers(token),
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            return {"success": False, "message": f"HTTP {resp.status_code}"}
        return {"success": True, "message": "已撤单"}
    except _client().HTTPError as e:
        return {"success": False, "message": str(e)}


# ============================================================
# 实盘 API (/api/v1/real-trading/*) — 后端 → TdxBroker → 通达信
# ============================================================

def get_real_account(token: str, user_id: str = "") -> dict:
    """查实盘账户 (通达信快照)."""
    try:
        params = {"user_id": user_id} if user_id else {}
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/account",
            headers=_auth_headers(token),
            params=params,
            timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return {"error": "账户信息尚未持久化"}
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        return resp.json() or {}
    except _client().HTTPError as e:
        logger.warning("查实盘账户失败: %s", e)
        return {"error": f"连接失败: {e}"}


def get_real_orders(token: str, user_id: str = "") -> dict:
    """查实盘委托 (通达信当日委托)."""
    try:
        params = {"user_id": user_id} if user_id else {}
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/orders",
            headers=_auth_headers(token),
            params=params,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {"orders": [], "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        if isinstance(data, list):
            return {"orders": data}
        return data if isinstance(data, dict) else {"orders": []}
    except _client().HTTPError as e:
        return {"orders": [], "error": f"连接失败: {e}"}


def get_strategy_status(token: str, user_id: str = "") -> dict:
    """查策略/交易运行状态."""
    try:
        params = {"user_id": user_id} if user_id else {}
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/status",
            headers=_auth_headers(token),
            params=params,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        return resp.json() or {}
    except _client().HTTPError as e:
        return {"error": f"连接失败: {e}"}


def start_strategy(token: str, trading_mode: str = "SIMULATION",
                   strategy_id: str = "", user_id: str = "") -> dict:
    """启动策略. trading_mode: SIMULATION / REAL."""
    form = {"trading_mode": trading_mode}
    if strategy_id:
        form["strategy_id"] = strategy_id
    if user_id:
        form["user_id"] = user_id
    try:
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/start",
            data=form,
            headers=_auth_headers(token),
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"success": False, "message": f"HTTP {resp.status_code}: {detail}"}
        return {"success": True, "data": resp.json() or {}, "message": "策略已启动"}
    except _client().HTTPError as e:
        return {"success": False, "message": f"连接失败: {e}"}


def stop_strategy(token: str, user_id: str = "") -> dict:
    """停止策略."""
    try:
        form = {"user_id": user_id} if user_id else {}
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/stop",
            data=form,
            headers=_auth_headers(token),
            timeout=30,
        )
        if resp.status_code >= 400:
            return {"success": False, "message": f"HTTP {resp.status_code}"}
        return {"success": True, "message": "策略已停止"}
    except _client().HTTPError as e:
        return {"success": False, "message": f"连接失败: {e}"}


def preview_execution(token: str, model_id: str, run_id: str,
                      strategy_id: str, trading_mode: str = "SIMULATION",
                      note: str = "") -> dict:
    """构建调仓预案预览 (不提交)."""
    payload = {
        "model_id": model_id,
        "run_id": run_id,
        "strategy_id": strategy_id,
        "trading_mode": trading_mode,
    }
    if note:
        payload["note"] = note
    try:
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/manual-executions/preview",
            json=payload,
            headers=_auth_headers(token),
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"success": False, "message": f"HTTP {resp.status_code}: {detail}"}
        data = resp.json()
        return {"success": True, "data": data}
    except _client().HTTPError as e:
        return {"success": False, "message": f"连接失败: {e}"}


def submit_execution(token: str, model_id: str, run_id: str,
                     strategy_id: str, trading_mode: str = "SIMULATION",
                     preview_hash: str = "", note: str = "") -> dict:
    """提交手动执行任务."""
    payload = {
        "model_id": model_id,
        "run_id": run_id,
        "strategy_id": strategy_id,
        "trading_mode": trading_mode,
    }
    if preview_hash:
        payload["preview_hash"] = preview_hash
    if note:
        payload["note"] = note
    try:
        resp = _client().post(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/manual-executions",
            json=payload,
            headers=_auth_headers(token),
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"success": False, "message": f"HTTP {resp.status_code}: {detail}"}
        data = resp.json()
        return {"success": True, "data": data,
                "message": f"任务 {data.get('task_id', '')} 已创建"}
    except _client().HTTPError as e:
        return {"success": False, "message": f"连接失败: {e}"}


def list_executions(token: str, user_id: str = "") -> list:
    """列出手动/托管执行任务."""
    try:
        params = {"user_id": user_id} if user_id else {}
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/manual-executions",
            headers=_auth_headers(token),
            params=params,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except _client().HTTPError as e:
        logger.warning("查执行任务失败: %s", e)
        return []


def get_task_logs(token: str, task_id: str, after_id: int = 0) -> dict:
    """获取执行任务日志."""
    try:
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/real-trading/manual-executions/{task_id}/logs",
            headers=_auth_headers(token),
            params={"after_id": after_id} if after_id else {},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {"logs": []}
        data = resp.json()
        return data if isinstance(data, dict) else {"logs": []}
    except _client().HTTPError as e:
        return {"logs": [], "error": str(e)}


def list_signals(token: str, limit: int = 20) -> list:
    """读取最近推理信号 (engine_signal_scores 简化). 失败返回空."""
    try:
        resp = _client().get(
            f"{TRADE_SERVICE_URL}/api/v1/simulation/signals",
            headers=_auth_headers(token),
            params={"limit": limit},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except _client().HTTPError as e:
        logger.warning("查信号失败: %s", e)
        return []
