#!/usr/bin/env python3
"""北向季度快照未匹配股票修复 — 用 AHlog 缓存映射表补齐 A 股代码。

data-AH 导入时未匹配的股票用文件名 HKEX 代号落盘（如 77159.HK，标记
unmatched=1）。AHlog 目录的 cache/stock_code_mapping.csv（港股5位→A股6位，
3540条）可修复其中大部分。本脚本把季度快照里的 .HK 未匹配 symbol 替换为
标准 A 股代码，并更新 market / 清除 unmatched 标记。

用法:
  python backend/scripts/quantdb_north_fix_unmatched.py \
    --mapping /media/.../AHlog/cache/stock_code_mapping.csv
  python backend/scripts/quantdb_north_fix_unmatched.py --mapping ... --quarter 2025Q1
  python backend/scripts/quantdb_north_fix_unmatched.py --mapping ... --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quantdb_north_fix_unmatched")

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


def _market_of(code6: str) -> str:
    if code6.startswith(("6", "9")):
        return "SH"
    if code6.startswith(("0", "3", "2")):
        return "SZ"
    return "HK"


def _load_hk_map(mapping_path: str) -> dict[str, str]:
    """读取 stock_code_mapping.csv → {港股5位代号: A股6位代码}。"""
    df = pd.read_csv(mapping_path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    hk_col = next((c for c in df.columns if "港股" in c or "代码" in c), df.columns[0])
    ac_col = next((c for c in df.columns if "A股" in c), None)
    if not ac_col:
        raise ValueError(f"映射表缺少 A股代码 列: {list(df.columns)}")
    hk = df[hk_col].astype(str).str.strip().str.zfill(5)
    ac = df[ac_col].astype(str).str.strip().str.zfill(6)
    return dict(zip(hk, ac))


def fix_unmatched(*, mapping_path: str, quarters: list[str] | None = None,
                  dry_run: bool = False) -> dict:
    """修复季度快照中的 .HK 未匹配 symbol → 标准 A 股代码。"""
    hk_map = _load_hk_map(mapping_path)
    log.info("港股→A股映射: %d 条", len(hk_map))

    base = _quantdb_root() / REL_DIR
    if not base.is_dir():
        return {"status": "skipped", "reason": f"{base} 不存在"}

    q_dirs = sorted(p for p in base.glob("quarter=*") if (p / "data.parquet").is_file())
    if quarters:
        q_dirs = [p for p in q_dirs if p.name[8:] in quarters]

    summary = {"quarters": [], "fixed": 0, "still_unmatched": 0, "etf": 0}
    for p in q_dirs:
        quarter = p.name[8:]
        f = p / "data.parquet"
        df = pd.read_parquet(f)
        if "unmatched" not in df.columns:
            summary["quarters"].append({"quarter": quarter, "action": "no_unmatched_col", "rows": len(df)})
            continue

        um = df["unmatched"].fillna(0) == 1
        n_um = int(um.sum())
        if n_um == 0:
            summary["quarters"].append({"quarter": quarter, "action": "none", "rows": len(df)})
            continue

        # 尝试用映射修复
        fixed_mask = pd.Series(False, index=df.index)
        new_sym = df["symbol"].copy()
        for idx in df.index[um]:
            code = str(df.at[idx, "symbol"]).replace(".HK", "")
            acode = hk_map.get(code)
            if acode:
                new_sym.at[idx] = f"{acode}.{_market_of(acode)}"
                df.at[idx, "market"] = _market_of(acode)
                fixed_mask.at[idx] = True

        n_fixed = int(fixed_mask.sum())
        n_still = n_um - n_fixed
        df.loc[fixed_mask, "unmatched"] = 0

        # 仍无法的：ETF/指数保留（unmatched=1），真股票保留待后续
        summary["fixed"] += n_fixed
        summary["still_unmatched"] += n_still

        if dry_run:
            summary["quarters"].append({
                "quarter": quarter, "rows": len(df), "unmatched_before": n_um,
                "fixed": n_fixed, "still_unmatched": n_still, "action": "dry_run",
            })
            continue

        # 去掉 unmatched 列全为 0 时保留列（保留 unmatched 列，统一 schema）
        df["symbol"] = new_sym
        df.to_parquet(f, index=False)
        summary["quarters"].append({
            "quarter": quarter, "rows": len(df), "unmatched_before": n_um,
            "fixed": n_fixed, "still_unmatched": n_still, "action": "rewritten",
        })
        log.info("[%s] 修复 %d / 未匹配 %d，仍无法 %d", quarter, n_fixed, n_um, n_still)

    summary["status"] = "ok" if not dry_run else "dry_run"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="北向季度快照未匹配股票修复")
    parser.add_argument("--mapping", required=True, help="stock_code_mapping.csv 路径")
    parser.add_argument("--quarter", default=None, help="只修复指定季度，逗号分隔")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    quarters = [q.strip() for q in args.quarter.split(",") if q.strip()] if args.quarter else None
    try:
        result = fix_unmatched(mapping_path=args.mapping, quarters=quarters, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("修复失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
