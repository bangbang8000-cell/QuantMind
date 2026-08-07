"""
负分模块增益回测：量化验证负分分析的 4 大应用价值

验证项：
1. 避雷增益：正分Top50组合 排除"近5天曾最负Top20" vs 不排除
2. 情绪过滤：负分占比>60%降仓 vs 不过滤（全市场等权T+5）
3. 持仓风控：Top50买入后跌入最负Top20 → 次日卖 vs 持有5天
4. 做空信号：最负Top20不同持有期做空收益

数据：2026.01-08 全市场推理分数 + price_lookup_full_v2.pkl 价格
"""

import json
import glob
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
TOP20_DIR = PROJECT_ROOT / "analysis/top20_tracking"
OUTPUT_DIR = PROJECT_ROOT / "analysis/negative_score_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_N = 20


def load_all_scores() -> dict:
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


def load_prices():
    with open(TOP20_DIR / "price_lookup_full_v2.pkl", "rb") as fh:
        price = pickle.load(fh)
    trading_days = sorted(set(ts for _, ts in price.keys()))
    return price, trading_days


def get_close(price, sym, ts):
    r = price.get((sym, ts))
    return r["close"] if r else None


def t_plus_return(price, trading_days, sym, signal_ts, horizon):
    futs = [d for d in trading_days if d > signal_ts]
    if len(futs) < horizon:
        return None
    c0 = get_close(price, sym, signal_ts)
    cH = get_close(price, sym, futs[horizon - 1])
    if c0 and cH and c0 > 0:
        return (cH - c0) / c0
    return None


def backtest_avoidance(all_scores, price, trading_days):
    """避雷增益：正分Top50排除近5天曾最负Top20"""
    dates = sorted(all_scores.keys())
    neg20 = {d: set(all_scores[d].nsmallest(TOP_N, "score")["symbol"])
             for d in dates if len(all_scores[d]) > 100}
    pos50 = {d: set(all_scores[d].nlargest(50, "score")["symbol"])
             for d in dates if len(all_scores[d]) > 100}

    rows = []
    for i, date in enumerate(dates):
        if date not in pos50:
            continue
        dts = pd.Timestamp(date)
        lookback = dates[max(0, i - 5):i]
        recent_neg = set()
        for lb in lookback:
            recent_neg |= neg20.get(lb, set())

        for sym in pos50[date]:
            ret5 = t_plus_return(price, trading_days, sym, dts, 5)
            if ret5 is None:
                continue
            rows.append({"date": date, "was_recent_neg": sym in recent_neg, "ret5": ret5})

    rdf = pd.DataFrame(rows)
    rdf["avoided"] = ~rdf["was_recent_neg"]  # 排除后保留的

    result = {}
    if len(rdf) > 0:
        all_ret = rdf["ret5"]
        clean = rdf[rdf["avoided"]]["ret5"]
        result = {
            "样本数": len(rdf),
            "曾最负占比%": round(rdf["was_recent_neg"].mean() * 100, 2),
            "不排除·全组合T+5均收%": round(all_ret.mean() * 100, 3),
            "不排除·胜率%": round((all_ret > 0).mean() * 100, 1),
            "排除后·T+5均收%": round(clean.mean() * 100, 3),
            "排除后·胜率%": round((clean > 0).mean() * 100, 1),
        }
    return result


def backtest_sentiment_filter(all_scores, price, trading_days):
    """情绪过滤：负分占比>60%降仓/空仓 vs 不过滤"""
    dates = sorted(all_scores.keys())
    rows = []
    for date in dates:
        dts = pd.Timestamp(date)
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        neg_ratio = (day["score"] < 0).mean() * 100
        rets = []
        for _, r in day.iterrows():
            ret5 = t_plus_return(price, trading_days, r["symbol"], dts, 5)
            if ret5 is not None:
                rets.append(ret5)
        if rets:
            rows.append({"date": date, "neg_ratio": neg_ratio, "mkt_t5": np.mean(rets)})

    rdf = pd.DataFrame(rows)
    result = {}
    if len(rdf) > 0:
        result = {
            "总天数": len(rdf),
            "负分占比>60%天数": int((rdf["neg_ratio"] > 60).sum()),
            "不过滤·全期T+5均收%": round(rdf["mkt_t5"].mean() * 100, 3),
            "过滤后·仅负分占比≤60%买入期T+5均收%": round(
                rdf[rdf["neg_ratio"] <= 60]["mkt_t5"].mean() * 100, 3),
            "空仓期·负分占比>60%市场T+5均收%(避开的部分)": round(
                rdf[rdf["neg_ratio"] > 60]["mkt_t5"].mean() * 100, 3),
            "相关性(负分占比 vs 市场T+5)": round(rdf["neg_ratio"].corr(rdf["mkt_t5"]), 3),
        }
    return result


