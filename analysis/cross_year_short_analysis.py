"""
2024-2026 跨年负分做空分析（向量化版本）：负分信号、板块拆分、负分反弹子集

核心目标（用户要求）：
1. 按做空思路广分析负分：最负Top20做空收益跨年一致性
2. 加板块维度：不同板块负分的做空价值差异
3. 找出"负分中也会涨"的子集：识别负分反弹规律

数据：
- 分数: cross_year_loader.load_all_scores() (612天, 每天5000+只)
- 价格: cross_year_loader.load_all_prices() (625天)
- 行业/板块: cross_year_loader.load_industry()

向量化：所有T+N收益通过日期偏移预计算，避免逐行index查找。
"""

from pathlib import Path

import numpy as np
import pandas as pd

from cross_year_loader import (
    load_all_scores, load_all_prices, load_industry,
    get_trading_days,
)

OUTPUT_DIR = Path("/home/zbox/projects/quantmind/analysis/negative_score_analysis/cross_year")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_N = 20
HORIZONS = [1, 2, 3, 5, 10]


def build_returns_frame(all_scores, price, trading_days):
    """构建统一长表：每只股票每日分数 + 价格 + T+N收益（全部用 merge 向量化）"""
    # 1. 合并所有分数
    frames = []
    for date, day in all_scores.items():
        d = day.copy()
        d["date"] = date
        frames.append(d)
    full = pd.concat(frames, ignore_index=True)
    full["date"] = full["date"].astype(str)
    full = full.dropna(subset=["score"])
    full["symbol"] = full["symbol"].astype(str)
    full["year"] = full["date"].str[:4]
    print(f"  分数长表: {len(full)} 行 ({full['date'].nunique()} 天)")

    # 2. 价格长表 close_df(date, symbol, close)
    close_records = []
    for date, syms in price.items():
        for sym, v in syms.items():
            if v.get("close") and v["close"] > 0:
                close_records.append((date, str(sym), v["close"]))
    close_df = pd.DataFrame(close_records, columns=["date", "symbol", "close"])
    close_df["date"] = close_df["date"].astype(str)
    print(f"  价格长表: {len(close_df)} 行 ({close_df['date'].nunique()} 天)")

    # 3. 交易日序号，预计算每个信号的 T+h 目标日
    day_list = sorted(close_df["date"].unique())
    date_rank = {d: i for i, d in enumerate(day_list)}
    rank_to_date = {i: d for i, d in enumerate(day_list)}
    for h in HORIZONS:
        # signal_date(rank i) -> target(rank i+h)
        sig_map = {rank_to_date[i]: rank_to_date[i + h] for i in range(len(day_list) - h)}
        full[f"target_{h}"] = full["date"].map(sig_map)

    # 4. 全部用 merge 关联价格
    full = full.merge(close_df, on=["date", "symbol"], how="left", suffixes=("", "_sig"))
    full = full.rename(columns={"close": "close_sig"})

    for h in HORIZONS:
        tgt = close_df.rename(columns={"date": f"target_{h}", "close": f"close_tgt_{h}"})
        full = full.merge(tgt, on=[f"target_{h}", "symbol"], how="left")
        full[f"ret{h}"] = np.where(
            (full["close_sig"] > 0) & full[f"close_tgt_{h}"].notna(),
            (full[f"close_tgt_{h}"] - full["close_sig"]) / full["close_sig"],
            np.nan,
        )

    full.to_parquet(OUTPUT_DIR / "score_long.parquet")
    return full, close_df


