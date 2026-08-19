"""每日复盘统计核心逻辑（纯函数，可单测，不碰 IO）。

为单一事实源，涨跌停/广度/分布/板块聚合等纯函数统一收归
backend/shared/market_breadth.py，本模块仅转引用，供 daily-review 脚本使用。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "backend" / "main_oss.py").is_file():
            return p
    raise FileNotFoundError("未找到仓库根（含 backend/main_oss.py）")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402

from backend.shared.market_breadth import (  # noqa: E402, F401
    CAT_BROKE_UP,
    CAT_CORP_ACTION,
    CAT_DOWN,
    CAT_FLAT,
    CAT_LIMIT_DOWN,
    CAT_LIMIT_UP,
    CAT_NORMAL,
    CAT_UP,
    TOL_BJ,
    TOL_SHSZ,
    breadth_distribution,
    classify_by_pct,
    classify_price,
    compute_limits,
    fmt_yi,
    is_bse_symbol,
    is_corp_action_pct,
    is_ex_div,
    limit_pct,
    market_breadth,
    sector_aggregate,
    streak_from_tail,
    volume_ratio_5,
    wan_to_yi,
)
