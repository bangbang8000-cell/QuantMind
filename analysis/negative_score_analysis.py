"""
XGBoost Alpha112 模型负分分析：排雷避坑 + 行业流出预警 + 持仓风控 + 市场情绪 + 做空信号

数据来源：
- 全市场推理分数: top20_tracking/*_inference.json (2026.01-06) + full_ranking_2026.parquet (2026.07-08)
- 价格数据: top20_tracking/price_lookup_full_v2.pkl (2025-12-25 ~ 2026-08-03)
- 行业映射: data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet (rs_hyname 申万128行业)

核心实证：每日最负Top20 → T+5均收 -3.06%，胜率仅28.1%（正分极值 +0.53%）
负分极值预测力强于正分极值，符合"利空比利多更有效"的不对称现象。
"""

import json
import glob
import pickle
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import psycopg2

# ── 路径配置 ──
PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
TOP20_DIR = ANALYSIS_DIR / "top20_tracking"
OUTPUT_DIR = ANALYSIS_DIR / "negative_score_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

QUANTDB_INSTRUMENT = PROJECT_ROOT / "data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet"

TOP_N = 20          # 每日最负/最正股票数
NEG_RISK_THRESHOLD = -0.06  # 排雷确定性阈值

# ── 股票代码前缀 → 市场板块 ──
def market_board(sym: str) -> str:
    """按代码前缀识别市场板块（对应正分v2的板块过滤）"""
    s = sym.split(".")[0]
    if s.startswith(("6", "9")):
        return "主板沪"
    if s.startswith(("0", "2")):
        return "主板深"
    if s.startswith("3"):
        return "创业板"
    if s.startswith(("4", "8")):
        return "北交所"
    if s.startswith(("68",)):
        return "科创板"
    return "其他"


def load_all_scores() -> dict[str, pd.DataFrame]:
    """加载全市场推理分数，返回 {date_str: DataFrame(symbol, score)}"""
    all_scores = {}
    for f in sorted(glob.glob(str(TOP20_DIR / "*_inference.json"))):
        with open(f) as fh:
            d = json.load(fh)
        for date, rows in d.items():
            if isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], list):
                all_scores[date] = pd.DataFrame(rows, columns=["symbol", "score"])

    df7 = pd.read_parquet(TOP20_DIR / "full_ranking_2026.parquet")
    df7["trade_date"] = df7["trade_date"].astype(str)
    for date, grp in df7.groupby("trade_date"):
        if date not in all_scores:
            all_scores[date] = grp[["symbol", "fusion_score"]].rename(columns={"fusion_score": "score"})

    return all_scores


def load_prices() -> tuple[dict, list[pd.Timestamp]]:
    """加载价格查找表 + 交易日序列"""
    with open(TOP20_DIR / "price_lookup_full_v2.pkl", "rb") as fh:
        price = pickle.load(fh)
    trading_days = sorted(set(ts for _, ts in price.keys()))
    return price, trading_days


def load_industry() -> pd.DataFrame:
    """加载行业映射，返回 DataFrame(sym_num, name, rs_hyname, board, is_st)"""
    df = pd.read_parquet(QUANTDB_INSTRUMENT)
    df["sym_num"] = df["Symbol"].str.split(".").str[0]
    result = pd.DataFrame({
        "sym_num": df["sym_num"],
        "name": df["Name"],
        "industry": df["rs_hyname"],
        "board": df["sym_num"].map(lambda s: market_board(s)),
        "is_st": df["IsSTGP"].astype(str) == "1",
    })
    return result


def get_close(price: dict, sym: str, ts: pd.Timestamp) -> float | None:
    r = price.get((sym, ts))
    return r["close"] if r else None


def future_returns(price: dict, trading_days: list, sym: str, signal_ts: pd.Timestamp, horizon: int = 5) -> float | None:
    """T+horizon 收益（从信号日收盘到第horizon个交易日收盘）"""
    futs = [d for d in trading_days if d > signal_ts]
    if len(futs) < horizon:
        return None
    c0 = get_close(price, sym, signal_ts)
    cH = get_close(price, sym, futs[horizon - 1])
    if c0 and cH and c0 > 0:
        return (cH - c0) / c0
    return None


