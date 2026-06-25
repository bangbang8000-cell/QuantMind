#!/usr/bin/env python3
"""
因子评估脚本 - 科学筛选有效因子
=================================

评估维度:
1. IC (Information Coefficient) - 因子值与未来收益的相关性
2. ICIR (IC Information Ratio) - IC 的稳定性 (均值/标准差)
3. Rank IC - Spearman 秩相关，对异常值更鲁棒
4. 因子衰减 - IC 随预测窗口延长的变化
5. 因子相关性 - 识别冗余因子
6. 因子单调性 - 分5组后收益是否单调递增

用法:
    python evaluate_factors.py                    # 评估全部因子
    python evaluate_factors.py --top 30           # 只看 Top 30
    python evaluate_factors.py --category momentum # 按类别筛选
    python evaluate_factors.py --export           # 导出推荐因子列表

输出:
    - 因子 IC/ICIR 排名表
    - 因子相关性热力图
    - 推荐因子列表 (去冗余后)
"""

import argparse
import os
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# 路径配置
if os.path.exists("/app") and not os.environ.get("QUANTMIND_HOST_MODE"):
    PARQUET_PATH = Path("/app/db/feature_snapshots/model_features_2026.parquet")
    OUTPUT_DIR = Path("/app/db/feature_snapshots")
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    PARQUET_PATH = PROJECT_ROOT / "db" / "feature_snapshots" / "model_features_2026.parquet"
    OUTPUT_DIR = PROJECT_ROOT / "db" / "feature_snapshots"


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ═══════════════════════════════════════════════════════════════════════════
# 因子分类
# ═══════════════════════════════════════════════════════════════════════════

FACTOR_CATEGORIES = {
    "momentum": ["mom_"],
    "volatility": ["vol_"],
    "liquidity": ["liq_"],
    "flow": ["flow_"],
    "style": ["style_"],
    "kline": ["kline_", "prel_"],
    "tech": ["tech_"],
    "alpha": ["alpha_"],
    "fundamental": ["fund_", "pe_", "pb_", "roe", "bp", "ep_"],
    "industry": ["ind_"],
    "trend": ["trend_", "consecutive_"],
    "price_position": ["price_position", "dist_to_", "ret_rank"],
}


def get_factor_category(col: str) -> str:
    """根据列名前缀判断因子类别"""
    for cat, prefixes in FACTOR_CATEGORIES.items():
        for prefix in prefixes:
            if col.startswith(prefix):
                return cat
    return "other"


# ═══════════════════════════════════════════════════════════════════════════
# IC 计算
# ═══════════════════════════════════════════════════════════════════════════

def compute_ic_series(
    df: pd.DataFrame,
    factor_col: str,
    forward_col: str = "fwd_ret_5d",
    method: str = "spearman",
) -> pd.Series:
    """
    计算因子的每日 IC 序列

    Args:
        df: 包含 symbol, trade_date, factor_col, forward_col 的 DataFrame
        factor_col: 因子列名
        forward_col: 未来收益列名
        method: 'spearman' (Rank IC) 或 'pearson' (Normal IC)

    Returns:
        IC 时间序列 (index=trade_date)
    """
    # 按日期分组计算截面相关
    ic_series = df.groupby("trade_date").apply(
        lambda g: g[[factor_col, forward_col]].corr(method=method).iloc[0, 1]
        if len(g) > 10 and g[factor_col].std() > 1e-8 else np.nan
    )
    return ic_series.dropna()


