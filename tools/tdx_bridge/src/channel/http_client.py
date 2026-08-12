import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from ..core.trade_plan import TradePlan
from ..utils.retry import with_retry

log = logging.getLogger(__name__)


class HttpBridgeError(Exception):
    def __init__(self, message: str, code: str = "HTTP_ERROR", status: int = 500,
                 retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


class HttpBridgeClient:
    """Linux 侧 HTTP 桥客户端, 请求 Windows :8550."""

    def __init__(self, host: str, port: int, token: str, timeout: float = 30.0):
        self.base = f"http://{host}:{port}/api/v1"
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        url = f"{self.base}{path}"
        data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8"))
                code = err.get("error", {}).get("code", "HTTP_ERROR")
                msg = err.get("error", {}).get("message", str(e))
            except Exception:
                code, msg = "HTTP_ERROR", str(e)
            retryable = e.code in (500, 502, 503, 504)
            raise HttpBridgeError(msg, code, e.code, retryable) from e
        except (urllib.error.URLError, OSError) as e:
            raise HttpBridgeError(f"连接失败: {e}", "CONNECTION_ERROR", 0, True) from e

    @with_retry(max_retries=1, base_delay=0.5, retryable_exceptions=(HttpBridgeError,))
    def _request_with_retry(self, method: str, path: str, body: dict = None) -> dict:
        try:
            return self._request(method, path, body)
        except HttpBridgeError as e:
            if not e.retryable:
                raise
            raise

    # ---- 对外 API ----

    def health(self) -> dict:
        return self._request("GET", "/health")

    def execute_plan(self, plan: TradePlan) -> dict:
        return self._request_with_retry("POST", "/plans/execute", plan.to_dict())

    def query_account(self, account: str = "", account_type: str = "stock") -> dict:
        return self._request_with_retry("POST", "/account/query",
                                        {"account": account, "account_type": account_type})

    def query_orders(self, account: str = "", account_type: str = "stock",
                     stock_code: str = "", cancelable_only: bool = False) -> dict:
        return self._request_with_retry("POST", "/orders/query", {
            "account": account, "account_type": account_type,
            "stock_code": stock_code, "cancelable_only": cancelable_only})

    def cancel_order(self, account: str = "", account_type: str = "stock",
                     stock_code: str = "", order_id: str = "") -> dict:
        return self._request_with_retry("POST", "/orders/cancel", {
            "account": account, "account_type": account_type,
            "stock_code": stock_code, "order_id": order_id})

    def configure_sltp(self, items: list) -> dict:
        return self._request_with_retry("POST", "/sltp/configure", {"items": items})

    def sltp_state(self) -> dict:
        return self._request("GET", "/sltp/state")
