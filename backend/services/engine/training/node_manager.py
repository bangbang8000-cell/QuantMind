"""AutoDL 训练节点配置加载与状态采集。

提供两件事：
1. load_training_nodes() —— 读取多节点配置（config/training_nodes.yaml），
   无 YAML 时回退单节点环境变量（向后兼容）。
2. NodeStatus.collect() —— SSH 到节点采集实时状态（CPU/GPU/内存/训练容器），
   供后台「AutoDL 节点」状态面板展示。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

NODES_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "training_nodes.yaml"
# 容器内路径（docker-compose 挂载 ./config:/app/config）
NODES_CONFIG_CONTAINER = Path("/app/config/training_nodes.yaml")


def _resolve_config_path() -> Path | None:
    for p in (NODES_CONFIG_PATH, NODES_CONFIG_CONTAINER):
        if p.exists():
            return p
    return None


def _env_or(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


def load_training_nodes() -> list[dict[str, Any]]:
    """读取所有 AutoDL 远程节点配置。

    优先 config/training_nodes.yaml；不存在时回退旧的单节点环境变量
    （TRAINING_AUTODL_HOST），保证老部署无缝升级。
    """
    cfg_path = _resolve_config_path()
    if cfg_path:
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            nodes = data.get("nodes") or []
            result = []
            for n in nodes:
                if not n.get("id") or not n.get("host"):
                    continue
                # 认证信息缺省时回退单节点环境变量（docker-compose 传入）
                if not n.get("ssh_password") and not n.get("ssh_key"):
                    n["ssh_password"] = _env_or("TRAINING_AUTODL_SSH_PASSWORD", "")
                    n["ssh_key"] = _env_or("TRAINING_AUTODL_SSH_KEY", "")
                result.append(n)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取训练节点配置失败 %s: %s", cfg_path, exc)

    # 回退：单节点环境变量
    host = _env_or("TRAINING_AUTODL_HOST", "")
    if not host:
        return []
    return [{
        "id": "autodl-1",
        "name": _env_or("TRAINING_AUTODL_NODE_NAME", "AutoDL GPU"),
        "host": host,
        "port": _env_or("TRAINING_AUTODL_SSH_PORT", "22"),
        "user": _env_or("TRAINING_AUTODL_USER", "root"),
        "ssh_password": _env_or("TRAINING_AUTODL_SSH_PASSWORD", ""),
        "ssh_key": _env_or("TRAINING_AUTODL_SSH_KEY", ""),
        "work_dir": _env_or("TRAINING_AUTODL_WORK_DIR", "/workspace"),
        "docker_image": _env_or("TRAINING_AUTODL_DOCKER_IMAGE", "quantmind-train:latest"),
        "gpus": _env_or("TRAINING_AUTODL_GPUS", "all"),
    }]


def get_node_config(node_id: str) -> dict[str, Any] | None:
    """按 node_id 查节点配置。"""
    for n in load_training_nodes():
        if n["id"] == node_id:
            return n
    return None


class NodeStatus:
    """从 AutoDL 节点采集实时状态（SSH）。"""

    _SSH_TIMEOUT = 15
    _COLLECT_CMD = r"""
set -e
echo "===SYS==="
nproc
uptime
echo "mem:$(free -m | grep -iE 'mem|内存' | awk '{print $2, $3}')"
echo "disk:$(df -P / | awk 'NR==2{print $2, $3}')"
echo "net:$(cat /proc/net/dev | awk '/eth0|ens|enp/{gsub(/:/,\"\"); rx+=$2; tx+=$10} END{print rx, tx}')"
echo "rx1:$(cat /sys/class/net/*/statistics/rx_bytes 2>/dev/null | awk '{s+=$1} END{print s+0}')"
echo "tx1:$(cat /sys/class/net/*/statistics/tx_bytes 2>/dev/null | awk '{s+=$1} END{print s+0}')"
echo "===GPU==="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name --format=csv,noheader,nounits 2>&1 || echo "gpu-error"
else
  echo "no-gpu"
