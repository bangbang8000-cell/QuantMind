import asyncio
import json
import logging
import os
import time
from datetime import datetime

from ..core.trade_plan import TradePlan

log = logging.getLogger(__name__)


class FileSyncChannel:
    """Linux 侧文件通道: 写计划到 pending/, 轮询 execution_reports/ 读取结果."""

    def __init__(self, shared_dir: str, poll_interval: float = 0.5,
                 report_timeout: float = 300.0):
        self.shared_dir = shared_dir
        self.pending_dir = os.path.join(shared_dir, "trade_plans", "pending")
        self.report_dir = os.path.join(shared_dir, "execution_reports")
        self.poll_interval = poll_interval
        self.report_timeout = report_timeout
        os.makedirs(self.pending_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)

    def write_plan(self, plan: TradePlan) -> str:
        """写入计划文件, 返回文件名."""
        fname = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}.json"
        path = os.path.join(self.pending_dir, fname)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        log.info(f"计划 {plan.plan_id} 已写入 {path}")
        return path

    async def wait_report(self, plan_id: str, timeout: float = None) -> dict:
        """轮询等待指定 plan_id 的执行报告."""
        deadline = time.monotonic() + (timeout or self.report_timeout)
        start_mtime = self._report_max_mtime()
        while time.monotonic() < deadline:
            report = self._find_report(plan_id, start_mtime)
            if report:
                return report
            await asyncio.sleep(self.poll_interval)
        raise TimeoutError(f"等待执行报告超时: {plan_id}")

    def _report_max_mtime(self) -> float:
        try:
            files = [os.path.join(self.report_dir, f)
                     for f in os.listdir(self.report_dir) if f.endswith(".json")]
            return max(os.path.getmtime(f) for f in files) if files else 0.0
        except OSError:
            return 0.0

    def _find_report(self, plan_id: str, min_mtime: float = 0.0) -> dict:
        try:
            for fname in os.listdir(self.report_dir):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(self.report_dir, fname)
                try:
                    if os.path.getmtime(path) < min_mtime:
                        continue
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("plan_id") == plan_id:
                        return data
                except (OSError, ValueError):
                    continue
        except OSError:
            pass
        return None