def analyze_short_signal(full):
    """最负Top20做空信号：跨年"""
    print("\n" + "=" * 66)
    print("一、最负Top20 做空信号：跨年一致性")
    print("=" * 66)

    # 取每日最负Top20
    neg20 = full.groupby("date").apply(
        lambda d: d.nsmallest(TOP_N, "score"), include_groups=False
    ).reset_index(level=0, drop=True)
    neg20 = neg20.reset_index()

    for h in HORIZONS:
        sub = neg20[neg20[f"ret{h}"].notna()]
        arr = sub[f"ret{h}"]
        print(f"  持有{h:>2}天: 做空收益{-arr.mean()*100:+.2f}%  下跌概率{(arr<0).mean()*100:.1f}%  "
              f"最差单笔{-arr.max()*100:+.2f}%  n={len(arr)}")

    print("\n  [分年度] 最负Top20做空 持有5/10天")
    for year in ["2024", "2025", "2026"]:
        sub = neg20[neg20["year"] == year]
        if sub.empty:
            continue
        parts = []
        for h in [5, 10]:
            arr = sub[f"ret{h}"].dropna()
            if len(arr):
                parts.append(f"H{h}做空{-arr.mean()*100:+.2f}%({(arr<0).mean()*100:.0f}%↓)")
        if parts:
            print(f"  {year}: n={len(sub)}  " + "  ".join(parts))

    neg20.to_csv(OUTPUT_DIR / "neg20_short_by_year.csv", index=False, encoding="utf-8-sig")
    return neg20


def analyze_short_by_board(full, industry):
    """板块维度：最负Top20做空收益"""
    print("\n" + "=" * 66)
    print("二、板块维度：最负Top20做空收益（持有5天）")
    print("=" * 66)
    ind_map = industry.set_index("sym_num")
    board_map = industry.set_index("sym_num")["board"]
    st_map = industry.set_index("sym_num")["is_st"]

    neg20 = full.groupby("date").apply(
        lambda d: d.nsmallest(TOP_N, "score"), include_groups=False
    ).reset_index(level=0, drop=True).reset_index()
    neg20["board"] = neg20["symbol"].map(board_map)
    neg20["is_st"] = neg20["symbol"].map(st_map)
    neg20 = neg20.dropna(subset=["board", "ret5"])

    print(f"\n{'板块':<8}{'样本':>8}{'做空收益%':>10}{'下跌概率%':>10}{'收益std%':>10}")
    for board, grp in neg20.groupby("board"):
        if len(grp) < 100:
            continue
        arr = grp["ret5"]
        print(f"{board:<8}{len(grp):>8}{-arr.mean()*100:>+10.2f}{(arr<0).mean()*100:>10.1f}{arr.std()*100:>10.2f}")

    print("\n[ST 过滤] 最负Top20 含ST的做空价值")
    for st_flag, grp in neg20.groupby("is_st"):
        tag = "ST" if st_flag else "非ST"
        arr = grp["ret5"]
        print(f"  {tag:<6}: n={len(grp):>6}  做空收益{-arr.mean()*100:+.2f}%  下跌概率{(arr<0).mean()*100:.1f}%")

    neg20.to_csv(OUTPUT_DIR / "neg20_by_board.csv", index=False, encoding="utf-8-sig")
    return neg20