def compute_ic_stats(ic_series: pd.Series, name: str = "") -> dict:
    """计算 IC 统计指标"""
    if len(ic_series) < 5:
        return {
            "factor": name,
            "ic_mean": np.nan,
            "ic_std": np.nan,
            "icir": np.nan,
            "ic_positive_ratio": np.nan,
            "ic_abs_mean": np.nan,
            "sample_days": len(ic_series),
        }

    ic_mean = ic_series.mean()
    ic_std = ic_series.std()
    icir = ic_mean / ic_std if ic_std > 1e-8 else 0

    return {
        "factor": name,
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "icir": icir,
        "ic_positive_ratio": (ic_series > 0).mean(),  # IC > 0 的比例
        "ic_abs_mean": ic_series.abs().mean(),
        "sample_days": len(ic_series),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 因子分组收益 (分位数分析)
# ═══════════════════════════════════════════════════════════════════════════

def compute_quantile_returns(
    df: pd.DataFrame,
    factor_col: str,
    forward_col: str = "fwd_ret_5d",
    n_quantiles: int = 5,
) -> dict:
    """
    按因子值分 N 组，计算各组平均收益

    理想情况: 从 Q1 到 Q5 收益单调递增 (做多 Q5, 做空 Q1)

    Returns:
        {
            "q1_ret": 最低组平均收益,
            "q5_ret": 最高组平均收益,
            "long_short": Q5 - Q1 (多空收益),
            "monotonic": 是否单调 (bool),
        }
    """
    result = {}

    # 对每个日期分组
    daily_qret = []
    for dt, g in df.groupby("trade_date"):
        if len(g) < n_quantiles * 5:  # 样本太少跳过
            continue
        try:
            g = g.copy()
            g["quantile"] = pd.qcut(g[factor_col], n_quantiles, labels=False, duplicates="drop")
            qret = g.groupby("quantile")[forward_col].mean()
            daily_qret.append(qret)
        except Exception:
            continue

    if not daily_qret:
        return {"q1_ret": np.nan, "q5_ret": np.nan, "long_short": np.nan, "monotonic": False}

    avg_qret = pd.DataFrame(daily_qret).mean()

    q1_ret = avg_qret.iloc[0] if len(avg_qret) > 0 else np.nan
    q5_ret = avg_qret.iloc[-1] if len(avg_qret) > 0 else np.nan
    long_short = q5_ret - q1_ret if not (pd.isna(q1_ret) or pd.isna(q5_ret)) else np.nan

    # 检查单调性
    monotonic = True
    if len(avg_qret) >= 3:
        for i in range(1, len(avg_qret)):
            if avg_qret.iloc[i] < avg_qret.iloc[i - 1] - 0.001:  # 容忍小偏差
                monotonic = False
                break

    return {
        "q1_ret": q1_ret,
        "q5_ret": q5_ret,
        "long_short": long_short,
        "monotonic": monotonic,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 因子相关性分析
# ═══════════════════════════════════════════════════════════════════════════

def compute_factor_correlation(df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
    """计算因子间的截面相关性矩阵 (取时间平均)"""
    # 对每个日期计算相关矩阵，然后取平均
    daily_corrs = []
    for dt, g in df.groupby("trade_date"):
        if len(g) > 50:
            corr = g[factor_cols].corr()
            daily_corrs.append(corr)

    if not daily_corrs:
        return pd.DataFrame()

    avg_corr = pd.DataFrame(
        np.mean([c.values for c in daily_corrs], axis=0),
        index=factor_cols,
        columns=factor_cols,
    )
    return avg_corr


def find_redundant_factors(corr_matrix: pd.DataFrame, threshold: float = 0.8) -> list:
    """
    找出冗余因子 (相关性 > threshold)

    策略: 保留 IC 更高的因子，删除与其高度相关的其他因子
    """
    redundant = []
    processed = set()

    cols = corr_matrix.columns.tolist()

    for i, col1 in enumerate(cols):
        if col1 in processed:
            continue
        for col2 in cols[i + 1:]:
            if col2 in processed:
                continue
            corr = abs(corr_matrix.loc[col1, col2])
            if corr > threshold:
                # 标记 col2 为冗余 (假设 col1 排在前面是因为 IC 更高)
                redundant.append({
                    "redundant": col2,
                    "correlated_with": col1,
                    "correlation": corr,
                })
                processed.add(col2)

    return redundant


# ═══════════════════════════════════════════════════════════════════════════
# 因子衰减分析
# ═══════════════════════════════════════════════════════════════════════════

def compute_factor_decay(
    df: pd.DataFrame,
    factor_col: str,
    windows: list = [1, 3, 5, 10, 20],
) -> dict:
    """
    计算因子在不同预测窗口的 IC 衰减

    好的因子: 短期 IC 高，且衰减缓慢 (长期仍有预测力)
    差的因子: 短期 IC 高，但快速衰减到 0 (可能是噪声)
    """
    decay = {}
    for w in windows:
        fwd_col = f"fwd_ret_{w}d"
        if fwd_col not in df.columns:
            continue
        ic_series = compute_ic_series(df, factor_col, fwd_col)
        decay[f"ic_{w}d"] = ic_series.mean() if len(ic_series) > 0 else np.nan

    return decay


# ═══════════════════════════════════════════════════════════════════════════
# 主评估流程
# ═══════════════════════════════════════════════════════════════════════════

def prepare_data(
    parquet_path: Path,
    sample_stocks: int = 500,
    date_range: tuple = None,
) -> pd.DataFrame:
    """
    加载数据并计算未来收益

    为了效率，随机抽取部分股票进行评估
    """
    _log(f"加载数据: {parquet_path}")
    df = pd.read_parquet(parquet_path)

    # 日期过滤
    if date_range:
        df = df[(df["trade_date"] >= date_range[0]) & (df["trade_date"] <= date_range[1])]

    _log(f"  原始数据: {len(df):,} 行, {df['symbol'].nunique()} 只股票")

    # 随机抽样股票 (减少计算量)
    all_symbols = df["symbol"].unique()
    if len(all_symbols) > sample_stocks:
        np.random.seed(42)
        sampled = np.random.choice(all_symbols, sample_stocks, replace=False)
        df = df[df["symbol"].isin(sampled)]
        _log(f"  抽样后: {len(df):,} 行, {len(sampled)} 只股票")

    # 计算未来收益
    df = df.sort_values(["symbol", "trade_date"])

    for w in [1, 3, 5, 10, 20]:
        df[f"fwd_ret_{w}d"] = df.groupby("symbol")["close"].transform(
            lambda x: x.shift(-w) / x - 1
        )

    # 过滤无效数据
    df = df.dropna(subset=["fwd_ret_5d"])

    _log(f"  有效数据: {len(df):,} 行")
    return df


def get_factor_columns(df: pd.DataFrame) -> list:
    """获取所有因子列 (排除基础数据和目标变量)"""
    exclude_prefixes = [
        "symbol", "trade_date", "open", "high", "low", "close",
        "volume", "amount", "adj_factor", "stock_name", "industry",
        "listing_market", "fwd_ret",
    ]

    factor_cols = []
    for col in df.columns:
        if any(col.startswith(p) or col == p for p in exclude_prefixes):
            continue
        if df[col].dtype in ["float64", "float32", "int64"]:
            # 排除常量列
            if df[col].std() > 1e-8:
                factor_cols.append(col)

    return factor_cols


def evaluate_all_factors(
    df: pd.DataFrame,
    factor_cols: list,
    forward_col: str = "fwd_ret_5d",
    top_n: int = None,
    category_filter: str = None,
) -> pd.DataFrame:
    """评估所有因子，返回 IC 统计表"""
    _log(f"评估 {len(factor_cols)} 个因子...")

    results = []
    for i, col in enumerate(factor_cols):
        if (i + 1) % 20 == 0:
            _log(f"  进度: {i + 1}/{len(factor_cols)}")

        # 基本 IC 统计
        ic_series = compute_ic_series(df, col, forward_col)
        stats = compute_ic_stats(ic_series, col)

        # 分组收益
        qret = compute_quantile_returns(df, col, forward_col)
        stats.update(qret)

        # 因子类别
        stats["category"] = get_factor_category(col)

        # Null 率
        stats["null_rate"] = df[col].isna().mean()

        results.append(stats)

    result_df = pd.DataFrame(results)

    # 按 ICIR 排序 (综合考虑 IC 大小和稳定性)
    result_df = result_df.sort_values("icir", ascending=False, na_position="last")

    # 类别过滤
    if category_filter:
        result_df = result_df[result_df["category"] == category_filter]

    # Top N
    if top_n:
        result_df = result_df.head(top_n)

    return result_df


def generate_recommendations(
    ic_stats: pd.DataFrame,
    corr_matrix: pd.DataFrame = None,
    ic_threshold: float = 0.02,
    icir_threshold: float = 0.3,
    corr_threshold: float = 0.8,
) -> dict:
    """
    生成因子推荐列表

    筛选条件:
    1. |IC| > ic_threshold (至少 2% 的相关性)
    2. |ICIR| > icir_threshold (IC 稳定)
    3. 分组收益单调
    4. 去除冗余因子 (相关性 < corr_threshold)
    """
    # 基础筛选
    qualified = ic_stats[
        (ic_stats["ic_abs_mean"] > ic_threshold) &
        (ic_stats["icir"].abs() > icir_threshold) &
        (ic_stats["null_rate"] < 0.3)
    ].copy()

    _log(f"基础筛选: {len(qualified)} 个因子通过 IC/ICIR 门槛")

    # 单调性筛选
    monotonic = qualified[qualified["monotonic"] == True]
    _log(f"单调性筛选: {len(monotonic)} 个因子通过")

    # 去冗余
    if corr_matrix is not None and len(monotonic) > 0:
        # 只对通过的因子计算相关性
        common_cols = [c for c in monotonic["factor"] if c in corr_matrix.columns]
        sub_corr = corr_matrix.loc[common_cols, common_cols]
        redundant = find_redundant_factors(sub_corr, corr_threshold)
        redundant_names = {r["redundant"] for r in redundant}

        final = monotonic[~monotonic["factor"].isin(redundant_names)]
        _log(f"去冗余: {len(final)} 个因子 (移除 {len(redundant_names)} 个冗余)")
    else:
        final = monotonic
        redundant = []

    return {
        "recommended": final,
        "redundant": redundant,
        "stats": {
            "total_evaluated": len(ic_stats),
            "passed_ic": len(qualified),
            "passed_monotonic": len(monotonic),
            "final_count": len(final),
        },
    }


def print_report(ic_stats: pd.DataFrame, recommendations: dict):
    """打印评估报告"""
    print("\n" + "=" * 80)
    print("因子评估报告")
    print("=" * 80)

    # Top 20 因子
    print("\n📊 Top 20 因子 (按 ICIR 排序)")
    print("-" * 80)
    top20 = ic_stats.head(20)
    print(f"{'因子':<30} {'类别':<12} {'IC':>8} {'ICIR':>8} {'IC>0':>8} {'多空':>10} {'单调':>6}")
    print("-" * 80)
    for _, row in top20.iterrows():
        mono = "✓" if row.get("monotonic") else "✗"
        ls = f"{row.get('long_short', 0):.4f}" if not pd.isna(row.get("long_short")) else "N/A"
        print(
            f"{row['factor']:<30} "
            f"{row.get('category', ''):<12} "
            f"{row.get('ic_mean', 0):>8.4f} "
            f"{row.get('icir', 0):>8.3f} "
            f"{row.get('ic_positive_ratio', 0):>7.1%} "
            f"{ls:>10} "
            f"{mono:>6}"
        )

    # 推荐因子
    rec = recommendations["recommended"]
    print(f"\n✅ 推荐因子列表 ({len(rec)} 个)")
    print("-" * 80)
    for cat in rec["category"].unique():
        cat_factors = rec[rec["category"] == cat]["factor"].tolist()
        if cat_factors:
            print(f"  {cat}: {', '.join(cat_factors[:10])}")
            if len(cat_factors) > 10:
                print(f"         ... (+{len(cat_factors) - 10} more)")

    # 冗余因子
    redundant = recommendations["redundant"]
    if redundant:
        print(f"\n⚠️ 冗余因子 ({len(redundant)} 个)")
        print("-" * 80)
        for r in redundant[:10]:
            print(f"  {r['redundant']} ↔ {r['correlated_with']} (corr={r['correlation']:.2f})")
        if len(redundant) > 10:
            print(f"  ... (+{len(redundant) - 10} more)")

    # 统计
    stats = recommendations["stats"]
    print(f"\n📈 筛选统计")
    print("-" * 80)
    print(f"  总因子数:     {stats['total_evaluated']}")
    print(f"  IC 通过:      {stats['passed_ic']}")
    print(f"  单调通过:     {stats['passed_monotonic']}")
    print(f"  最终推荐:     {stats['final_count']}")
    print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="因子评估脚本")
    parser.add_argument("--top", type=int, default=50, help="显示 Top N 因子")
    parser.add_argument("--category", type=str, default=None, help="按类别筛选")
    parser.add_argument("--sample", type=int, default=500, help="抽样股票数量")
    parser.add_argument("--export", action="store_true", help="导出推荐因子列表")
    parser.add_argument("--corr", action="store_true", help="计算因子相关性 (较慢)")
    parser.add_argument("--ic-threshold", type=float, default=0.02, help="IC 门槛")
    parser.add_argument("--icir-threshold", type=float, default=0.3, help="ICIR 门槛")
    args = parser.parse_args()

    if not PARQUET_PATH.exists():
        _log(f"ERROR: parquet 文件不存在: {PARQUET_PATH}")
        sys.exit(1)

    # 准备数据
    df = prepare_data(PARQUET_PATH, sample_stocks=args.sample)

    # 获取因子列
    factor_cols = get_factor_columns(df)
    _log(f"发现 {len(factor_cols)} 个因子列")

    # 评估因子
    ic_stats = evaluate_all_factors(
        df, factor_cols,
        forward_col="fwd_ret_5d",
        top_n=args.top,
        category_filter=args.category,
    )

    # 计算相关性矩阵 (可选，较慢)
    corr_matrix = None
    if args.corr and len(ic_stats) > 0:
        _log("计算因子相关性矩阵...")
        top_factors = ic_stats.head(50)["factor"].tolist()
        corr_matrix = compute_factor_correlation(df, top_factors)

    # 生成推荐
    recommendations = generate_recommendations(
        ic_stats, corr_matrix,
        ic_threshold=args.ic_threshold,
        icir_threshold=args.icir_threshold,
    )

    # 打印报告
    print_report(ic_stats, recommendations)

    # 导出
    if args.export:
        output_path = OUTPUT_DIR / "recommended_factors.csv"
        recommendations["recommended"].to_csv(output_path, index=False)
        _log(f"推荐因子已导出: {output_path}")

        if corr_matrix is not None:
            corr_path = OUTPUT_DIR / "factor_correlation.csv"
            corr_matrix.to_csv(corr_path)
            _log(f"相关性矩阵已导出: {corr_path}")


if __name__ == "__main__":
    main()
