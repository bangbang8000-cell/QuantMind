#!/usr/bin/env python3
"""CCASS top50 机构持股数据 → QuantHK 导入脚本。

从外部 duckdb (position.duckdb) 读取 CCASS 机构持仓数据，按 QuantDB 的
Hive 分区格式落盘到 quanthk 本地 parquet。

数据源结构 (position_data 表):
  query_date DATE, stock_name VARCHAR, stock_code VARCHAR,
  participant_id VARCHAR, participant_name VARCHAR,
  holding_quantity BIGINT, holding_percentage DOUBLE

落盘格式:
  {quanthk}/2_base_sector/ccass_top50/dt=YYYYMMDD/data.parquet
  stock_code 保持 5 位（如 00700），不加 .HK 后缀。

用法:
  python backend/scripts/quanthk_import_ccass.py --source /path/to/position.duckdb
  python backend/scripts/quanthk_import_ccass.py --source /path/to/position.duckdb --start 2026-01-01
  python backend/scripts/quanthk_import_ccass.py --source /path/to/position.duckdb --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
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
log = logging.getLogger("quanthk_import_ccass")

QUANTHK_DATA_DIR = Path(
    os.getenv("QM_QUANTHK_DATA_DIR", str(PROJECT_ROOT / "data" / "quanthk"))
)
REL_DIR = "2_base_sector/ccass_top50"

# 输出列（与源对齐，顺序固定）
OUT_COLS = [
    "stock_code", "stock_name", "participant_id", "participant_name",
    "holding_quantity", "holding_percentage", "query_date",
]


def _quanthk_root() -> Path:
    """解析 quanthk 数据目录（容器优先 /data/quanthk）。"""
    env_val = os.getenv("QM_QUANTHK_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/data/quanthk").is_dir():
        return Path("/data/quanthk")
    QUANTHK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTHK_DATA_DIR


def _load_dates(source: str, start: str | None, end: str | None) -> list[str]:
    """列出待导入的交易日（YYYYMMDD）。"""
    import duckdb

    con = duckdb.connect(source, read_only=True)
    sql = "SELECT DISTINCT query_date FROM position_data"
    conds = []
    if start:
        conds.append(f"query_date >= DATE '{start}'")
    if end:
        conds.append(f"query_date <= DATE '{end}'")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = con.execute(sql).fetchall()
    con.close()
    dates = [d[0].strftime("%Y%m%d") for d in rows if d[0] is not None]
    return sorted(dates)


def _import_date(source: str, date_str: str, target_dir: Path, *, dry_run: bool = False) -> int:
    """导入单日分区。返回行数。"""
    import duckdb

    dt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    con = duckdb.connect(source, read_only=True)
    df = con.execute(
        f"SELECT stock_code, stock_name, participant_id, participant_name, "
        f"holding_quantity, holding_percentage, query_date "
        f"FROM position_data WHERE query_date = DATE '{dt}'"
    ).df()
    con.close()

    if df.empty:
        log.warning("  %s 无数据", date_str)
        return 0

    # 统一列顺序 + 类型
    df = df[OUT_COLS].copy()
    df["query_date"] = pd.to_datetime(df["query_date"]).dt.date
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")
    df["holding_percentage"] = pd.to_numeric(df["holding_percentage"], errors="coerce").fillna(0.0)
    # 代码统一为后缀格式（00700 → 0700.HK；创业板 8 开头保留 5 位+.HK）
    from backend.shared.stock_utils import StockCodeUtil

    df["stock_code"] = df["stock_code"].astype(str).map(StockCodeUtil.to_hk_suffix)

    if dry_run:
        return len(df)

    # 按日分区落盘
    dt_dir = target_dir / f"dt={date_str}"
    dt_dir.mkdir(parents=True, exist_ok=True)
    target = dt_dir / "data.parquet"
    if target.exists():
        old = pd.read_parquet(target)
        combined = pd.concat([old, df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["stock_code", "participant_id"], keep="last"
        )
        combined.to_parquet(target, index=False)
    else:
        df.to_parquet(target, index=False)

    return len(df)


def import_ccass(source: str, *, start: str | None = None, end: str | None = None, dry_run: bool = False) -> dict:
    """全量导入 CCASS top50 数据到 quanthk。"""
    if not Path(source).is_file():
        raise FileNotFoundError(f"duckdb 文件不存在: {source}")

    root = _quanthk_root()
    target_dir = root / REL_DIR

    dates = _load_dates(source, start, end)
    log.info("待导入交易日: %d 个 (%s ~ %s)", len(dates), dates[0] if dates else "-", dates[-1] if dates else "-")

    if dry_run:
        return {"source": source, "days": len(dates), "dry_run": True, "dir": str(target_dir)}

    total_rows = 0
    imported = 0
    for i, date_str in enumerate(dates):
        rows = _import_date(source, date_str, target_dir)
        total_rows += rows
        imported += 1
        if (i + 1) % 50 == 0 or i == len(dates) - 1:
            log.info("  进度 %d/%d，累计 %d 行", i + 1, len(dates), total_rows)

    return {
        "source": source,
        "days": imported,
        "rows": total_rows,
        "dir": str(target_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CCASS top50 → QuantHK")
    parser.add_argument("--source", required=True, help="position.duckdb 路径")
    parser.add_argument("--start", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="仅列出待导入，不写盘")
    args = parser.parse_args()

    try:
        result = import_ccass(args.source, start=args.start, end=args.end, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("导入失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
