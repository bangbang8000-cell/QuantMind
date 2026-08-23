"""运行时代码版本读取。

版本来源（优先级）：
1. backend/shared/version.txt —— 由 deploy/update.sh 在每次 git pull 后写入
   （`git describe --tags --always` 格式，如 v1.10.0 或 v1.10.0-3-gabc1234）
2. 缺省回退 "dev"（本地未走 update.sh 的开发环境）
"""
from __future__ import annotations

from pathlib import Path

_VERSION_TXT = Path(__file__).resolve().parent / "version.txt"


def get_version() -> str:
    try:
        v = _VERSION_TXT.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    return "dev"


__all__ = ["get_version"]