def backtest_position_risk(all_scores, price, trading_days):
    """持仓风控：Top50买入后跌入最负Top20 → 次日卖 vs 持有5天"""
    dates = sorted(all_scores.keys())
    daily_scores = {}
    daily_neg20 = {}
    for date in dates:
        day = all_scores[date].dropna(subset=["score"])
        if len(day) < 100:
            continue
        daily_scores[date] = day.set_index("symbol")["score"]
        daily_neg20[date] = set(day.nsmallest(TOP_N, "score")["symbol"])

    rows = []
    for date in dates:
        if date not in daily_scores:
            continue
        dts = pd.Timestamp(date)
        top50 = daily_scores[date].nlargest(50)
        futs = [d for d in dates if d > date]
        if len(futs) < 5:
            continue
        futs = futs[:5]
        for sym in top50.index:
            hit_date = None
            for fd in futs:
                if sym in daily_neg20.get(fd, set()):
                    hit_date = fd
                    break
            c0 = get_close(price, sym, dts)
            c5 = get_close(price, sym, pd.Timestamp(futs[4]))
            hit_sell_ret = None
            if hit_date is not None:
                hit_idx = futs.index(hit_date)
                if hit_idx + 1 < len(futs):
                    c_sell = get_close(price, sym, pd.Timestamp(futs[hit_idx + 1]))
                    if c0 and c_sell and c0 > 0:
                        hit_sell_ret = (c_sell - c0) / c0
            hold5 = (c5 - c0) / c0 if c0 and c5 and c0 > 0 else None
            if hold5 is not None:
                rows.append({
                    "hit": hit_date is not None,
                    "sell_on_hit_ret": hit_sell_ret,
                    "hold5_ret": hold5,
                })

    rdf = pd.DataFrame(rows)
    result = {}
    if len(rdf) > 0:
        hit = rdf[rdf["hit"]]
        nohit = rdf[~rdf["hit"]]
        result = {
            "Top50买入样本": len(rdf),
            "5日内跌入最负Top20": int(len(hit)),
            "跌入率%": round(len(hit) / len(rdf) * 100, 2),
            "跌入者·次日卖均收%": round(hit["sell_on_hit_ret"].mean() * 100, 3),
            "跌入者·持有5日均收%": round(hit["hold5_ret"].mean() * 100, 3),
            "未跌入者·持有5日均收%": round(nohit["hold5_ret"].mean() * 100, 3),
        }
    return result


def backtest_short(all_scores, price, trading_days):
    """做空信号：最负Top20不同持有期做空"""
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
                ret = t_plus_return(price, trading_days, r["symbol"], dts, h)
                if ret is not None:
                    rets.append(ret)
            if rets:
                arr = np.array(rets)
                rows.append({
                    "h": h, "n": len(arr), "short_ret": -arr.mean(),
                    "down_prob": (arr < 0).mean(), "worst": -arr.max(),
                })
    short = pd.DataFrame(rows).groupby("h", as_index=False).agg(
        n=("n", "sum"), short_ret=("short_ret", "mean"),
        down_prob=("down_prob", "mean"), worst=("worst", "mean"),
    )
    return short


def main():
    print("=" * 62)
    print("负分模块增益回测 (2026.01-08)")
    print("=" * 62)

    print("\n加载数据...")
    all_scores = load_all_scores()
    price, trading_days = load_prices()

    print("\n[1/4] 避雷增益回测...")
    r1 = backtest_avoidance(all_scores, price, trading_days)
    print(f"  曾最负占比 {r1.get('曾最负占比%')}%, "
          f"排除前均收 {r1.get('不排除·全组合T+5均收%')}% → "
          f"排除后均收 {r1.get('排除后·T+5均收%')}%")

    print("[2/4] 情绪过滤回测...")
    r2 = backtest_sentiment_filter(all_scores, price, trading_days)
    print(f"  负分占比>60%共{r2.get('负分占比>60%天数')}天, "
          f"过滤后均收 {r2.get('过滤后·仅负分占比≤60%买入期T+5均收%')}% vs "
          f"不过滤 {r2.get('不过滤·全期T+5均收%')}%")

    print("[3/4] 持仓风控回测...")
    r3 = backtest_position_risk(all_scores, price, trading_days)
    print(f"  跌入率 {r3.get('跌入率%')}%, 跌入者持有5日均收 {r3.get('跌入者·持有5日均收%')}%")

    print("[4/4] 做空信号回测...")
    r4 = backtest_short(all_scores, price, trading_days)
    print("  最负Top20做空:")
    for _, row in r4.iterrows():
        print(f"    持有{int(row['h'])}天: 收益{row['short_ret']*100:+.2f}% "
              f"下跌概率{row['down_prob']*100:.1f}%")

    # 保存
    summary = {
        "避雷增益": r1,
        "情绪过滤": r2,
        "持仓风控": r3,
        "做空信号": r4.to_dict(orient="records"),
    }
    with open(OUTPUT_DIR / "backtest_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    r4.to_csv(OUTPUT_DIR / "short_signal_backtest.csv", index=False, encoding="utf-8-sig")
    print(f"\n结果保存到 {OUTPUT_DIR}/backtest_summary.json")


if __name__ == "__main__":
    main()
