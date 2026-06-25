"""计算 GTJA 16 个因子的 IC + ICIR + 分行情 IC。

在 2024 年全量数据上算：
  1. 整体 IC (T+10 收益)
  2. 整体 ICIR
  3. 分行情 IC（牛市 / 熊市段）
  4. 覆盖率

参考：用户提示的因子用法：
  - 正向 6 (83, 62, 90, 99, 32, 16): 整体 IC 应 > 0
  - 反向 6 (176, 74, 70, 36, 179, 150): 整体 IC 应 < 0
  - 分行情 6 (70, 158, 42, 159, 150, 95): 牛/熊市 IC 不同方向
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/app/scripts/data_repair")
from gtja_16_factors import compute_gtja_16


PARQUET = "/app/db/feature_snapshots/model_features_2024.parquet"

# 用户标记
USER_LABELS = {
    "gtja_alpha_016": "正向",
    "gtja_alpha_032": "正向",
    "gtja_alpha_062": "正向",
    "gtja_alpha_083": "正向",
    "gtja_alpha_090": "正向",
    "gtja_alpha_099": "正向",
    "gtja_alpha_036": "反向",
    "gtja_alpha_070": "反向/分行情",  # 也在分行情列表
    "gtja_alpha_074": "反向",
    "gtja_alpha_150": "反向/分行情",  # 也在分行情列表
    "gtja_alpha_176": "反向",
    "gtja_alpha_179": "反向",
    "gtja_alpha_042": "分行情",
    "gtja_alpha_095": "分行情",
    "gtja_alpha_158": "分行情",
    "gtja_alpha_159": "分行情",
}


def calculate_ic(factor_df: pd.DataFrame, label_col: str = "future_ret_10d") -> dict:
    """对每个因子算 IC、ICIR、覆盖率。"""
    factor_cols = [c for c in factor_df.columns if c.startswith("gtja_")]

    results = {}
    for col in factor_cols:
        # 每日横截面 Spearman 相关
        daily_ic = factor_df.groupby("trade_date").apply(
            lambda g: g[col].corr(g[label_col], method="spearman")
            if g[col].notna().sum() > 10 else np.nan
        )
        daily_ic = daily_ic.dropna()

        if len(daily_ic) < 10:
            results[col] = {
                "ic_mean": np.nan, "ic_std": np.nan, "icir": np.nan,
                "n_days": 0, "ic_pos_pct": np.nan,
                "coverage": factor_df[col].notna().sum() / len(factor_df),
            }
            continue

        ic_mean = daily_ic.mean()
        ic_std = daily_ic.std()
        icir = ic_mean / ic_std * np.sqrt(252) if ic_std > 1e-10 else np.nan
        results[col] = {
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "icir": icir,
            "n_days": len(daily_ic),
            "ic_pos_pct": (daily_ic > 0).mean(),
            "coverage": factor_df[col].notna().sum() / len(factor_df),
        }

    return results


def calculate_ic_by_regime(factor_df: pd.DataFrame, bench_returns: pd.Series,
                            label_col: str = "future_ret_10d") -> dict:
    """按市场行情分段算 IC。

    bench_returns: 基准指数（沪深300）的 trade_date → daily_ret 映射
    """
    # 用基准 20 日累计收益判断牛/熊
    bench_cumret = (1 + bench_returns).rolling(20).apply(np.prod) - 1
    bull_dates = bench_cumret[bench_cumret > 0.03].index   # 20日+3%
    bear_dates = bench_cumret[bench_cumret < -0.03].index  # 20日-3%
    neutral_dates = bench_cumret[(bench_cumret >= -0.03) & (bench_cumret <= 0.03)].index

    print(f"  牛市段日数: {len(bull_dates)}")
    print(f"  熊市段日数: {len(bear_dates)}")
    print(f"  震荡段日数: {len(neutral_dates)}")

    factor_cols = [c for c in factor_df.columns if c.startswith("gtja_")]
    results = {}

    for col in factor_cols:
        bull_ic = factor_df[factor_df["trade_date"].isin(bull_dates)].groupby("trade_date").apply(
            lambda g: g[col].corr(g[label_col], method="spearman")
            if g[col].notna().sum() > 10 else np.nan
        ).mean()
        bear_ic = factor_df[factor_df["trade_date"].isin(bear_dates)].groupby("trade_date").apply(
            lambda g: g[col].corr(g[label_col], method="spearman")
            if g[col].notna().sum() > 10 else np.nan
        ).mean()
        neut_ic = factor_df[factor_df["trade_date"].isin(neutral_dates)].groupby("trade_date").apply(
            lambda g: g[col].corr(g[label_col], method="spearman")
            if g[col].notna().sum() > 10 else np.nan
        ).mean()

        results[col] = {
            "bull_ic": bull_ic,
            "bear_ic": bear_ic,
            "neut_ic": neut_ic,
        }
    return results


def main():
    print("=== 加载 2024 数据 ===")
    t0 = time.time()
    df = pd.read_parquet(PARQUET, columns=[
        "symbol", "trade_date", "open", "high", "low", "close", "volume", "liq_amount"
    ])
    print(f"  数据: {len(df):,} 行 × {df['symbol'].nunique():,} 票 × {df['trade_date'].nunique()} 天")
    print(f"  耗时: {time.time()-t0:.1f}s")

    print("\n=== 计算 16 个 GTJA 因子 ===")
    t0 = time.time()
    factors = compute_gtja_16(df)
    print(f"  耗时: {time.time()-t0:.1f}s")
    print(f"  因子数据: {len(factors):,} 行 × {factors.shape[1]} 列")

    # 算 T+10 收益（用 close）
    print("\n=== 算 T+10 收益（label）===")
    df = df.sort_values(["symbol", "trade_date"])
    df["future_ret_10d"] = df.groupby("symbol")["close"].shift(-10) / df["close"] - 1
    # 删掉收益异常的（指数 / 复权切换边界）
    df = df[df["future_ret_10d"].abs() < 0.5]
    print(f"  有效 label: {df['future_ret_10d'].notna().sum():,}")

    # merge
    merged = factors.merge(df[["symbol", "trade_date", "future_ret_10d"]],
                            on=["symbol", "trade_date"], how="inner")
    print(f"  merged: {len(merged):,} 行")

    print("\n=== 整体 IC ===")
    ic_results = calculate_ic(merged)
    print(f"\n{'因子':<22s} {'类型':<14s} {'IC':>8s} {'ICIR':>8s} {'IC>0%':>8s} {'覆盖率':>8s}")
    print("-" * 80)
    for col, r in sorted(ic_results.items(), key=lambda x: -abs(x[1].get("ic_mean", 0) or 0)):
        label = USER_LABELS.get(col, "?")
        ic = r["ic_mean"]
        icir = r["icir"]
        pos = r["ic_pos_pct"]
        cov = r["coverage"]
        if ic is None or np.isnan(ic):
            print(f"{col:<22s} {label:<14s} {'NaN':>8s} {'NaN':>8s} {'NaN':>8s} {cov*100:>7.1f}%")
        else:
            print(f"{col:<22s} {label:<14s} {ic:>+8.4f} {icir:>+8.4f} {pos*100:>7.1f}% {cov*100:>7.1f}%")

    # 分行情：用市值大的 ETF 替代基准（这里用所有股票的等权日均收益作 proxy）
    print("\n=== 分行情 IC（用全市场等权日均收益作 proxy）===")
    df["daily_ret"] = df.groupby("symbol")["close"].pct_change()
    market_ret = df.groupby("trade_date")["daily_ret"].mean()
    regime_results = calculate_ic_by_regime(merged, market_ret)
    print(f"\n{'因子':<22s} {'类型':<14s} {'牛市IC':>10s} {'震荡IC':>10s} {'熊市IC':>10s}")
    print("-" * 80)
    for col in sorted(regime_results.keys()):
        r = regime_results[col]
        label = USER_LABELS.get(col, "?")
        bull = r["bull_ic"] if not np.isnan(r["bull_ic"]) else 0
        bear = r["bear_ic"] if not np.isnan(r["bear_ic"]) else 0
        neut = r["neut_ic"] if not np.isnan(r["neut_ic"]) else 0
        flip = "✓ flip" if bull * bear < 0 else ""
        print(f"{col:<22s} {label:<14s} {bull:>+10.4f} {neut:>+10.4f} {bear:>+10.4f}  {flip}")

    # 保存结果
    out_csv = "/app/scripts/data_repair/gtja_16_ic_report_2024.csv"
    rows = []
    for col, r in ic_results.items():
        regime = regime_results.get(col, {})
        rows.append({
            "factor": col,
            "user_label": USER_LABELS.get(col, ""),
            "ic_mean": r["ic_mean"],
            "icir": r["icir"],
            "ic_pos_pct": r["ic_pos_pct"],
            "coverage": r["coverage"],
            "n_days": r["n_days"],
            "bull_ic": regime.get("bull_ic", np.nan),
            "neut_ic": regime.get("neut_ic", np.nan),
            "bear_ic": regime.get("bear_ic", np.nan),
        })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"\n报告保存: {out_csv}")


if __name__ == "__main__":
    main()
