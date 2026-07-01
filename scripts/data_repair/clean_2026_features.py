"""修复 2026 parquet 特征质量 + catalog 排除坏特征。

四项修复:
  1. catalog default_selected 排除 10 个坏特征（全0 / 89%NaN / 全 inf）
     - 全0 placeholder: flow_qsp, style_size_percentile, ind_strength_60, ind_relative_volume_20
     - 高NaN（行业/基本面数据未回填）: style_bp, style_ep_ttm,
       ind_ret_1d, ind_ret_20d, ind_strength_20, ind_momentum_rank_20
  2. winsorize mom_ret_* 极端值（除权跳变/新股异常），clip 到 ±0.2
  3. 清洗 GTJA 因子 inf/nan（gtja_alpha_042/062/176 含 inf），inf→nan→ffill
  4. flow_vpin 系列恒等于 0.999 问题：标注但不修（计算逻辑 bug，需另查；
     flow_vpin_ma_20 在 catalog 但区分度极低，从 default_selected 移除）

作用域:
  - config/features/model_training_feature_catalog_v1.json（catalog）
  - db/feature_snapshots/model_features_2026.parquet（特征清洗）

使用:
  python clean_2026_features.py catalog --dry-run   # 看 catalog 改动
  python clean_2026_features.py catalog --apply
  python clean_2026_features.py parquet --apply     # 清洗 parquet（自动备份）
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CATALOG_PATH = Path("/app/config/features/model_training_feature_catalog_v1.json")
PARQUET_2026 = Path("/app/db/feature_snapshots/model_features_2026.parquet")

# default_selected 需改为 False 的坏特征 + 原因
BAD_FEATURES = {
    "flow_qsp": "全0 placeholder（_compute_industry_features 未计算）",
    "style_size_percentile": "全0 placeholder",
    "ind_strength_60": "全0 placeholder",
    "ind_relative_volume_20": "全0 placeholder",
    "style_bp": "73% NaN（基本面数据未回填，Phase 2）",
    "style_ep_ttm": "73% NaN（基本面数据未回填，Phase 2）",
    "ind_ret_1d": "73.7% NaN（industry 列仅 27% 填充）",
    "ind_ret_20d": "89.2% NaN",
    "ind_strength_20": "89.2% NaN",
    "ind_momentum_rank_20": "89.2% NaN",
    "flow_vpin_ma_20": "恒定 0.998（std=0.016，区分度极低，计算 bug 待查）",
}

# winsorize 的动量特征（clip 到 ±0.2，A 股日涨跌停 ±10%×复权，0.2 已很宽）
WINSORIZE_COLS = ["mom_ret_1d", "mom_ret_3d", "mom_ret_5d"]
WINSORIZE_LIMIT = 0.2

# 含 inf 的 GTJA 因子
GTJA_INF_COLS = ["gtja_alpha_042", "gtja_alpha_062", "gtja_alpha_176"]


def fix_catalog(apply: bool):
    cat = json.loads(CATALOG_PATH.read_text())
    changed = []
    for c in cat.get("categories", []):
        for feat in c.get("features", []):
            key = feat.get("key")
            if key in BAD_FEATURES and feat.get("default_selected"):
                changed.append((key, BAD_FEATURES[key]))
                if apply:
                    feat["default_selected"] = False
    print(f"=== catalog {'apply' if apply else 'dry-run'} ===")
    print(f"将 {len(changed)} 个特征 default_selected 改为 False:")
    for k, reason in changed:
        print(f"  {k:28s}  ({reason})")
    if apply:
        # 更新 feature_count 等？保持原值，只改 flag
        CATALOG_PATH.write_text(json.dumps(cat, ensure_ascii=False, indent=2))
        print(f"\n已写回 {CATALOG_PATH}")


def clean_parquet(apply: bool):
    if not apply:
        print("=== parquet dry-run（用 --apply 真改）===")
        print("将执行: 1) winsorize mom_ret_{1d,3d,5d} ±0.2")
        print("        2) GTJA inf→nan→按 symbol ffill")
        print("        3) 所有 inf→nan（全表兜底）")
        return

    backup = PARQUET_2026.with_suffix(".parquet.before_clean_feat")
    if not backup.exists():
        print(f"backup -> {backup.name}")
        shutil.copy2(PARQUET_2026, backup)

    print("=== parquet apply ===")
    df = pd.read_parquet(PARQUET_2026)
    df["symbol"] = df["symbol"].astype(str)
    n_before = len(df)

    # 1. winsorize 动量极端值
    for col in WINSORIZE_COLS:
        if col in df.columns:
            clipped = df[col].clip(-WINSORIZE_LIMIT, WINSORIZE_LIMIT)
            n_changed = (clipped != df[col]).sum()
            df[col] = clipped
            print(f"  winsorize {col}: clip {n_changed} 行到 ±{WINSORIZE_LIMIT}")

    # 2. 全表 inf → nan（兜底，含 GTJA）
    n_inf_total = 0
    for col in df.columns:
        if df[col].dtype.kind in "fi":
            mask = np.isinf(df[col])
            n = mask.sum()
            if n:
                df.loc[mask, col] = np.nan
                n_inf_total += n
    print(f"  inf→nan: 共 {n_inf_total} 个单元格")

    # 3. GTJA inf 行按 symbol ffill（inf 已转 nan，这里补 nan）
    for col in GTJA_INF_COLS:
        if col in df.columns:
            before = df[col].isna().sum()
            df[col] = df.groupby("symbol")[col].ffill()
            after = df[col].isna().sum()
            print(f"  ffill {col}: nan {before}→{after}")

    # 写回
    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, PARQUET_2026, compression="snappy")
    print(f"\n写回 {PARQUET_2026.name}: {len(df)} 行（原 {n_before}）")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target", choices=["catalog", "parquet", "all"])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if args.target in ("catalog", "all"):
        fix_catalog(args.apply)
    if args.target in ("parquet", "all"):
        clean_parquet(args.apply)


if __name__ == "__main__":
    main()
