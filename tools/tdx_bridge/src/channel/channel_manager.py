import asyncio
import logging

from ..core.trade_plan import TradePlan
from .file_sync import FileSyncChannel
from .http_client import HttpBridgeClient, HttpBridgeError

log = logging.getLogger(__name__)


class ChannelManager:
    """双通道编排: 优先 HTTP, 失败自动切换文件通道, HTTP 恢复后自动切回."""

    def __init__(self, http: HttpBridgeClient, file_sync: FileSyncChannel,
                 mode: str = "auto", max_retries: int = 3,
                 retry_delay: float = 1.0,
                 health_interval: float = 10.0):
        self.http = http
        self.file_sync = file_sync
        self.mode = mode
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_interval = health_interval
        self.http_healthy = True
        self._health_task = None

    async def start(self):
        if self.mode in ("auto", "http"):
            self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self):
        if self._health_task:
            self._health_task.cancel()

    async def _health_loop(self):
        while True:
            try:
                self.http.health()
                if not self.http_healthy:
                    log.info("HTTP 桥已恢复")
                self.http_healthy = True
            except Exception:
                if self.http_healthy:
                    log.warning("HTTP 桥不可用, 切换文件通道")
                self.http_healthy = False
            await asyncio.sleep(self.health_interval)

    async def send_plan(self, plan: TradePlan) -> dict:
        if self.mode in ("http", "auto") and self.http_healthy:
            try:
                return await asyncio.to_thread(self._http_send, plan)
            except HttpBridgeError as e:
                if not e.retryable:
                    raise
                log.warning(f"HTTP 发送失败({e.code}), 重试...")
        if self.mode in ("file_sync", "auto"):
            return await self._file_send(plan)
        raise RuntimeError("无可用通道")

    def _http_send(self, plan: TradePlan) -> dict:
        return self.http.execute_plan(plan)

    async def _file_send(self, plan: TradePlan) -> dict:
        self.file_sync.write_plan(plan)
        try:
            report = await self.file_sync.wait_report(plan.plan_id, plan.timeout_seconds)
            return report
        except TimeoutError as e:
            return {"plan_id": plan.plan_id, "status": "timeout",
                    "message": str(e), "channel_used": "file_sync"}