fi
echo "===DOCKER==="
docker ps --filter name=qm-train- --format '{{.Names}}|{{.Status}}' 2>/dev/null || echo "no-docker"
echo "===NET==="
cat /proc/loadavg 2>/dev/null | awk '{print $1}'
"""

    @staticmethod
    def _build_ssh(node: dict[str, Any]) -> list[str]:
        args = []
        if node.get("ssh_password"):
            args += ["sshpass", "-p", node["ssh_password"]]
        args += ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
        args += ["-p", str(node.get("port") or 22)]
        if node.get("ssh_key"):
            args += ["-i", node["ssh_key"]]
        args.append(f"{node.get('user') or 'root'}@{node['host']}")
        return args

    @classmethod
    async def collect(cls, node: dict[str, Any]) -> dict[str, Any]:
        """SSH 采集节点状态。失败时返回 offline 标记，不抛错。"""
        result: dict[str, Any] = {
            "id": node.get("id"),
            "name": node.get("name") or node.get("id"),
            "host": node.get("host"),
            "online": False,
        }
        proc = await asyncio.create_subprocess_exec(
            *cls._build_ssh(node),
            cls._COLLECT_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=cls._SSH_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            result["error"] = "SSH 超时"
            return result
        if proc.returncode not in (0, None):
            result["error"] = f"SSH 失败 code={proc.returncode}"
            return result

        out = stdout.decode(errors="replace")
        return cls._parse(out, result)

    @staticmethod
    def _parse(out: str, result: dict[str, Any]) -> dict[str, Any]:
        result["online"] = True
        sections: dict[str, str] = {}
        current = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("===") and line.endswith("==="):
                current = line.strip("=")
                sections[current] = ""
            elif current is not None:
                sections[current] = (sections[current] + "\n" + line).strip()

        # CPU 核数 + loadavg
        sys_text = sections.get("SYS", "")
        sys_lines = [l for l in sys_text.splitlines() if l]
        if sys_lines:
            result["cpu_cores"] = int(sys_lines[0]) if sys_lines[0].isdigit() else None
        # loadavg（NET 段取了第 1 个值）
        load_txt = sections.get("NET", "").strip()
        result["cpu_load"] = float(load_txt) if load_txt.replace(".", "", 1).isdigit() else None

        # 内存 mem:total used（free -m，MB）
        mem_line = next((l for l in sys_lines if l.startswith("mem:")), None)
        if mem_line:
            parts = mem_line.split(":")
            if len(parts) >= 2:
                vals = parts[1].split()
                if len(vals) >= 2:
                    result["mem_total_mb"] = int(vals[0]) if vals[0].isdigit() else None
                    result["mem_used_mb"] = int(vals[1]) if vals[1].isdigit() else None

        # 硬盘 disk:total used（df -P /，KB）
        disk_line = next((l for l in sys_lines if l.startswith("disk:")), None)
        if disk_line:
            parts = disk_line.split(":")
            if len(parts) >= 2:
                vals = parts[1].split()
                if len(vals) >= 2:
                    result["disk_total_kb"] = int(vals[0]) if vals[0].isdigit() else None
                    result["disk_used_kb"] = int(vals[1]) if vals[1].isdigit() else None

        # 网络累计收发（字节）——用于前端计算速率
        rx_line = next((l for l in sys_lines if l.startswith("rx1:")), None)
        tx_line = next((l for l in sys_lines if l.startswith("tx1:")), None)
        result["net_rx_bytes"] = int(rx_line.split(":")[1]) if rx_line and rx_line.split(":")[1].strip().isdigit() else None
        result["net_tx_bytes"] = int(tx_line.split(":")[1]) if tx_line and tx_line.split(":")[1].strip().isdigit() else None

        # GPU nvidia-smi（若驱动异常则记录原因）
        gpu_lines = [l for l in sections.get("GPU", "").splitlines() if l]
        gpu_list = []
        if gpu_lines and gpu_lines[0] not in ("no-gpu", "gpu-error"):
            for l in gpu_lines:
                parts = [p.strip() for p in l.split(",")]
                if len(parts) >= 4:
                    gpu_list.append({
                        "util": int(parts[0]) if parts[0].isdigit() else 0,
                        "mem_used_mb": int(parts[1]) if parts[1].isdigit() else 0,
                        "mem_total_mb": int(parts[2]) if parts[2].isdigit() else 0,
                        "temp_c": int(parts[3]) if parts[3].isdigit() else 0,
                        "name": parts[4] if len(parts) > 4 else "",
                    })
        result["gpus"] = gpu_list
        if not gpu_list:
            # 记录 GPU 不可用原因
            if gpu_lines and gpu_lines[0] == "gpu-error":
                err = " ".join(gpu_lines[1:]).strip()
                result["gpu_error"] = err or "nvidia-smi 驱动异常"
            elif gpu_lines and gpu_lines[0] == "no-gpu":
                result["gpu_error"] = "未安装 nvidia-smi"
            else:
                result["gpu_error"] = "未检测到 GPU"

        # Docker 训练容器
        docker_lines = [l for l in sections.get("DOCKER", "").splitlines() if l and l != "no-docker"]
        containers = []
        for l in docker_lines:
            if "|" in l:
                name, status = l.split("|", 1)
                containers.append({"name": name.strip(), "status": status.strip()})
        result["containers"] = containers
        result["training_active"] = bool(containers)

        # 网络延迟：ping 一次网关（尽力而为）
        result["ping_ms"] = None
        return result
