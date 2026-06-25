"""方案 C：清洗 2026-05-06 起的数据，4.30 之前保留不动。

数据真相：
  - 2026-04-30 及之前 prefix（如 SH600519）= 老标度（被 per-symbol 错缩放，但内部连续）
  - 2026-05-06 起 prefix + suffix 双写：suffix 是正确复权价，prefix 部分票被错算
  - 2026-06-11 起 prefix 完全消失，仅 suffix 存在
  - 5 个指数（000300.SH 等）混入个股表，污染横截面

清洗动作（5.6 之后，4.30 之前不动）：
  1. 删 5 个指数行（× 2 格式 = 5+5 个 symbol，全部在 2026 段）
  2. 删 5.6 起所有 prefix 行（保留 suffix，因为 suffix 是真复权值）
  3. 把留下的 suffix（600519.SH）重命名为 prefix（SH600519）以与 4.30 之前格式统一
  4. 6.23/6.24 沪市缺失保持现状（不引入新数据源）

作用域：
  - PostgreSQL: stock_daily_latest
  - Parquet: /app/db/feature_snapshots/model_features_2026.parquet
  - 2016-2025 年份 parquet 不动

使用：
  # PG dry-run
  python cleanup_v3_plan_c.py pg --dry-run
  # PG 真改
  python cleanup_v3_plan_c.py pg --apply
  # Parquet dry-run
  python cleanup_v3_plan_c.py parquet --dry-run
  # Parquet 真改（自动备份 .before_cleanup_v3）
  python cleanup_v3_plan_c.py parquet --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import asyncpg
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

INDEX_SYMBOLS = {
    "000300.SH", "000852.SH", "000905.SH", "000906.SH", "399300.SZ",
    "SH000300", "SH000852", "SH000905", "SH000906", "SZ399300",
}

CUTOFF_DATE = date(2026, 5, 6)  # 这天起改用 suffix 行（含），4.30 是最后一天 prefix 老标度
CUTOFF_DATE_STR = "2026-05-06"

PARQUET_2026 = Path("/app/db/feature_snapshots/model_features_2026.parquet")


def _suffix_to_prefix(sym: str) -> str:
    """600519.SH -> SH600519. 已是 prefix 或非标准格式则原样返回。"""
    if sym.endswith(".SH") and sym[:-3].isdigit():
        return f"SH{sym[:-3]}"
    if sym.endswith(".SZ") and sym[:-3].isdigit():
        return f"SZ{sym[:-3]}"
    if sym.endswith(".BJ") and sym[:-3].isdigit():
        return f"BJ{sym[:-3]}"
    return sym


# ============================================================
# PostgreSQL
# ============================================================
async def clean_pg(dry_run: bool):
    # DATABASE_URL 在容器内带 +asyncpg driver 前缀，asyncpg.connect 不接受，要剥掉
    dsn = os.environ.get("DATABASE_URL", "")
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    if not dsn:
        # fallback：从 DB_* 拼
        dsn = (
            f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
            f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
        )
    conn = await asyncpg.connect(dsn)
    try:
        if dry_run:
            print("=== PG dry-run ===")
            r = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE symbol = ANY($1)) as idx_rows,
                  COUNT(*) FILTER (WHERE symbol ~ '^(SH|SZ|BJ)[0-9]+$' AND trade_date >= $2) as late_prefix,
                  COUNT(*) FILTER (WHERE symbol ~ '^[0-9]+\.(SH|SZ|BJ)$' AND trade_date >= $2) as late_suffix,
                  COUNT(*) as total
                FROM stock_daily_latest
                """,
                list(INDEX_SYMBOLS), CUTOFF_DATE,
            )
            print(f"  total rows         : {r['total']:,}")
            print(f"  待删 5 个指数行    : {r['idx_rows']:,}")
            print(f"  待删 5.6 起 prefix : {r['late_prefix']:,}")
            print(f"  待重命名 suffix    : {r['late_suffix']:,}")
            return

        print("=== PG apply ===")
        async with conn.transaction():
            t0 = time.time()
            # 1. 删指数
            n1 = await conn.execute(
                "DELETE FROM stock_daily_latest WHERE symbol = ANY($1)",
                list(INDEX_SYMBOLS),
            )
            print(f"  step 1 删指数: {n1}")

            # 2. 删 5.6 起 prefix
            n2 = await conn.execute(
                "DELETE FROM stock_daily_latest "
                "WHERE symbol ~ '^(SH|SZ|BJ)[0-9]+$' AND trade_date >= $1",
                CUTOFF_DATE,
            )
            print(f"  step 2 删 5.6 起 prefix: {n2}")

            # 3. 5.6 起 suffix -> prefix（用 SQL 直接重写 symbol）
            #    SH/SZ/BJ 三个市场分别处理
            for mkt in ("SH", "SZ", "BJ"):
                n = await conn.execute(
                    """
                    UPDATE stock_daily_latest
                    SET symbol = $1 || SUBSTRING(symbol FROM 1 FOR 6)
                    WHERE symbol ~ ('^[0-9]+\.' || $1 || '$')
                      AND trade_date >= $2
                    """,
                    mkt, CUTOFF_DATE,
                )
                print(f"  step 3 重命名 .{mkt}: {n}")

            elapsed = time.time() - t0
            print(f"  done in {elapsed:.1f}s")
    finally:
        await conn.close()


