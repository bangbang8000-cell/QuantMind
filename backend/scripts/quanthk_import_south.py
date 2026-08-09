#!/usr/bin/env python3
"""南向资金（港股通）历史 → QuantHK 导入脚本。

从外部 data-hs 目录（每只股票一个 CSV，南向资金持仓时间序列）读取港股通
持仓数据，落盘到 quanthk 本地 parquet。

数据源结构 (data-hs/{股票名}/南向资金_{股票名}_{代码}.csv):
  查询日期, 股份代号, 名称, 于中央结算系统的持股量, 占已发行股份/单位百分比

落盘格式:
  {quanthk}/2_base_sector/hsgt_south/{symbol}.parquet
  stock_code 5位（00700）→ 4位+.HK（0700.HK）

用法:
  python backend/scripts/quanthk_import_south.py --dir /path/to/data-hs
  python backend/scripts/quanthk_import_south.py --dir ... --dry-run
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
log = logging.getLogger("quanthk_import_south")

QUANTHK_DATA_DIR = Path(
    os.getenv("QM_QUANTHK_DATA_DIR", str(PROJECT_ROOT / "data" / "quanthk"))
)
REL_DIR = "2_base_sector/hsgt_south"

DEFAULT_SRC_DIR = "/media/zbox/sata/jr/stock-quant_bJbLC/stock-quant/data/data-hs"

# 输出列
OUT_COLS = [
    "symbol", "query_date", "holding_quantity", "holding_percentage",
]


def _quanthk_root() -> Path:
    env_val = os.getenv("QM_QUANTHK_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/data/quanthk").is_dir():
        return Path("/data/quanthk")
    QUANTHK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTHK_DATA_DIR


def _to_qhk_symbol(code: str) -> str:
    """5位港股代码 → 4位+.HK。00700 → 0700.HK。"""
    code = code.strip().zfill(5)
    if code.startswith("0") and len(code) == 5:
        code = code[1:]
    return f"{code}.HK"


def _read_south_csv(path: Path) -> pd.DataFrame | None:
    """读单个南向资金 CSV（GBK 编码），标准化。"""
    df = None
    for enc in ("gbk", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None or df.empty:
        return None

    # 列：查询日期/股份代号/名称/于中央结算系统的持股量/占已发行股份百分比
    rename = {}
    for col in df.columns:
        if "查询日期" in col:
            rename[col] = "query_date"
        elif "股份代号" in col:
            rename[col] = "stock_code"
        elif "名称" in col and "股票" not in col:
            rename[col] = "stock_name"
        elif "持股量" in col:
            rename[col] = "holding_quantity"
        elif "百分比" in col:
            rename[col] = "holding_percentage"
    df = df.rename(columns=rename)

    if "query_date" not in df.columns or "stock_code" not in df.columns:
        log.debug("跳过 %s：缺少必要列 %s", path.name, list(df.columns))
        return None

    df["query_date"] = pd.to_datetime(df["query_date"], errors="coerce")
    df = df.dropna(subset=["query_date"])
    df["query_date"] = df["query_date"].dt.date

    df["symbol"] = df["stock_code"].astype(str).map(_to_qhk_symbol)
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")
    # 百分比 "11.10%" → 0.111
    df["holding_percentage"] = (
        df["holding_percentage"].astype(str).str.replace("%", "", regex=False).str.strip()
    )
    df["holding_percentage"] = pd.to_numeric(df["holding_percentage"], errors="coerce").fillna(0.0) / 100.0

    df = df.drop_duplicates(subset=["symbol", "query_date"], keep="last")
    df = df[OUT_COLS].dropna(subset=["symbol"])
    return df


def _import_one(csv_path: Path, target_dir: Path) -> tuple[int, bool, str]:
    """导入单个 CSV → (rows, success, error)。"""
    try:
        df = _read_south_csv(csv_path)
        if df is None or df.empty:
            return 0, False, "empty"
        symbol = df["symbol"].iloc[0]
        out = target_dir / f"{symbol}.parquet"
        if out.exists():
            old = pd.read_parquet(out)
            combined = pd.concat([old, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["symbol", "query_date"], keep="last")
            combined.to_parquet(out, index=False)
        else:
            df.to_parquet(out, index=False)
        return len(df), True, ""
    except Exception as exc:  # noqa: BLE001
        return 0, False, str(exc)


def import_south(src_dir: str | None = None, *, dry_run: bool = False,
                 workers: int = 8) -> dict:
    """多线程导入南向资金历史到 quanthk。

    data-hs 每只股票一个 CSV（955 个），用 ThreadPoolExecutor 并行读取落盘。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    src = Path(src_dir or DEFAULT_SRC_DIR)
    if not src.is_dir():
        raise FileNotFoundError(f"数据目录不存在: {src}")

    target_dir = _quanthk_root() / REL_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # 收集所有 CSV（data-hs/{股票名}/南向资金_{名}_{代码}.csv）
    csv_files = list(src.rglob("*.csv"))
    log.info("待导入 CSV: %d 个，线程 %d (%s)", len(csv_files), workers, src)

    if dry_run:
        return {"dir": str(src), "files": len(csv_files), "dry_run": True, "target_dir": str(target_dir)}

    total_rows = 0
    written = 0
    errors = 0
    err_samples = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_import_one, f, target_dir): f for f in csv_files}
        done = 0
        for fut in as_completed(futures):
            done += 1
            rows, success, err = fut.result()
            if success:
                total_rows += rows
                written += 1
            else:
                errors += 1
                if len(err_samples) < 10:
                    err_samples.append(f"{futures[fut].name}: {err}")
            if done % 200 == 0:
                log.info("  进度 %d/%d，累计 %d 行", done, len(csv_files), total_rows)

    return {
        "dir": str(src),
        "files": len(csv_files),
        "stocks_written": written,
        "rows": total_rows,
        "errors": errors,
        "error_samples": err_samples,
        "target_dir": str(target_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="南向资金历史 → QuantHK")
    parser.add_argument("--dir", default=None, help="data-hs 目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写盘")
    parser.add_argument("--workers", type=int, default=8, help="并发线程数")
    args = parser.parse_args()

    try:
        result = import_south(args.dir, dry_run=args.dry_run, workers=args.workers)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("导入失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