# ══════════════════════════════════════════════════════════════════
# 模块1：排雷避坑 — 每日最负Top20清单 + 负分区间行为
# ══════════════════════════════════════════════════════════════════
def analyze_risk_zones(all_scores: dict, price, trading_days, industry):
    """负分区间行为分析（T+5收益）"""
    bins = [(-0.31, -0.15), (-0.15, -0.10), (-0.10, -0.08), (-0.08, -0.06),
            (-0.06, -0.04), (-0.04, -0.02), (-0.02, 0.0)]
    rows = []
    for date, day in all_scores.items():
        day = day.dropna(subset=["score"])
        if len(day) < 100:
            continue
        dts = pd.Timestamp(date)
        for lo, hi in bins:
            sub = day[(day["score"] >= lo) & (day["score"] < hi)]
            rets = []
            for _, r in sub.iterrows():
                ret = future_returns(price, trading_days, r["symbol"], dts)
                if ret is not None:
                    rets.append(ret)
            if rets:
                arr = np.array(rets)
                rows.append({
                    "区间下限": lo, "区间上限": hi,
                    "样本数": len(arr),
                    "T+5均收%": round(arr.mean() * 100, 3),
                    "T+5中位数%": round(np.median(arr) * 100, 3),
                    "胜率%": round((arr > 0).mean() * 100, 1),
                })
    zone_df = pd.DataFrame(rows).groupby(["区间下限", "区间上限"], as_index=False).agg({
        "样本数": "sum", "T+5均收%": "mean", "T+5中位数%": "mean", "胜率%": "mean",
    })
    zone_df.to_csv(OUTPUT_DIR / "negative_risk_zones.csv", index=False, encoding="utf-8-sig")

    # 每日最负Top20清单
    daily_risk_rows = []
    for date in sorted(all_scores.keys()):
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        top_neg = day.nsmallest(TOP_N, "score").copy()
        top_neg["date"] = date
        daily_risk_rows.append(top_neg)
    risk_all = pd.concat(daily_risk_rows, ignore_index=True)
    risk_all["board"] = risk_all["symbol"].map(market_board)
    ind_map = industry.set_index("sym_num")
    risk_all["industry"] = risk_all["symbol"].map(lambda s: ind_map.loc[s, "industry"] if s in ind_map.index else "未知")
    risk_all["name"] = risk_all["symbol"].map(lambda s: ind_map.loc[s, "name"] if s in ind_map.index else "")
    risk_all["is_st"] = risk_all["symbol"].map(lambda s: ind_map.loc[s, "is_st"] if s in ind_map.index else False)
    risk_all.to_csv(OUTPUT_DIR / "daily_negative_top20.csv", index=False, encoding="utf-8-sig")

    return zone_df, risk_all


# ══════════════════════════════════════════════════════════════════
# 模块2：行业流出预警 — 资金撤离地图
# ══════════════════════════════════════════════════════════════════
def analyze_industry_outflow(all_scores: dict, industry):
    """行业资金流出分析"""
    ind_map = industry.set_index("sym_num")
    rows = []
    daily_top20_counts = {}

    for date in sorted(all_scores.keys()):
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        day = day.copy()
        day["industry"] = day["symbol"].map(lambda s: ind_map.loc[s, "industry"] if s in ind_map.index else "未知")
        day["neg"] = day["score"] < 0

        # 行业流出指标
        ind_grp = day.groupby("industry").agg(
            股票数=("symbol", "count"),
            负分占比=("neg", lambda x: x.mean() * 100),
            平均分=("score", "mean"),
            负分均值=("score", lambda x: x[x < 0].mean() if (x < 0).any() else 0),
        )
        ind_grp["date"] = date
        rows.append(ind_grp.reset_index())

        # 行业在每日最负Top20的出镜次数
        top_neg = day.nsmallest(TOP_N, "score")
        for ind in top_neg["industry"].unique():
            daily_top20_counts[(date, ind)] = daily_top20_counts.get((date, ind), 0) + \
                int((top_neg["industry"] == ind).sum())

    ind_all = pd.concat(rows, ignore_index=True)
    # 只保留股票数足够的行业
    ind_all = ind_all[ind_all["股票数"] >= 5]

    # 汇总
    summary = ind_all.groupby("industry").agg(
        平均负分占比=("负分占比", "mean"),
        平均分=("平均分", "mean"),
        平均负分均值=("负分均值", "mean"),
        观测天数=("date", "nunique"),
    ).reset_index()
    summary["平均负分占比"] = summary["平均负分占比"].round(1)
    summary["平均分"] = summary["平均分"].round(4)
    summary["平均负分均值"] = summary["平均负分均值"].round(4)

    # 行业进入每日最负Top20的次数
    cnt = pd.Series(daily_top20_counts, name="次数").reset_index()
    cnt.columns = ["date", "industry", "次数"]
    top20_count = cnt.groupby("industry")["次数"].sum()
    summary["最负Top20出镜次数"] = summary["industry"].map(top20_count).fillna(0).astype(int)

    summary = summary.sort_values("平均负分均值", ascending=True)
    summary.to_csv(OUTPUT_DIR / "industry_outflow.csv", index=False, encoding="utf-8-sig")

    return summary


