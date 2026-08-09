#!/usr/bin/env python3
"""北向资金（沪深港通）HKEX 季度数据清洗脚本（存量 dt 分区 → quarter 分区迁移）。

2024-08-19 起北向个股持仓改为季度披露：每季度第 5 个沪深股通交易日公布
上季度末数据。HKEX 按日查询会连续多天返回同一份季度快照，导致旧版
`dt=YYYYMMDD/` 分区存在大量重复。

本脚本把存量 dt 分区合并、清洗、去重，迁移到新格式 `quarter=YYYYQN/`：

1. 代码映射：HKEX 5 位代号（030001/090001）→ 标准 `600036.SH`（名称匹配
   instrument_detail 优先，名称内嵌 `#688266` 次之，前缀规则兜底）。
2. 名称对齐：科创板/创业板 `-U/-W/-UW` 后缀归一，ETF/行业指数标注剔除。
3. 季度快照去重：同一 symbol 持仓重复只保留最早披露日。

用法:
  python backend/scripts/quantdb_north_clean.py --quarter 2026Q2   # 从 dt 分区迁移到 quarter=2026Q2
  python backend/scripts/quantdb_north_clean.py --quarter 2026Q2 --dry-run
  python backend/scripts/quantdb_north_clean.py --delete-old        # 迁移后删除旧 dt 分区
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quantdb_north_clean")

QUANTDB_DATA_DIR = Path(
    os.getenv("QM_QUANTDB_DATA_DIR", str(PROJECT_ROOT / "data" / "quantdb"))
)
REL_DIR = "2_base_sector/hsgt_north"


def _quantdb_root() -> Path:
    env_val = os.getenv("QM_QUANTDB_DATA_DIR", "").strip()
    if env_val:
        return Path(env_val)
    if Path("/data/quantdb").is_dir() and any(Path("/data/quantdb").iterdir()):
        return Path("/data/quantdb")
    QUANTDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTDB_DATA_DIR


def _quarter_end(quarter: str) -> date:
    mt = re.match(r"(\d{4})Q([1-4])", quarter)
    if not mt:
        raise ValueError(f"无效季度: {quarter}，应为 YYYYQN")
    year, q = int(mt.group(1)), int(mt.group(2))
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[q]


def _guess_quarter_from_dt(dt: str) -> str:
    """从 dt=YYYYMMDD 推测季度。以日期所在季度为准（清洗时用报告期替代）。"""
    d = date(int(dt[:4]), int(dt[4:6]), int(dt[6:8]))
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def migrate_partitions(*, quarter: str, dry_run: bool = False, delete_old: bool = False) -> dict:
    """把存量 dt= 分区合并清洗，落盘为 quarter=YYYYQN 快照。

    Args:
        quarter: 目标季度（如 2026Q2）。
        dry_run: 仅预览。
        delete_old: 迁移成功后删除旧 dt 分区。
    """
    from backend.scripts.quantdb_north_sync import _load_symbol_map, _resolve_symbol

    base = _quantdb_root() / REL_DIR
    if not base.is_dir():
        return {"status": "skipped", "reason": f"{base} 不存在"}

    # 收集所有 dt 分区
    dt_parts = sorted(p for p in base.glob("dt=*") if (p / "data.parquet").is_file())
    if not dt_parts:
        return {"status": "skipped", "reason": "无 dt= 分区可迁移"}

    target_dir = base / f"quarter={quarter}"
    if target_dir.exists():
        log.warning("目标 %s 已存在，将覆盖", target_dir)

    # 合并所有 dt 分区
    merged = []
    for p in dt_parts:
        df = pd.read_parquet(p / "data.parquet")
        if df.empty:
            continue
        merged.append(df)
    if not merged:
        return {"status": "skipped", "reason": "分区数据为空"}
    all_df = pd.concat(merged, ignore_index=True)

    symbol_map = _load_symbol_map()
    log.info("instrument_detail 名称映射: %d 条", len(symbol_map))

    # 解析 symbol
    resolved = all_df.apply(
        lambda r: _resolve_symbol(r, symbol_map), axis=1, result_type="expand"
    )
    all_df["symbol"] = resolved[0]
    all_df["_match"] = resolved[1]

    summary = {"total_rows": int(len(all_df))}
    for method in ("name", "embedded", "prefix", "unmatched"):
        summary[method] = int((all_df["_match"] == method).sum())

    # 未匹配：ETF/指数 与 真未匹配
    unm = all_df[all_df["symbol"].isna()]
    etf_mask = unm["stock_name"].astype(str).str.contains(
        r"ETF|LOF|基金|红利|增强|指增|A50|A500|现金|银行|证券|军工|半导体|央企|国企", regex=True, na=False
    )
    summary["etf"] = int(etf_mask.sum())
    summary["unmatched_dropped"] = int(len(unm) - etf_mask.sum())

    # 保留已解析 symbol 的行，季度快照去重（同一 symbol 只保留最早）
    keep = all_df[all_df["symbol"].notna()].copy()
    keep = keep.sort_values(["query_date"] if "query_date" in keep.columns else ["stock_code"])
    keep = keep.drop_duplicates(subset=["symbol"], keep="first")
    summary["unique_stocks"] = int(len(keep))

    # 落盘
    report_date = _quarter_end(quarter)
    keep["report_date"] = report_date
    out_cols = ["symbol", "stock_name", "holding_quantity", "holding_percentage", "query_date", "report_date", "market"]
    keep = keep[[c for c in out_cols if c in keep.columns]].reset_index(drop=True)

    if dry_run:
        return {
            "status": "dry_run",
            "quarter": quarter,
            "report_date": report_date.isoformat(),
            "source_partitions": [p.name for p in dt_parts],
            "unique_stocks": len(keep),
            "summary": summary,
            "target": str(target_dir),
        }

    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / "data.parquet"
    keep.to_parquet(out, index=False)
    log.info("写入 %s: %d 只股票", out, len(keep))

    if delete_old:
        for p in dt_parts:
            shutil.rmtree(p, ignore_errors=True)
        log.info("已删除 %d 个旧 dt 分区", len(dt_parts))

    return {
        "status": "ok",
        "quarter": quarter,
        "report_date": report_date.isoformat(),
        "source_partitions": [p.name for p in dt_parts],
        "unique_stocks": len(keep),
        "summary": summary,
        "target": str(out),
        "deleted_old": len(dt_parts) if delete_old else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="北向资金存量 dt 分区 → quarter 季度快照迁移清洗")
    parser.add_argument("--quarter", required=True, help="目标季度 YYYYQN，如 2026Q2")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    parser.add_argument("--delete-old", action="store_true", help="迁移成功后删除旧 dt 分区")
    args = parser.parse_args()

    try:
        result = migrate_partitions(quarter=args.quarter, dry_run=args.dry_run, delete_old=args.delete_old)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("迁移失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
