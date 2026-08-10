#!/usr/bin/env python3
"""CCASS top50 缺失数据导入 → QuantHK。

从外部 data/data 目录（按股票/年份/日组织的 CCASS top50 CSV）导入，
转成 dt=YYYYMMDD 分区，补齐本地 ccass_top50 缺失的交易日。

源结构:
  {data}/{股票名}/{年份}/{股票名}_{代码}_{YYYY-MM-DD}_top50.csv
  列: 查询日期/股票名称/股票代码/参与者编号/参与者名称/持股数量/占已发行股份百分比

落盘:
  {quanthk}/2_base_sector/ccass_top50/dt=YYYYMMDD/data.parquet

用法:
  python backend/scripts/quanthk_import_ccass_data.py --dir /media/.../data/data
  python backend/scripts/quanthk_import_ccass_data.py --dir ... --date 2026-05-11
  python backend/scripts/quanthk_import_ccass_data.py --dir ... --dry-run
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quanthk_import_ccass_data")

QUANTHK_DATA_DIR = Path(os.getenv("QM_QUANTHK_DATA_DIR", str(PROJECT_ROOT / "data" / "quanthk")))
REL_DIR = "2_base_sector/ccass_top50"

DEFAULT_SRC_DIR = "/media/zbox/sata/jr/stock-quant_bJbLC/stock-quant/data/data"

# 输出列（与本地 ccass_top50 parquet 一致）
OUT_COLS = ["stock_code", "stock_name", "participant_id", "participant_name",
            "holding_quantity", "holding_percentage", "query_date"]

_DATE_IN_FILENAME = re.compile(r"_(\d{4}-\d{2}-\d{2})_top50\.csv$")


def _quanthk_root() -> Path:
    env_val = os.getenv("QM_QUANTHK_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/data/quanthk").is_dir() and any(Path("/data/quanthk").iterdir()):
        return Path("/data/quanthk")
    QUANTHK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTHK_DATA_DIR


def _parse_csv(path: Path) -> pd.DataFrame | None:
    """读单个 CCASS top50 CSV → 标准列。"""
    df = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None or df.empty:
        return None
    df.columns = [str(c).strip() for c in df.columns]

    rename = {}
    for col in df.columns:
        if "查询日期" in col:
            rename[col] = "query_date"
        elif "股票名称" in col:
            rename[col] = "stock_name"
        elif "股票代码" in col:
            rename[col] = "stock_code"
        elif "参与者编号" in col or "参与者代号" in col:
            rename[col] = "participant_id"
        elif "参与者名称" in col:
            rename[col] = "participant_name"
        elif "持股数量" in col:
            rename[col] = "holding_quantity"
        elif "占已发行股份" in col or "百分比" in col:
            rename[col] = "holding_percentage"
    df = df.rename(columns=rename)

    need = {"query_date", "stock_code", "participant_name", "holding_quantity"}
    if not need.issubset(df.columns):
        log.debug("跳过 %s：缺列 %s", path.name, list(df.columns))
        return None

    df["query_date"] = pd.to_datetime(df["query_date"], errors="coerce").dt.date
    df["stock_code"] = df["stock_code"].astype(str).str.strip().str.zfill(5)
    df["stock_name"] = df.get("stock_name", "").astype(str)
    if "participant_id" not in df.columns:
        df["participant_id"] = ""
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")
    df["holding_percentage"] = (
        df["holding_percentage"].astype(str).str.replace("%", "", regex=False).str.strip()
    )
    df["holding_percentage"] = pd.to_numeric(df["holding_percentage"], errors="coerce").fillna(0.0) / 100.0

    return df[OUT_COLS].dropna(subset=["query_date", "stock_code"])


def import_ccass(src_dir: str | None = None, *, dates: list[str] | None = None,
                 dry_run: bool = False, workers: int = 8) -> dict:
    """导入 CCASS top50 CSV → dt 分区。dates 指定日期（YYYY-MM-DD），空则全部缺失日。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    src = Path(src_dir or DEFAULT_SRC_DIR)
    if not src.is_dir():
        return {"status": "skipped", "reason": f"{src} 不存在"}

    # 收集所有 top50 CSV，按日期分组
    csvs = list(src.rglob("*_top50.csv"))
    log.info("源 CSV: %d 个 (%s)", len(csvs), src)

    by_date: dict[str, list[Path]] = defaultdict(list)
    for f in csvs:
        m = _DATE_IN_FILENAME.search(f.name)
        if m:
            by_date[m.group(1)].append(f)
    all_dates = sorted(by_date)
    log.info("源日期数: %d, 范围 %s ~ %s", len(all_dates), all_dates[0], all_dates[-1])

    # 已有分区
    target_dir = _quanthk_root() / REL_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name[3:] for p in target_dir.glob("dt=*")}

    # 目标日期：指定 dates，或缺失日期
    if dates:
        want = {d.replace("-", "") for d in dates}
    else:
        want = {d.replace("-", "") for d in all_dates if d.replace("-", "") not in existing}
    want_dates = sorted(want)
    missing_new = [d for d in want_dates if d not in existing]
    log.info("待补日期: %d 个 (已有 %d)", len(missing_new), len(existing))
    if not missing_new:
        return {"status": "ok", "imported": 0, "target_dir": str(target_dir), "reason": "无缺失日期"}

    if dry_run:
        return {"status": "dry_run", "dates": missing_new, "count": len(missing_new),
                "target_dir": str(target_dir)}

    # 按日期导入
    imported = 0
    errors = []
    for date_str in missing_new:
        ymd = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        files = by_date.get(ymd, [])
        if not files:
            continue
        frames = []
        for f in files:
            try:
                df = _parse_csv(f)
                if df is not None and not df.empty:
                    frames.append(df)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{f.name}: {str(exc)[:60]}")
        if not frames:
            continue
        all_df = pd.concat(frames, ignore_index=True)
        # 同一参与者同一天去重
        all_df = all_df.drop_duplicates(subset=["stock_code", "participant_id"], keep="last")

        dt_dir = target_dir / f"dt={date_str}"
        dt_dir.mkdir(parents=True, exist_ok=True)
        out = dt_dir / "data.parquet"
        if out.exists():
            old = pd.read_parquet(out)
            all_df = pd.concat([old, all_df], ignore_index=True)
            all_df = all_df.drop_duplicates(subset=["stock_code", "participant_id"], keep="last")
        all_df.to_parquet(out, index=False)
        imported += 1
        log.info("[%s] 导入 %d 只股票", date_str, all_df["stock_code"].nunique())

    return {
        "status": "ok",
        "imported": imported,
        "dates": missing_new,
        "errors": errors[:20],
        "target_dir": str(target_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CCASS top50 缺失数据导入")
    parser.add_argument("--dir", default=None, help="源 data/data 目录")
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD，逗号分隔")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    dates = [d.strip() for d in args.date.split(",") if d.strip()] if args.date else None
    try:
        result = import_ccass(args.dir, dates=dates, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("导入失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
