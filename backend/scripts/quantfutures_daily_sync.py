#!/usr/bin/env python3
"""期货数据同步入口 — 按勾选数据集分发到 akshare 期货同步脚本。

支持的数据集（与后台 catalog 对应）:
  daily_forward     期货/贵金属日K  → foreign_daily + cn_daily + sge_daily
  futures_realtime  实时行情快照    → foreign_realtime + cn_realtime

用法:
  python backend/scripts/quantfutures_daily_sync.py --days 5
  python backend/scripts/quantfutures_daily_sync.py --datasets daily_forward,futures_realtime
"""

from __future__ import annotations

import sys
from typing import Any

# catalog 数据集名 → akshare_futures_sync 的 field（一个数据集可对应多个数据段）
DATASET_FIELDS: dict[str, list[str]] = {
    "daily_forward": ["foreign_daily", "cn_daily", "sge_daily"],
    "futures_realtime": ["foreign_realtime", "cn_realtime"],
}


def run(*, days: int = 5, datasets: list[str] | None = None, **kwargs: Any) -> dict:
    """同步期货数据。datasets 为勾选的 catalog 数据集名；None 时全量同步。"""
    from backend.scripts.akshare_futures_sync import sync as ak_futures_sync

    if not datasets:
        return ak_futures_sync("all")

    fields: list[str] = []
    for ds in datasets:
        fields.extend(DATASET_FIELDS.get(ds, []))
    if not fields:
        return {"market": "futures", "days": days, "datasets": datasets, "result": {}}

    result = {}
    for field in fields:
        result[field] = ak_futures_sync(field)
    return {"market": "futures", "days": days, "datasets": datasets, "result": result}


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="期货数据同步")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--datasets", default=None, help="逗号分隔数据集名")
    args, _ = parser.parse_known_args()

    ds = [d.strip() for d in args.datasets.split(",") if d.strip()] if args.datasets else None
    result = run(days=args.days, datasets=ds)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