def analyze_neg_risers(full, industry):
    """核心：找出负分中也会涨的子集"""
    print("\n" + "=" * 66)
    print("三、负分中也会涨的子集：负分反弹规律")
    print("=" * 66)
    ind_map = industry.set_index("sym_num")
    board_map = industry.set_index("sym_num")["board"]
    st_map = industry.set_index("sym_num")["is_st"]

    full = full.copy()
    full["board"] = full["symbol"].map(board_map)
    full["is_st"] = full["symbol"].map(st_map)
    full["industry"] = full["symbol"].map(
        lambda s: ind_map.loc[s, "industry"] if s in ind_map.index else "未知"
    )

    neg = full[full["score"] < 0].dropna(subset=["ret5"]).copy()
    print(f"  负分样本: {len(neg)} 条")
    print(f"  负分中T+5上涨比例: {(neg['ret5']>0).mean()*100:.1f}%")
    print(f"  负分整体T+5均收: {neg['ret5'].mean()*100:+.3f}%")

    # A. 负分程度分档
    print("\n[A] 负分程度 vs T+5")
    bins = [(-0.31, -0.15), (-0.15, -0.10), (-0.10, -0.08), (-0.08, -0.06),
            (-0.06, -0.04), (-0.04, -0.02), (-0.02, 0.0)]
    for lo, hi in bins:
        sub = neg[(neg["score"] >= lo) & (neg["score"] < hi)]
        if len(sub) < 100:
            continue
        print(f"  [{lo:+.2f},{hi:+.2f}): n={len(sub):>7}  T+5均收{sub['ret5'].mean()*100:+.3f}%  "
              f"上涨比例{(sub['ret5']>0).mean()*100:.1f}%")

    # B. 板块
    print("\n[B] 板块维度：负分股票 T+5")
    for board, grp in neg.groupby("board"):
        if len(grp) < 100:
            continue
        print(f"  {board:<8}: n={len(grp):>7}  T+5均收{grp['ret5'].mean()*100:+.3f}%  "
              f"上涨比例{(grp['ret5']>0).mean()*100:.1f}%")

    # C. 分年
    print("\n[C] 分年度：负分股票 T+5")
    for year, grp in neg.groupby("year"):
        print(f"  {year}: n={len(grp):>7}  T+5均收{grp['ret5'].mean()*100:+.3f}%  "
              f"上涨比例{(grp['ret5']>0).mean()*100:.1f}%")

    # D. 行业：负分反弹率
    print("\n[D] 行业维度：负分反弹率")
    ind_stats = neg.groupby("industry").agg(
        n=("ret5", "count"), 均收=("ret5", "mean"),
        上涨比例=("ret5", lambda x: (x > 0).mean() * 100),
    )
    ind_stats = ind_stats[ind_stats["n"] >= 500].copy()
    ind_stats["均收%"] = (ind_stats["均收"] * 100).round(3)
    ind_stats["上涨比例"] = ind_stats["上涨比例"].round(1)
    ind_stats = ind_stats.sort_values("上涨比例", ascending=False)
    print("  负分反弹率最高 Top8（负分也抗跌/会涨，做空需谨慎）:")
    for ind, row in ind_stats.head(8).iterrows():
        print(f"    {ind:<10}: n={int(row['n']):>6}  均收{row['均收%']:+.2f}%  上涨比例{row['上涨比例']:.1f}%")
    print("  负分下跌率最高 Top8（负分做空最有效）:")
    for ind, row in ind_stats.tail(8).iterrows():
        print(f"    {ind:<10}: n={int(row['n']):>6}  均收{row['均收%']:+.2f}%  上涨比例{row['上涨比例']:.1f}%")

    # E. 最负Top20中也会涨的
    print("\n[E] 最负Top20中也会涨的股票（做空被套场景）")
    neg20 = full.groupby("date").apply(
        lambda d: d.nsmallest(TOP_N, "score"), include_groups=False
    ).reset_index(level=0, drop=True).reset_index()
    neg20 = neg20.dropna(subset=["ret5"])
    risers = neg20[neg20["ret5"] > 0]
    print(f"  最负Top20样本: {len(neg20)}, 其中T+5上涨: {len(risers)} ({len(risers)/len(neg20)*100:.1f}%)")
    if len(risers) >= 100:
        print(f"  上涨者: 均收{risers['ret5'].mean()*100:+.2f}%, 板块 {risers['board'].value_counts().to_dict()}")
        print(f"  上涨者中ST占比: {risers['is_st'].mean()*100:.1f}%")
        print(f"  上涨者行业Top8: {dict(risers['industry'].value_counts().head(8))}")

    neg.to_csv(OUTPUT_DIR / "negative_returns_all.csv", index=False, encoding="utf-8-sig")
    neg20.to_csv(OUTPUT_DIR / "neg20_risers.csv", index=False, encoding="utf-8-sig")
    return neg, neg20


def main():
    print("=" * 66)
    print("2024-2026 跨年负分做空分析（向量化）")
    print("=" * 66)

    print("\n加载数据...")
    all_scores = load_all_scores()
    price = load_all_prices()
    trading_days = get_trading_days(price)
    industry = load_industry()
    print(f"  分数 {len(all_scores)} 天, 价格 {len(trading_days)} 天, 行业映射 {len(industry)} 只")

    print("\n构建收益长表...")
    full, close_pivot = build_returns_frame(all_scores, price, trading_days)

    neg20 = analyze_short_signal(full)
    neg20_board = analyze_short_by_board(full, industry)
    neg, neg20_risers = analyze_neg_risers(full, industry)

    print(f"\n所有结果保存到: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
