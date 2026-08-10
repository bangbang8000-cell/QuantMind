"""训练编排器抽象基类 + 工厂。

LocalDockerOrchestrator（本地 Docker-in-Docker）与 RemoteSSHOrchestrator
（AutoDL 远程 GPU）实现同一接口，调用方通过 get_orchestrator(node_id) 获取，
本地/远端可无缝切换。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TrainingOrchestrator(ABC):
    """训练编排器基类。子类必须实现单周期/多周期训练。"""

    @abstractmethod
    async def launch_training_job(self, run_id: str, payload: dict | None = None) -> None:
        """编排单周期训练任务（推送数据 → 训练 → 注册模型）。"""

    @abstractmethod
    async def launch_multi_horizon_job(
        self, parent_run_id: str, child_run_ids: list[str], payload: dict | None = None
    ) -> None:
        """编排多周期训练（串行跑各 child，全部成功后创建融合模型）。"""


def get_orchestrator(node_id: str | None = None) -> TrainingOrchestrator:
    """根据 node_id 返回对应训练编排器。

    - node_id 为空 / "local" → LocalDockerOrchestrator（默认，现有逻辑）
    - node_id 以 "autodl" 开头 → RemoteSSHOrchestrator（AutoDL 远程 GPU）
    """
    if node_id and node_id.startswith("autodl"):
        from backend.services.engine.training.remote_ssh_orchestrator import RemoteSSHOrchestrator

        return RemoteSSHOrchestrator(node_id=node_id)
    from backend.services.engine.training.local_docker_orchestrator import LocalDockerOrchestrator

    return LocalDockerOrchestrator()


# 便于类型标注 / 前端感知
LOCAL_NODE_ID = "local"
