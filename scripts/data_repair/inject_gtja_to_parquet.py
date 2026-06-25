"""把 16 个 GTJA 因子作为新列写入 2016-2026 全部 feature parquet。

设计:
  1. 每个年份单独处理，避免一次性把 11 GB 数据加载内存
  2. 跨年因子（如 60 日均量）需要前 60 个交易日的 warm-up 数据
     → 加载本年 + 上一年最后 90 天，算因子后只保留本年的行
  3. 写入时保留原 schema，只追加 16 列
  4. 备份原文件以便回滚
  5. 写入完成后输出每年新列的覆盖率，确认无遗漏

输出:
  - /app/db/feature_snapshots/model_features_{YYYY}.parquet 追加 16 列
  - /app/db/feature_snapshots/model_features_{YYYY}.parquet.before_gtja  备份
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, "/app/scripts/data_repair")
from gtja_16_factors import compute_gtja_16


FEATURE_DIR = Path("/app/db/feature_snapshots")
GTJA_COLS = [
    "gtja_alpha_016", "gtja_alpha_032", "gtja_alpha_036", "gtja_alpha_042",
    "gtja_alpha_062", "gtja_alpha_070", "gtja_alpha_074", "gtja_alpha_083",
    "gtja_alpha_090", "gtja_alpha_095", "gtja_alpha_099", "gtja_alpha_150",
    "gtja_alpha_158", "gtja_alpha_159", "gtja_alpha_176", "gtja_alpha_179",
]


def inject_year(year: int, warmup_days: int = 90) -> dict:
    """处理某一年的 parquet，追加 16 个 GTJA 列。"""
    target = FEATURE_DIR / f"model_features_{year}.parquet"
    if not target.exists():
        return {"year": year, "status": "missing", "rows": 0}

    backup = target.parent / f"{target.name}.before_gtja"
    if not backup.exists():
        shutil.copy2(target, backup)
        print(f"  [{year}] backup → {backup.name}")

    # 加载本年 + warm-up 上一年最后 N 天
    prev_year_file = FEATURE_DIR / f"model_features_{year - 1}.parquet"
    pieces = []
    if prev_year_file.exists():
        prev_df = pd.read_parquet(prev_year_file, columns=[
            "symbol", "trade_date", "open", "high", "low", "close", "volume", "liq_amount"
        ])
        # 统一为 datetime64：跨年合并时不同 parquet 可能写不同 dtype
        # (update_feature_parquet 用 .dt.date 写 object，原始数据用 timestamp[ns])
        prev_df["trade_date"] = pd.to_datetime(prev_df["trade_date"])
        prev_max = prev_df["trade_date"].max()
        warmup_cutoff = prev_max - pd.Timedelta(days=warmup_days)
        prev_df = prev_df[prev_df["trade_date"] >= warmup_cutoff]
        pieces.append(prev_df)
        warmup_rows = len(prev_df)
    else:
        warmup_rows = 0

    cur_df = pd.read_parquet(target, columns=[
        "symbol", "trade_date", "open", "high", "low", "close", "volume", "liq_amount"
    ])
    cur_df["trade_date"] = pd.to_datetime(cur_df["trade_date"])
    cur_min = cur_df["trade_date"].min()
    cur_max = cur_df["trade_date"].max()
    pieces.append(cur_df)
    df_compute = pd.concat(pieces, ignore_index=True).drop_duplicates(
        subset=["symbol", "trade_date"], keep="last"
    )

    # 计算 GTJA 16 因子
    t0 = time.time()
    factors = compute_gtja_16(df_compute)
    compute_sec = time.time() - t0

    # 只保留本年行（去掉 warmup）
    factors_cur = factors[
        (factors["trade_date"] >= cur_min) & (factors["trade_date"] <= cur_max)
    ].copy()

    # merge 到当前年 parquet
    cur_full = pd.read_parquet(target)
    before_cols = set(cur_full.columns)
    if "gtja_alpha_016" in before_cols:
        # 已经注入过，先去除
        cur_full = cur_full.drop(columns=[c for c in GTJA_COLS if c in before_cols])

    # 注意 trade_date 类型对齐
    factors_cur["trade_date"] = pd.to_datetime(factors_cur["trade_date"])
    cur_full["trade_date"] = pd.to_datetime(cur_full["trade_date"])

    merged = cur_full.merge(
        factors_cur[["symbol", "trade_date"] + GTJA_COLS],
        on=["symbol", "trade_date"], how="left",
    )

    # 覆盖率检查
    coverage = {col: merged[col].notna().sum() / len(merged) for col in GTJA_COLS}

    # 写回
    table = pa.Table.from_pandas(merged, preserve_index=False)
    pq.write_table(table, target, compression="snappy")

    return {
        "year": year,
        "status": "ok",
        "rows": len(merged),
        "warmup_rows": warmup_rows,
        "compute_sec": round(compute_sec, 1),
        "coverage": coverage,
    }


def main():
    print("=== GTJA 16 因子注入 2016-2026 parquet ===\n")
    overall_t0 = time.time()

    results = []
    for year in range(2016, 2027):
        print(f"\n[{year}]")
        try:
            r = inject_year(year)
            results.append(r)
            print(f"  status: {r['status']}")
            if r["status"] == "ok":
                print(f"  rows: {r['rows']:,}  warmup: {r['warmup_rows']:,}  compute: {r['compute_sec']}s")
                low_cov = [(k, v) for k, v in r["coverage"].items() if v < 0.5]
                if low_cov:
                    print(f"  ⚠️  低覆盖率: {[(k, f'{v*100:.1f}%') for k, v in low_cov]}")
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            results.append({"year": year, "status": "error", "error": str(e)})

    print(f"\n=== 总耗时: {time.time()-overall_t0:.0f}s ===\n")
    print("覆盖率总览（avg, min）:")
    print(f"{'年':<6s}", end="")
    for col in GTJA_COLS:
        print(f"{col[-7:]:>10s}", end="")
    print()
    for r in results:
        if r["status"] != "ok":
            continue
        print(f"{r['year']:<6d}", end="")
        for col in GTJA_COLS:
            cov = r["coverage"].get(col, 0)
            print(f"{cov*100:>9.1f}%", end="")
        print()


if __name__ == "__main__":
    main()
