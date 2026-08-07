"""运行时密钥文件读写。

后台管理页面填写的 API Key 需要在容器重启后仍然生效，因此落盘到
``config/runtime.env``（Docker 中 ``./config`` 是挂载卷，宿主机可见）。

优先级：真实环境变量（非空） > runtime.env > 默认值。
docker-compose 里形如 ``QUANTDB_API_KEY=${QUANTDB_API_KEY:-}`` 的声明会注入
空字符串，因此空值视为“未配置”，允许被 runtime.env 覆盖。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def runtime_env_path() -> Path:
    override = os.getenv("QM_RUNTIME_ENV_FILE", "").strip()
    if override:
        return Path(override)
    return _PROJECT_ROOT / "config" / "runtime.env"


def _parse(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'\"")
    return out


def load_runtime_env() -> int:
    """将 runtime.env 注入进程环境变量，返回注入条数。"""
    try:
        entries = _parse(runtime_env_path())
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 runtime.env 失败: %s", exc)
        return 0
    loaded = 0
    for key, value in entries.items():
        if not os.environ.get(key, "").strip():
            os.environ[key] = value
            loaded += 1
    return loaded


def set_secret(key: str, value: str) -> Path:
    """写入/更新一条密钥，同时立即生效于当前进程。"""
    if not _KEY_PATTERN.match(key):
        raise ValueError(f"非法的配置键名: {key}")
    if "\n" in value or "\r" in value:
        raise ValueError("配置值不能包含换行")

    path = runtime_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    new_line = f"{key}={value}"
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    os.environ[key] = value
    return path


def mask_secret(value: str | None) -> str:
    """脱敏展示，永不回传明文。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 8}{value[-4:]}"
