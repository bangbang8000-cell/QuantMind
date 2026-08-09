#!/usr/bin/env python3
"""北向资金（沪深港通）历史 → QuantDB 导入脚本。

从外部 AHlog 目录（北向资金持股变动 CSV）读取沪深港通北向持股变动数据，
落盘到 quantdb 本地 parquet。

数据源结构 (AHlog/北向资金持股变动_*.csv):
  初始日期, 股份代码, 股票名称, 股票类型, 初始持股百分比(%), 初始持股量,
  变动日期, 变动类型, 股份变动数量, 百分比变动(%), 变动后持股百分比(%),
  变动后持股量, 增持幅度(%), 减持幅度(%)

落盘格式:
  {quantdb}/2_base_sector/hsgt_north/hsgt_north.parquet
  股份代码保持 5 位（30001），与 A 股一致。

用法:
  python backend/scripts/quantdb_import_north.py --dir /path/to/AHlog
  python backend/scripts/quantdb_import_north.py --dir ... --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quantdb_import_north")

QUANTDB_DATA_DIR = Path(
    os.getenv("QM_QUANTDB_DATA_DIR", str(PROJECT_ROOT / "data" / "quantdb"))
)
REL_DIR = "2_base_sector/hsgt_north"
OUT_FILE = "hsgt_north.parquet"

DEFAULT_SRC_DIR = "/media/zbox/sata/jr/stock-quant_bJbLC/stock-quant/data/AHlog"

# 输出列（统一英文）
OUT_COLS = [
    "init_date", "stock_code", "stock_name", "stock_type",
    "init_percent", "init_quantity", "change_date", "change_type",
    "change_quantity", "change_percent", "after_percent", "after_quantity",
    "increase_pct", "decrease_pct",
]


def _quantdb_root() -> Path:
    env_val = os.getenv("QM_QUANTDB_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    # 容器内 /data/quantdb 有内容才用；否则用项目根 ./data/quantdb
    if Path("/data/quantdb").is_dir() and any(Path("/data/quantdb").iterdir()):
        return Path("/data/quantdb")
    QUANTDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTDB_DATA_DIR


def _read_north_csv(path: Path) -> pd.DataFrame | None:
    """读单个北向资金 CSV（GBK/utf-8-sig），标准化。"""
    df = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None or df.empty:
        return None

    # 列名标准化
    rename = {
        "初始日期": "init_date",
        "股份代码": "stock_code",
        "股票名称": "stock_name",
        "股票类型": "stock_type",
        "初始持股百分比(%)": "init_percent",
        "初始持股量": "init_quantity",
        "变动日期": "change_date",
        "变动类型": "change_type",
        "股份变动数量": "change_quantity",
        "百分比变动(%)": "change_percent",
        "变动后持股百分比(%)": "after_percent",
        "变动后持股量": "after_quantity",
        "增持幅度(%)": "increase_pct",
        "减持幅度(%)": "decrease_pct",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "init_date" not in df.columns or "stock_code" not in df.columns:
        return None

    df["init_date"] = pd.to_datetime(df["init_date"], errors="coerce").dt.date
    if "change_date" in df.columns:
        df["change_date"] = pd.to_datetime(df["change_date"], errors="coerce").dt.date
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)  # A股6位

    for c in ("init_percent", "init_quantity", "change_quantity", "change_percent",
              "after_percent", "after_quantity", "increase_pct", "decrease_pct"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["init_date", "stock_code"])
    return df[OUT_COLS] if all(c in df.columns for c in OUT_COLS) else df


def import_north(src_dir: str | None = None, *, dry_run: bool = False) -> dict:
    """全量导入北向资金历史到 quantdb。"""
    src = Path(src_dir or DEFAULT_SRC_DIR)
    if not src.is_dir():
        raise FileNotFoundError(f"数据目录不存在: {src}")

    target_dir = _quantdb_root() / REL_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    csv_files = list(src.glob("*.csv"))
    log.info("待导入 CSV: %d 个 (%s)", len(csv_files), src)

    if dry_run:
        return {"dir": str(src), "files": len(csv_files), "dry_run": True, "target_dir": str(target_dir)}

    frames = []
    for f in csv_files:
        try:
            df = _read_north_csv(f)
            if df is not None and not df.empty:
                frames.append(df)
                log.info("  读取 %s: %d 行", f.name, len(df))
        except Exception as exc:  # noqa: BLE001
            log.warning("读取 %s 失败: %s", f.name, exc)

    if not frames:
        return {"dir": str(src), "files": len(csv_files), "rows": 0, "errors": len(csv_files)}

    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.drop_duplicates(subset=["stock_code", "change_date", "change_type", "change_quantity"], keep="last")
    all_df = all_df.sort_values(["stock_code", "change_date"]).reset_index(drop=True)

    out = target_dir / OUT_FILE
    all_df.to_parquet(out, index=False)

    return {
        "dir": str(src),
        "files": len(csv_files),
        "rows": int(len(all_df)),
        "target_dir": str(target_dir),
        "file": str(out),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="北向资金历史 → QuantDB")
    parser.add_argument("--dir", default=None, help="AHlog 目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写盘")
    args = parser.parse_args()

    try:
        result = import_north(args.dir, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("导入失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
