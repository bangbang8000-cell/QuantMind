"""AutoDL 远程 GPU 训练编排器。

通过 SSH/rsync/scp 驱动远端 AutoDL 节点执行训练：
  1. rsync 推送特征快照（按训练区间选年）到远端
  2. rsync 推送 config.yaml
  3. ssh 远端 docker run 启动训练容器（复用 train.py）
  4. 轮询远端容器日志，解析进度推送到 Redis（与本地一致）
  5. 训练完成后 scp 拉取模型产物到本地工作目录
  6. 走现有模型注册流程（register_model_from_training_run）

依赖：系统 ssh/scp/rsync 命令行（asyncio.create_subprocess_exec），零额外 Python 依赖。
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from backend.services.engine.training.orchestrator_base import TrainingOrchestrator
from backend.services.engine.training.training_log_stream import TrainingRunLogStream
from backend.services.api.training_explain import DEFAULT_EXPLAIN_CFG

logger = logging.getLogger(__name__)


def _env_or(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


class RemoteSSHOrchestrator(TrainingOrchestrator):
    """AutoDL 远程 GPU 训练编排器。

    配置来源（环境变量）：
      TRAINING_AUTODL_HOST          远端 IP/域名
      TRAINING_AUTODL_SSH_PORT      SSH 端口（默认 22）
      TRAINING_AUTODL_USER          SSH 用户（默认 root）
      TRAINING_AUTODL_SSH_KEY       SSH 私钥路径（可选，默认 ~/.ssh/id_rsa）
      TRAINING_AUTODL_WORK_DIR      远端工作目录（默认 /workspace）
      TRAINING_AUTODL_DOCKER_IMAGE  远端训练镜像（默认 quantmind-oss:latest）
      TRAINING_AUTODL_NODE_NAME     节点标识（默认 autodl-1）
    """

    _POLL_INTERVAL = 10  # 容器状态轮询间隔（秒）
    _LOG_TAIL_LINES = 60

    def __init__(self, node_id: str = "autodl-1"):
        self.node_id = node_id
        self.host = _env_or("TRAINING_AUTODL_HOST", "")
        self.port = int(_env_or("TRAINING_AUTODL_SSH_PORT", "22"))
        self.user = _env_or("TRAINING_AUTODL_USER", "root")
        self.ssh_key = _env_or("TRAINING_AUTODL_SSH_KEY", "")
        self.ssh_password = _env_or("TRAINING_AUTODL_SSH_PASSWORD", "")
        self.work_dir = _env_or("TRAINING_AUTODL_WORK_DIR", "/workspace")
        self.docker_image = _env_or("TRAINING_AUTODL_DOCKER_IMAGE", "quantmind-oss:latest")
        self.api_base = _env_or("QUANTMIND_API_BASE_URL", "http://quantmind-api:8000")
        self.internal_secret = _env_or("INTERNAL_CALL_SECRET", "")
        self.log_stream = TrainingRunLogStream()

        if not self.host:
            raise ValueError(
                "TRAINING_AUTODL_HOST 未配置，无法使用远程训练。请先在 .env 设置 AutoDL 节点 IP。"
            )

    # ── SSH 基础工具（asyncio subprocess，零额外依赖） ──────────────────────────

    def _auth_prefix(self) -> list[str]:
        """SSH 认证前缀：密码用 sshpass，否则用 key。"""
        if self.ssh_password:
            return ["sshpass", "-p", self.ssh_password]
        return []

    def _ssh_base_args(self) -> list[str]:
        args = self._auth_prefix() + [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-p", str(self.port),
        ]
        if self.ssh_key:
            args += ["-i", self.ssh_key]
        args.append(f"{self.user}@{self.host}")
        return args

    async def _ssh_exec(self, cmd: str, *, timeout: int = 900) -> tuple[int, str, str]:
        """SSH 执行远端命令。返回 (exit_code, stdout, stderr)。"""
        proc = await asyncio.create_subprocess_exec(
            *self._ssh_base_args(),
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise
        return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def _rsync_push(self, local_path: str, remote_dir: str, *, is_dir: bool = False) -> None:
        """rsync 推送本地文件/目录到远端目录。"""
        ssh_opt = f"ssh -o StrictHostKeyChecking=no -p {self.port}"
        if self.ssh_password:
            ssh_opt = f"sshpass -p {self.ssh_password} " + ssh_opt
        elif self.ssh_key:
            ssh_opt += f" -i {self.ssh_key}"
        cmd = [
            "rsync", "-avz", "--partial",
            "-e", ssh_opt,
        ]
        if is_dir:
            cmd += ["--delete"]
        src = local_path.rstrip("/") + ("/" if is_dir else "")
        dst = f"{self.user}@{self.host}:{remote_dir}"
        proc = await asyncio.create_subprocess_exec(
            *cmd, src, dst,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

    async def _scp_pull(self, remote_file: str, local_dir: Path) -> None:
        """scp 拉取远端单个文件到本地目录（幂等，文件不存在则跳过）。"""
        local_dir.mkdir(parents=True, exist_ok=True)
        cmd = self._auth_prefix() + [
            "scp", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-p", str(self.port),
        ]
        if self.ssh_key:
            cmd += ["-i", self.ssh_key]
        cmd += [f"{self.user}@{self.host}:{remote_file}", str(local_dir)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

    async def launch_multi_horizon_job(
        self, parent_run_id: str, child_run_ids: list[str], payload: dict | None = None
    ) -> None:
        """远端多周期训练：串行跑各子任务（每周期一次远端训练），全部成功后融合。

        简化实现：逐个子任务走 launch_training_job，融合逻辑复用本地编排器。
        """
        from backend.services.engine.training.local_docker_orchestrator import LocalDockerOrchestrator

        # 多周期融合需要本地聚合产物；远端各子任务模型先各自注册，
        # 融合模型由 LocalDockerOrchestrator.launch_multi_horizon_job 编排。
        # 这里退化：远端只跑单周期，多周期走本地（避免远端融合复杂度）。
        logger.warning(
            "[%s] 多周期训练当前仅支持本地节点，回退到本地编排（node=%s）",
            parent_run_id, self.node_id,
        )
        local = LocalDockerOrchestrator()
        await local.launch_multi_horizon_job(parent_run_id, child_run_ids, payload)

    async def test_connection(self) -> dict:
        """测试 SSH 连接 + 远端 docker 可用性。"""
        results = {}
        code, out, err = await self._ssh_exec("echo OK && docker --version 2>&1 | head -1")
        results["ssh"] = code == 0 and "OK" in out
        results["docker"] = code == 0 and "Docker" in (out + err)
        if code == 0:
            results["host"] = self.host
            results["detail"] = (out + err).strip()
        else:
            results["error"] = (err or out).strip()
        return results

    # ── 训练编排 ───────────────────────────────────────────────────────────────

    async def launch_training_job(self, run_id: str, payload: dict | None = None) -> None:
        """编排远端训练：推送数据 → 启动容器 → 轮询 → 拉取产物 → 注册。"""
        payload = payload or {}
        self._log(run_id, "[SYSTEM] 远程训练启动（AutoDL），开始同步数据...", status="provisioning", progress=5)

        try:
            # 1. 生成配置（复用本地逻辑，但 local_dir 指向远端挂载点）
            config = self._build_config_yaml(run_id, payload)
            config["data"]["local_dir"] = f"{self.work_dir}/feature_snapshots"
            config["callback"]["url"] = f"{self.api_base}/api/v1/models/training-runs/{run_id}/complete"

            # 2. 确保远端工作目录结构
            await self._ssh_exec(f"mkdir -p {self.work_dir}/feature_snapshots {self.work_dir}/quantdb/2_base_sector")

            # 3. 推送特征快照（按训练区间选年）
            feature_files = self._resolve_feature_files(payload)
            if feature_files:
                self._log(run_id, f"[SYNC] 推送 {len(feature_files)} 个特征快照到 AutoDL...", progress=10)
                for f in feature_files:
                    if Path(f).exists():
                        await self._rsync_push(f, f"{self.work_dir}/feature_snapshots/")
                self._log(run_id, "[SYNC] 特征快照同步完成", progress=15)
            else:
                self._log(run_id, "[SYNC] 未匹配到特征快照文件，跳过", progress=15)

            # 4. 推送 config.yaml + train.py（写临时文件再 rsync）
            self._log(run_id, "[SYNC] 推送训练配置与训练脚本...", progress=18)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
                yaml.safe_dump(config, tf, allow_unicode=True)
                config_local = tf.name
            await self._rsync_push(config_local, f"{self.work_dir}/")
            os.unlink(config_local)

            # 训练脚本 train.py 每次训练都推送最新版并挂载覆盖镜像内置版，
            # 这样更新 train.py 不需要重新打包/上传 AutoDL 镜像。
            train_script = self._resolve_train_script()
            if train_script:
                await self._rsync_push(train_script, f"{self.work_dir}/train.py")
                self._log(run_id, "[SYNC] train.py 已同步（覆盖镜像内置版）")

            # 5. 远端启动训练容器
            self._log(run_id, "[SYSTEM] 在 AutoDL 启动训练容器...", progress=20)
            container_name = f"qm-train-{run_id}"
            docker_cmd = self._build_docker_run_cmd(container_name)
            code, out, err = await self._ssh_exec(docker_cmd, timeout=120)
            if code != 0:
                raise RuntimeError(f"远端 docker run 失败: {err or out}")
            container_id = (out or "").strip()[:12]
            self._log(run_id, f"[SYSTEM] 训练容器已启动: {container_name} ({container_id})", progress=22)

            # 6. 后台轮询训练进度
            asyncio.create_task(
                self._poll_remote(run_id, container_name),
                name=f"training-remote-{run_id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] 远程训练编排失败: %s", run_id, exc, exc_info=True)
            self._log(run_id, f"[ERROR] 远程训练编排失败: {exc}", status="failed", progress=0)

    async def _poll_remote(self, run_id: str, container_name: str) -> None:
        """轮询远端容器日志，解析进度，完成后拉取产物。"""
        seen_lines: set[str] = set()
        progress = 22
        try:
            while True:
                code, out, err = await self._ssh_exec(
                    f"docker logs {container_name} --tail {self._LOG_TAIL_LINES} 2>&1",
                    timeout=120,
                )
                # 进度解析 + 日志去重推送
                for line in (out + err).splitlines():
                    line = line.strip()
                    if not line or line in seen_lines:
                        continue
                    seen_lines.add(line)
                    progress = max(progress, LocalDockerProgress.infer(line, progress))
                    self.log_stream.append_log(run_id=run_id, line=line, progress=progress)

                # 检查容器状态
                code2, status_out, _ = await self._ssh_exec(
                    f"docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null || echo gone",
                    timeout=60,
                )
                status = (status_out or "").strip()
                if status in ("exited", "dead", "gone"):
                    # 拿退出码
                    code3, exit_out, _ = await self._ssh_exec(
                        f"docker inspect -f '{{{{.State.ExitCode}}}}' {container_name} 2>/dev/null || echo -1",
                        timeout=60,
                    )
                    exit_code = (exit_out or "").strip()
                    await self._handle_container_end(run_id, container_name, exit_code)
                    return

                await asyncio.sleep(self._POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] 远程轮询异常: %s", run_id, exc, exc_info=True)
            self._log(run_id, f"[ERROR] 远程轮询异常: {exc}", status="failed", progress=progress)

    async def _handle_container_end(self, run_id: str, container_name: str, exit_code: str) -> None:
        """容器结束后：拉取产物 → 触发注册 → 清理远端。"""
        try:
            if exit_code == "0":
                self._log(run_id, "[SYSTEM] 训练完成，拉取模型产物...", status="waiting_callback", progress=95)
                await self._pull_artifacts(run_id)
                self._log(run_id, "[SYSTEM] 模型产物已回传，等待模型注册...", progress=97)
                # 清理远端容器
                await self._ssh_exec(f"docker rm -f {container_name} 2>/dev/null || true", timeout=60)
                # 触发本地模型注册（与本地流程一致）
                await self._trigger_registration(run_id)
            else:
                self._log(run_id, f"[ERROR] 训练容器异常退出 (exit={exit_code})", status="failed", progress=0)
                await self._ssh_exec(f"docker rm -f {container_name} 2>/dev/null || true", timeout=60)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] 容器结束处理失败: %s", run_id, exc, exc_info=True)
            self._log(run_id, f"[ERROR] 容器结束处理失败: {exc}", status="failed", progress=0)

    async def _pull_artifacts(self, run_id: str) -> None:
        """scp 拉取模型产物到本地工作目录 /data/training_jobs/{run_id}（跳过 pred.* 大文件）。"""
        # 本地训练工作目录（与 LocalDockerOrchestrator 一致，注册流程从这里找产物）
        work_dir = Path("/data") / "training_jobs" / run_id
        work_dir.mkdir(parents=True, exist_ok=True)
        artifacts = [
            "model.lgb", "model.xgb", "model.cbm", "model.pkl", "model.pth",
            "model_xgb.xgb", "model_xgb.pkl", "model_lgb.lgb", "model_lgb.txt",
            "model_cbm.cbm", "model_lin.pkl", "meta_model.pkl", "ensemble_config.json",
            "metadata.json", "config.yaml", "result.json", "inference.py", "shap_summary.csv",
        ]
        for artifact in artifacts:
            await self._scp_pull(f"{self.work_dir}/{artifact}", work_dir)
        self._log(run_id, f"[SYNC] 模型产物已拉取到 {work_dir}")

    async def _trigger_registration(self, run_id: str) -> None:
        """读取本地工作目录的 result.json，调用 complete_training_run 触发模型注册。

        复用现有注册流程（_sync_candidate_artifacts 从 /data/training_jobs/{run_id} 找产物），
        与本地训练完成后的回调路径一致。
        """
        import json

        from backend.services.api.routers.admin.admin_training_utils import complete_training_run

        work_dir = Path("/data") / "training_jobs" / run_id
        result = {}
        result_path = work_dir / "result.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] result.json 解析失败: %s", run_id, exc)

        try:
            await complete_training_run(
                run_id=run_id,
                result=result,
                x_internal_call_secret=self.internal_secret,
            )
            self._log(run_id, "[SYSTEM] 模型注册流程已触发", progress=100)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] 模型注册失败: %s", run_id, exc, exc_info=True)
            self._log(run_id, f"[ERROR] 模型注册失败: {exc}", status="failed")

    # ── 配置 / 工具 ─────────────────────────────────────────────────────────────

    def _build_config_yaml(self, run_id: str, payload: dict) -> dict:
        """生成训练配置（与本地 LocalDockerOrchestrator._build_config_yaml 结构一致）。

        简化：从 payload 直接构建最小可用配置，local_dir 由调用方覆盖为远端路径。
        """
        context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}
        features = payload.get("features", []) or []

        config: dict[str, Any] = {
            "run_id": run_id,
            "job_name": payload.get("job_name", "unnamed"),
            "data": {
                "train_start": payload.get("train_start", "2022-01-01"),
                "train_end": payload.get("train_end", "2024-12-31"),
                "features": features,
                "source_mode": "LOCAL",
                "local_dir": "/tmp/feature_snapshots",
            },
            "model": {
                "type": payload.get("model_type", "lightgbm"),
                "types": payload.get("model_types"),
                "ensemble": payload.get("ensemble", "none"),
                "num_boost_round": payload.get("num_boost_round", 1000),
                "early_stopping_rounds": payload.get("early_stopping_rounds", 100),
                "val_ratio": payload.get("val_ratio", 0.15),
                "params": payload.get("lgb_params", {}),
                "xgb_params": payload.get("xgb_params", {}),
                "catboost_params": payload.get("catboost_params", {}),
                "dl_params": payload.get("dl_params", {}),
            },
            "label": {
                "target_horizon_days": payload.get("target_horizon_days", 1),
                "target_mode": payload.get("target_mode", "return"),
                "label_formula": payload.get("label_formula", ""),
            },
            "context": {
                "initial_capital": context.get("initial_capital", 1_000_000),
                "benchmark": context.get("benchmark", "SH000300"),
                "commission_rate": context.get("commission_rate", 0.00025),
                "slippage": context.get("slippage", 0.0005),
                "deal_price": context.get("deal_price", "close"),
                "market": context.get("market", "CN"),
                "industry_as_feature": context.get("industry_as_feature", False),
            },
            "explain": payload.get("explain", DEFAULT_EXPLAIN_CFG),
            "output": {
                "result_path": "/workspace/result.json",
                "required_artifacts": payload.get(
                    "required_artifacts",
                    ["model.lgb", "pred.pkl", "metadata.json", "result.json"],
                ),
            },
            "callback": {
                "url": f"{self.api_base}/api/v1/models/training-runs/{run_id}/complete",
                "secret": self.internal_secret,
            },
            "cache": {"dir": "/tmp"},
        }

        split_fields = ["valid_start", "valid_end", "test_start", "test_end"]
        if all(payload.get(k) for k in split_fields):
            config["split"] = {
                "train": [payload.get("train_start"), payload.get("train_end")],
                "valid": [payload.get("valid_start"), payload.get("valid_end")],
                "test": [payload.get("test_start"), payload.get("test_end")],
            }
            config["model"]["val_ratio"] = None

        if payload.get("wfa") and isinstance(payload.get("wfa"), dict):
            config["wfa"] = payload["wfa"]
        try:
            config["max_time_minutes"] = max(10, int(payload.get("max_time_minutes") or 120))
        except Exception:
            config["max_time_minutes"] = 120
        if isinstance(payload.get("factor_selection"), dict):
            config["factor_selection"] = payload["factor_selection"]
        return config

    def _resolve_feature_files(self, payload: dict) -> list[str]:
        """根据训练区间解析需要的特征快照年份文件。"""
        from backend.services.engine.training.local_docker_orchestrator import (
            _LOCAL_DATA_PATH,
        )

        train_start = str(payload.get("train_start") or "2022-01-01")
        train_end = str(payload.get("train_end") or "2024-12-31")
        try:
            start_year = int(train_start[:4]) - 1  # 前一年用于标签
            end_year = int(train_end[:4])
        except (ValueError, TypeError):
            return []
        feature_dir = Path(_LOCAL_DATA_PATH)
        files = []
        for y in range(max(start_year, 2010), end_year + 1):
            f = feature_dir / f"model_features_{y}.parquet"
            if f.exists():
                files.append(str(f))
        return files

    def _build_docker_run_cmd(self, container_name: str) -> str:
        """构造远端 docker run 命令字符串。

        train.py 已 rsync 到 {work_dir}/train.py 并挂载覆盖镜像内置版，
        保证 train.py 更新不需要重新打包/上传 AutoDL 镜像。
        """
        return (
            f"docker run -d --name {container_name} "
            f"-v {self.work_dir}:/workspace "
            f"-v {self.work_dir}/feature_snapshots:/tmp/feature_snapshots:ro "
            f"-v {self.work_dir}/train.py:/app/train.py:ro "
            f"{self.docker_image} python /app/train.py --config /workspace/config.yaml"
        )

    def _resolve_train_script(self) -> str | None:
        """定位本地 train.py 训练脚本路径（优先项目目录，回退容器内路径）。"""
        candidates = [
            str(Path(__file__).resolve().parents[3] / "docker" / "training" / "train.py"),
            "/app/docker/training/train.py",
            "/app/train.py",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
        return None

    def _log(self, run_id: str, line: str, *, status: str | None = None, progress: int | None = None) -> None:
        try:
            self.log_stream.append_log(run_id=run_id, line=line, status=status, progress=progress)
        except Exception:  # noqa: BLE001
            logger.warning("append_log failed for %s: %s", run_id, line)


class LocalDockerProgress:
    """复用 LocalDockerOrchestrator 的日志进度解析逻辑。"""

    @staticmethod
    def infer(line: str, current: int) -> int:
        from backend.services.engine.training.local_docker_orchestrator import (
            LocalDockerOrchestrator,
        )

        return LocalDockerOrchestrator._infer_progress_from_log_line(line, current)