# ============================================================
# Parquet
# ============================================================
def clean_parquet(dry_run: bool):
    target = PARQUET_2026
    if not target.exists():
        print(f"ERROR: {target} 不存在")
        sys.exit(1)

    if dry_run:
        print("=== Parquet dry-run ===")
        df = pd.read_parquet(target, columns=["symbol", "trade_date"])
        df["symbol"] = df["symbol"].astype(str)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        is_prefix = df["symbol"].str.match(r"^(SH|SZ|BJ)\d+$")
        is_suffix = df["symbol"].str.match(r"^\d+\.(SH|SZ|BJ)$")
        is_idx = df["symbol"].isin(INDEX_SYMBOLS)
        late = df["trade_date"] >= pd.Timestamp(CUTOFF_DATE)
        print(f"  total rows         : {len(df):,}")
        print(f"  待删指数           : {is_idx.sum():,}")
        print(f"  待删 5.6 起 prefix : {(is_prefix & late).sum():,}")
        print(f"  待重命名 suffix    : {(is_suffix & late).sum():,}")
        keep = (is_prefix & ~late & ~is_idx).sum() + (is_suffix & late & ~is_idx).sum()
        print(f"  清洗后保留行数     : {keep:,}")
        return

    print("=== Parquet apply ===")
    backup = target.with_suffix(target.suffix + ".before_cleanup_v3")
    if not backup.exists():
        print(f"  backup -> {backup.name}")
        shutil.copy2(target, backup)

    t0 = time.time()
    df = pd.read_parquet(target)
    df["symbol"] = df["symbol"].astype(str)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    n_before = len(df)
    is_prefix = df["symbol"].str.match(r"^(SH|SZ|BJ)\d+$")
    is_suffix = df["symbol"].str.match(r"^\d+\.(SH|SZ|BJ)$")
    is_idx = df["symbol"].isin(INDEX_SYMBOLS)
    late = df["trade_date"] >= pd.Timestamp(CUTOFF_DATE)

    # 1. 删指数
    df = df[~is_idx].copy()
    is_prefix = df["symbol"].str.match(r"^(SH|SZ|BJ)\d+$")
    is_suffix = df["symbol"].str.match(r"^\d+\.(SH|SZ|BJ)$")
    late = df["trade_date"] >= pd.Timestamp(CUTOFF_DATE)
    print(f"  step 1 删指数: {n_before - len(df)} 行")

    # 2. 删 5.6 起 prefix
    n_before_2 = len(df)
    df = df[~(is_prefix & late)].copy()
    print(f"  step 2 删 5.6 起 prefix: {n_before_2 - len(df)} 行")

    # 3. 5.6 起 suffix -> prefix
    is_suffix = df["symbol"].str.match(r"^\d+\.(SH|SZ|BJ)$")
    late = df["trade_date"] >= pd.Timestamp(CUTOFF_DATE)
    rename_mask = is_suffix & late
    n_rename = rename_mask.sum()
    df.loc[rename_mask, "symbol"] = df.loc[rename_mask, "symbol"].map(_suffix_to_prefix)
    print(f"  step 3 重命名 suffix -> prefix: {n_rename} 行")

    # 校验：清洗后 symbol 应该全部是 prefix 格式
    bad = df[~df["symbol"].str.match(r"^(SH|SZ|BJ)\d+$")]
    if not bad.empty:
        print(f"  ⚠️  清洗后仍有 {len(bad)} 行非 prefix 格式: {bad['symbol'].unique()[:10]}")

    # 校验：4.30 之前不应被修改
    old_after = df[df["trade_date"] <= pd.Timestamp("2026-04-30")]
    print(f"  4.30 及之前保留: {len(old_after):,} 行 (应等于 dry-run 值)")

    # 写回
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, target, compression="snappy")
    elapsed = time.time() - t0
    print(f"  写回 {target.name}: {len(df):,} 行, {elapsed:.1f}s")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["pg", "parquet", "all"])
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dry = args.dry_run
    if args.target in ("pg", "all"):
        asyncio.run(clean_pg(dry))
    if args.target in ("parquet", "all"):
        clean_parquet(dry)


if __name__ == "__main__":
    main()
