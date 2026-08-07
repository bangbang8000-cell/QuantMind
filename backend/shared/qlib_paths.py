"""
Qlib 数据路径统一解析
=====================
所有需要 Qlib provider_uri 的地方应通过本模块获取，避免硬编码 db/qlib_data。

优先级：
1. 环境变量 QLIB_PROVIDER_URI（显式覆盖）
2. /data/quantdb/.qlib_cache/cn_data（QuantDB 单源迁移后的标准路径）
3. /app/db/qlib_data（旧路径，兼容回退）
4. 项目相对路径 db/qlib_data（开发环境回退）
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_qlib_provider_uri(market: str = "CN") -> str:
    """返回 Qlib provider_uri 绝对路径。

    market: "CN", "HK", "US", "CRYPTO" — 仅 CN 走 QuantDB 路径，
    其他市场仍使用 db/qlib_data/{market}_data。
    """
    env_val = os.getenv("QLIB_PROVIDER_URI", "").strip()
    if env_val:
        return env_val

    market_upper = market.upper()

    # 非 A 股市场：固定子目录
    _MARKET_SUBDIR: dict[str, str] = {
        "HK": "hk_data",
        "US": "us_data",
        "CRYPTO": "crypto_data",
    }
    if market_upper in _MARKET_SUBDIR:
        subdir = _MARKET_SUBDIR[market_upper]
        for candidate in (
            Path(f"/data/qlib_data/{subdir}"),
            Path(f"/app/db/qlib_data/{subdir}"),
            _PROJECT_ROOT / "db" / "qlib_data" / subdir,
        ):
            if candidate.exists():
                return str(candidate)
        return str(_PROJECT_ROOT / "db" / "qlib_data" / subdir)

    # A 股 (CN)：优先 QuantDB 缓存路径
    for candidate in (
        Path("/data/quantdb/.qlib_cache/cn_data"),
        _PROJECT_ROOT / "data" / "quantdb" / ".qlib_cache" / "cn_data",
        Path("/app/db/qlib_data"),
        _PROJECT_ROOT / "db" / "qlib_data",
    ):
        if candidate.exists():
            return str(candidate)

    return str(_PROJECT_ROOT / "db" / "qlib_data")


def resolve_qlib_data_dir(market: str = "CN") -> str:
    """resolve_qlib_provider_uri 的别名，语义更清晰。"""
    return resolve_qlib_provider_uri(market=market)


def resolve_qlib_calendar_path(market: str = "CN") -> Path:
    """返回 Qlib 交易日历文件路径 (calendars/day.txt)。"""
    return Path(resolve_qlib_provider_uri(market=market)) / "calendars" / "day.txt"


def resolve_qlib_instruments_path(market: str = "CN") -> Path:
    """返回 Qlib instruments 文件路径 (instruments/all.txt)。"""
    return Path(resolve_qlib_provider_uri(market=market)) / "instruments" / "all.txt"
