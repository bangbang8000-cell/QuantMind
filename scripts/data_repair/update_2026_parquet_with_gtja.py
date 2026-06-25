#!/usr/bin/env python3
"""增量更新 model_features_2026.parquet 的一站式调度器。

把现有的两个脚本串起来:
    Step 1. update_feature_parquet.py
            从 stock_daily_latest 读 2026-05+ 新数据，算 ~150 个特征，写到 parquet
    Step 2. inject_gtja_to_parquet.py (年度模式或单年模式)
            重新算 GTJA 16 因子（warm-up 从 2026-01 开始）覆盖整个 2026 parquet

设计原则:
    - 不修改 update_feature_parquet.py 主流程（脚本能算 184 列，远超我们 47 列需求，
      多算的列不影响存储和后续使用）
    - GTJA 因子必须在 update_feature_parquet 之后跑（因为 GTJA 依赖 OHLCV，
      而 update 会写新一批 OHLCV 行）
    - 每步失败立即停止，避免半成品状态

用法:
    docker exec quantmind python /app/scripts/data_repair/update_2026_parquet_with_gtja.py [--dry-run] [--since YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


SCRIPTS = {
    "update_feature": "/app/backend/scripts/update_feature_parquet.py",
    "inject_gtja": "/app/scripts/data_repair/inject_gtja_to_parquet.py",
}
PARQUET = Path("/app/db/feature_snapshots/model_features_2026.parquet")


def run_script(name: str, args: list[str], log_path: str) -> int:
    """跑一个脚本，stdout/stderr 写文件并实时 tail。"""
    script = SCRIPTS[name]
    cmd = ["python", script] + args
    print(f"\n=== [{name}] 执行: {' '.join(cmd)}")
    print(f"    log: {log_path}")
    print(f"    开始时间: {time.strftime('%H:%M:%S')}")

    t0 = time.time()
    with open(log_path, "w") as logf:
        # subprocess 跑脚本 + tee 到 stdout（用户能看到关键 log）
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        last_print = 0
        while proc.poll() is None:
            time.sleep(5)
            elapsed = time.time() - t0
            # 每 30 秒打印一次进度
            if elapsed - last_print >= 30:
                # 取最近一行 [HH:MM:SS] 开头的 log
                try:
                    result = subprocess.run(
                        ["sh", "-c", f"grep -E '^\\[|进度|完成|写入' {log_path} | tail -3"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout:
                        print(f"  [{int(elapsed)}s] 最近进度:")
                        for ln in result.stdout.strip().split("\n"):
                            print(f"    {ln}")
                except Exception:
                    pass
                last_print = elapsed
        proc.wait()
    elapsed = time.time() - t0
    print(f"  完成: 退出码={proc.returncode}, 耗时={elapsed:.0f}s")
    return proc.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="补数据起始日 YYYY-MM-DD（默认自动检测）")
    ap.add_argument("--dry-run", action="store_true", help="只读，不实际写入")
    ap.add_argument("--skip-update", action="store_true", help="跳过 Step 1（已跑过）")
    ap.add_argument("--skip-gtja", action="store_true", help="跳过 Step 2（已跑过）")
    args = ap.parse_args()

    # 校验前置
    if not PARQUET.exists():
        print(f"ERROR: parquet 不存在: {PARQUET}")
        return 1
    for name, p in SCRIPTS.items():
        if not Path(p).exists():
            print(f"ERROR: 脚本不存在: [{name}] {p}")
            return 1

    print("=" * 70)
    print(" QuantMind 2026 Parquet 增量更新（含 GTJA 16 因子）")
    print("=" * 70)
    print(f"目标: {PARQUET}")
    print(f"dry_run: {args.dry_run}")
    print(f"skip_update: {args.skip_update}, skip_gtja: {args.skip_gtja}")

    # ── Step 1: 跑 update_feature_parquet ───────────────────────────
    if not args.skip_update:
        cli = []
        if args.since:
            cli += ["--since", args.since]
        if args.dry_run:
            cli += ["--dry-run"]
        rc = run_script("update_feature", cli, "/tmp/update_feature.log")
        if rc != 0:
            print(f"\n❌ Step 1 失败 (rc={rc})。详见 /tmp/update_feature.log")
            return rc
        print(f"\n✅ Step 1 完成: parquet 已扩展到 2026-06-24")
    else:
        print("\n⏭  跳过 Step 1")

    if args.dry_run:
        print("\n[DRY-RUN] 不跑 GTJA")
        return 0

    # ── Step 2: 跑 GTJA 16 因子重算（覆盖 2026 全年）─────────────────
    if not args.skip_gtja:
        rc = run_script("inject_gtja", [], "/tmp/inject_gtja_after_update.log")
        if rc != 0:
            print(f"\n❌ Step 2 失败 (rc={rc})。详见 /tmp/inject_gtja_after_update.log")
            return rc
        print(f"\n✅ Step 2 完成: GTJA 16 因子已覆盖 2016-2026 全部 parquet")
    else:
        print("\n⏭  跳过 Step 2")

    # ── Step 3: 最终验证 ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  最终验证")
    print("=" * 70)
    import pandas as pd
    df = pd.read_parquet(str(PARQUET), columns=["symbol", "trade_date"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    print(f"  行数: {len(df):,}")
    print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    print(f"  symbols: {df['symbol'].nunique():,}")

    # 看 GTJA 列覆盖率（最新交易日）
    latest = df["trade_date"].max()
    df_latest = pd.read_parquet(str(PARQUET))
    df_latest["trade_date"] = pd.to_datetime(df_latest["trade_date"]).dt.date
    df_latest = df_latest[df_latest["trade_date"] == latest]
    gtja_cols = [c for c in df_latest.columns if c.startswith("gtja_alpha_")]
    print(f"\n  最新日 {latest} GTJA 因子覆盖率:")
    for c in sorted(gtja_cols):
        n = df_latest[c].notna().sum()
        pct = n / len(df_latest) * 100
        print(f"    {c}: {n}/{len(df_latest)} ({pct:.1f}%)")

    print("\n✅ 全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