# ══════════════════════════════════════════════════════════════════
# 模块3：市场情绪指标 — 负分占比/均值时序
# ══════════════════════════════════════════════════════════════════
def analyze_sentiment(all_scores: dict):
    """市场情绪时序指标"""
    rows = []
    for date in sorted(all_scores.keys()):
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        neg = day[day["score"] < 0]
        top_neg = day.nsmallest(TOP_N, "score")
        rows.append({
            "date": date,
            "总样本": len(day),
            "负分占比%": round(len(neg) / len(day) * 100, 1),
            "全市场均分": round(day["score"].mean(), 4),
            "负分均值": round(neg["score"].mean(), 4) if len(neg) else None,
            "最负Top20均值": round(top_neg["score"].mean(), 4),
            "SELL信号数": len(neg),
        })
    sentiment = pd.DataFrame(rows)
    sentiment.to_csv(OUTPUT_DIR / "market_sentiment.csv", index=False, encoding="utf-8-sig")
    return sentiment


# ══════════════════════════════════════════════════════════════════
# 模块4：持仓风控验证 — 买入后跌入最负Top20的预警价值
# ══════════════════════════════════════════════════════════════════
def analyze_position_risk(all_scores: dict, price, trading_days):
    """动态验证：T日Top50买入 → 跟踪T+1~T+5是否跌入最负Top20
    对比：跌入后次日卖出 vs 一直持有到T+5的收益"""
    dates = sorted(all_scores.keys())
    # 预计算每日最负Top20集合 + 每日分数
    daily_neg20 = {}
    daily_scores = {}
    for date in dates:
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        daily_scores[date] = day.set_index("symbol")["score"]
        daily_neg20[date] = set(day.nsmallest(TOP_N, "score")["symbol"])

    rows = []
    for i, date in enumerate(dates):
        if date not in daily_scores:
            continue
        dts = pd.Timestamp(date)
        top50 = daily_scores[date].nlargest(50)
        futs = [d for d in dates if d > date]
        if len(futs) < 5:
            continue
        futs = futs[:5]  # T+1 ~ T+5

        for sym, score in top50.items():
            # 找到最早跌入最负Top20的日期
            hit_date = None
            for fd in futs:
                if sym in daily_neg20.get(fd, set()):
                    hit_date = fd
                    break

            c0 = get_close(price, sym, dts)
            c5 = get_close(price, sym, pd.Timestamp(futs[4])) if len(futs) >= 5 else None

            # 若跌入：T+2开盘卖出的收益（hit次日开盘）
            hit_sell_ret = None
            if hit_date is not None:
                hit_idx = futs.index(hit_date)
                if hit_idx + 1 < len(futs):
                    c_sell = get_close(price, sym, pd.Timestamp(futs[hit_idx + 1]))
                    if c0 and c_sell and c0 > 0:
                        hit_sell_ret = (c_sell - c0) / c0

            hold5_ret = None
            if c0 and c5 and c0 > 0:
                hold5_ret = (c5 - c0) / c0

            rows.append({
                "date": date, "symbol": sym, "score": round(score, 4),
                "跌入最负20天数": 5 - (len(futs) - (futs.index(hit_date) if hit_date else len(futs))),
                "hit_date": hit_date,
                "跌入后次日卖出收益%": round(hit_sell_ret * 100, 3) if hit_sell_ret is not None else None,
                "持有5日收益%": round(hold5_ret * 100, 3) if hold5_ret is not None else None,
            })

    pos = pd.DataFrame(rows)
    pos.to_csv(OUTPUT_DIR / "position_risk.csv", index=False, encoding="utf-8-sig")

    summary = {}
    if len(pos) > 0:
        hit = pos[pos["hit_date"].notna()]
        nohit = pos[pos["hit_date"].isna()]
        summary = {
            "Top50买入样本": int(len(pos)),
            "5日内跌入最负Top20的样本": int(len(hit)),
            "跌入率%": round(len(hit) / len(pos) * 100, 1),
            "跌入者·跌入后次日卖出均收%": round(hit["跌入后次日卖出收益%"].mean(), 3),
            "跌入者·持有5日均收%": round(hit["持有5日收益%"].mean(), 3),
            "未跌入者·持有5日均收%": round(nohit["持有5日收益%"].mean(), 3),
            "跌入者·持有5日胜率%": round((hit["持有5日收益%"] > 0).mean() * 100, 1),
            "未跌入者·持有5日胜率%": round((nohit["持有5日收益%"] > 0).mean() * 100, 1),
        }
    with open(OUTPUT_DIR / "position_risk_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


# ══════════════════════════════════════════════════════════════════
# 模块5：做空信号研究 — 最负Top20做空持有期扫描
# ══════════════════════════════════════════════════════════════════
def analyze_short_signal(all_scores: dict, price, trading_days):
    """最负Top20做空信号：不同持有期收益"""
    horizons = [1, 2, 3, 5, 10]
    rows = []
    for date, day in all_scores.items():
        day = day.dropna(subset=["score"])
        if len(day) < 100:
            continue
        dts = pd.Timestamp(date)
        top_neg = day.nsmallest(TOP_N, "score")
        for h in horizons:
            rets = []
            for _, r in top_neg.iterrows():
                ret = future_returns(price, trading_days, r["symbol"], dts, h)
                if ret is not None:
                    rets.append(ret)
            if rets:
                arr = np.array(rets)
                rows.append({
                    "持有期天数": h,
                    "样本数": len(arr),
                    "做空收益%(T+持有期)": round(-arr.mean() * 100, 3),
                    "下跌概率%": round((arr < 0).mean() * 100, 1),
                    "最大单笔做空收益%": round(-arr.min() * 100, 2),
                    "最差单笔做空收益%": round(-arr.max() * 100, 2),
                })
    short = pd.DataFrame(rows).groupby("持有期天数", as_index=False).agg({
        "样本数": "sum",
        "做空收益%(T+持有期)": "mean",
        "下跌概率%": "mean",
        "最大单笔做空收益%": "mean",
        "最差单笔做空收益%": "mean",
    })
    short.to_csv(OUTPUT_DIR / "short_signal.csv", index=False, encoding="utf-8-sig")
    return short


def main():
    print("=" * 60)
    print("XGBoost Alpha112 负分分析 (2026)")
    print("=" * 60)

    print("\n[1/5] 加载全市场推理分数...")
    all_scores = load_all_scores()
    dates = sorted(all_scores.keys())
    print(f"  共 {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")
    print(f"  每日约 {int(np.mean([len(v) for v in all_scores.values()]))} 只股票")

    print("[2/5] 加载价格数据...")
    price, trading_days = load_prices()
    print(f"  价格覆盖 {trading_days[0].date()} ~ {trading_days[-1].date()}")

    print("[3/5] 加载行业映射...")
    industry = load_industry()
    print(f"  申万行业 {industry['industry'].nunique()} 个, 覆盖 {len(industry)} 只股票")

    print("\n[4/5] 运行负分分析...")
    zone_df, risk_all = analyze_risk_zones(all_scores, price, trading_days, industry)
    print("  模块1 排雷避坑: 完成")
    ind_outflow = analyze_industry_outflow(all_scores, industry)
    print("  模块2 行业流出: 完成")
    sentiment = analyze_sentiment(all_scores)
    print("  模块3 市场情绪: 完成")
    pos_summary = analyze_position_risk(all_scores, price, trading_days)
    print("  模块4 持仓风控: 完成")
    short = analyze_short_signal(all_scores, price, trading_days)
    print("  模块5 做空信号: 完成")

    print("\n[5/5] 输出摘要")
    print("\n" + "=" * 60)
    print("★ 负分区间行为 (T+5收益)")
    print("=" * 60)
    for _, row in zone_df.iterrows():
        print(f"  [{row['区间下限']:+.2f},{row['区间上限']:+.2f}): "
              f"均收{row['T+5均收%']:+.2f}% 胜率{row['胜率%']:.1f}% n={int(row['样本数'])}")

    print("\n" + "=" * 60)
    print("★ 做空信号 (最负Top20 做空)")
    print("=" * 60)
    for _, row in short.iterrows():
        print(f"  持有{int(row['持有期天数']):>2}天: 做空收益{row['做空收益%(T+持有期)']:+.2f}% "
              f"下跌概率{row['下跌概率%']:.1f}% 最差{row['最差单笔做空收益%']:+.2f}%")

    print("\n" + "=" * 60)
    print("★ 持仓风控")
    print("=" * 60)
    if pos_summary:
        for k, v in pos_summary.items():
            print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("★ 行业流出 Top10")
    print("=" * 60)
    for _, row in ind_outflow.head(10).iterrows():
        print(f"  {row['industry']}: 负分占比{row['平均负分占比']}% "
              f"负分均值{row['平均负分均值']:+.4f} 最负Top20出镜{row['最负Top20出镜次数']}次")

    print(f"\n结果已保存到: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
