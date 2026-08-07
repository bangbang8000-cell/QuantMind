"""
XGBoost Alpha112 模型推理分析：每日 Top20 股票跟踪 + 买卖持有信号

数据来源：
- 推理信号: PostgreSQL engine_signal_scores 表 (2026年7月-8月)
- 价格数据: QuantDB daily_unadjusted parquet (2026年7月-8月)

分析逻辑：
1. 从 DB 读取推理信号，取每日 Top20 股票
2. 从 QuantDB 获取 7/21-8/4 实际价格
3. 跟踪每只股票从信号日到 8/4 的价格变化
4. 生成买入/卖出/持有信号
"""

import pandas as pd
import numpy as np
import psycopg2
import json
from pathlib import Path
from datetime import datetime, timedelta

# ── 路径配置 ──
PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
QUANTDB_DAILY = PROJECT_ROOT / "data/quantdb/1_kline_data/daily_unadjusted"
OUTPUT_DIR = PROJECT_ROOT / "analysis/top20_tracking"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 日期范围 (2026年) ──
SIGNAL_START = "2026-07-21"  # 第一个信号日
SIGNAL_END = "2026-08-04"    # 最后一个信号日
TRACK_END = "2026-08-04"     # 价格跟踪截止
TOP_N = 20
MODEL_ID = "mdl_train_20260804025559_058f404d_49f72631"


def load_signals_from_db():
    """从 PostgreSQL 加载推理信号"""
    print("从数据库加载推理信号...")
    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="quantmind", user="quantmind", password="quantmind2026",
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT s.trade_date, s.symbol, s.fusion_score, s.signal_side,
               r.data_trade_date
        FROM engine_signal_scores s
        JOIN qm_model_inference_runs r ON s.run_id = r.run_id
        WHERE r.model_id = %s
        AND s.signal_side = 'BUY'
        ORDER BY s.trade_date, s.fusion_score DESC
    """, (MODEL_ID,))

    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["trade_date", "symbol", "fusion_score", "signal_side", "data_date"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["data_date"] = pd.to_datetime(df["data_date"])
    print(f"  加载 {len(df)} 条 BUY 信号, 日期: {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
    return df


def load_price_data(start_date, end_date):
    """从 QuantDB daily_unadjusted 加载价格数据"""
    print("加载价格数据...")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    dates_needed = []
    current = start
    while current <= end:
        dt_str = current.strftime("%Y%m%d")
        partition = QUANTDB_DAILY / f"dt={dt_str}"
        if partition.exists():
            dates_needed.append(dt_str)
        current += timedelta(days=1)

    all_dfs = []
    for dt_str in dates_needed:
        partition = QUANTDB_DAILY / f"dt={dt_str}"
        try:
            df = pd.read_parquet(partition, columns=["symbol", "time", "open", "high", "low", "close", "volume", "amount"])
            all_dfs.append(df)
        except Exception as e:
            print(f"  跳过 {dt_str}: {e}")

    if not all_dfs:
        raise RuntimeError("没有加载到任何价格数据")

    price_df = pd.concat(all_dfs, ignore_index=True)
    price_df["time"] = pd.to_datetime(price_df["time"])
    price_df["symbol_num"] = price_df["symbol"].str.replace(r"\.(SH|SZ|BJ)$", "", regex=True)

    print(f"  加载 {len(dates_needed)} 天价格数据, 共 {len(price_df)} 行")
    return price_df


def get_daily_top20(signals_df):
    """获取每日 Top20 股票"""
    result = {}
    for date in sorted(signals_df["trade_date"].unique()):
        day_df = signals_df[signals_df["trade_date"] == date]
        top20 = day_df.nlargest(TOP_N, "fusion_score")[["symbol", "fusion_score", "data_date"]].copy()
        top20["rank"] = range(1, len(top20) + 1)
        result[date] = top20.reset_index(drop=True)
    return result


def get_price_for_symbol(price_df, symbol_num, date):
    """获取某只股票某天的价格"""
    mask = (price_df["symbol_num"] == symbol_num) & (price_df["time"] == pd.Timestamp(date))
    rows = price_df[mask]
    if len(rows) > 0:
        row = rows.iloc[0]
        return {
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]),
        }
    return None


def get_symbol_with_suffix(price_df, symbol_num):
    """获取带后缀的 symbol"""
    rows = price_df[price_df["symbol_num"] == symbol_num]
    if len(rows) > 0:
        return rows.iloc[0]["symbol"]
    # Auto-detect market
    if symbol_num.startswith(("6", "9")):
        return f"{symbol_num}.SH"
    elif symbol_num.startswith(("0", "3", "2")):
        return f"{symbol_num}.SZ"
    elif symbol_num.startswith(("4", "8")):
        return f"{symbol_num}.BJ"
    return symbol_num


def generate_signal(buy_close, current_close, hold_days, max_hold=10, stop_loss=-0.08, take_profit=0.15):
    """生成买卖信号"""
    if buy_close is None or current_close is None or buy_close == 0:
        return "无数据"

    ret = (current_close - buy_close) / buy_close

    if hold_days >= max_hold:
        if ret > 0.02:
            return "卖出(到期盈利)"
        elif ret < -0.02:
            return "卖出(到期亏损)"
        else:
            return "卖出(到期平)"

    if ret <= stop_loss:
        return "卖出(止损)"
    if ret >= take_profit:
        return "卖出(止盈)"

    if ret > 0.03:
        return "持有(盈利中)"
    elif ret > 0:
        return "持有(微盈)"
    elif ret > -0.03:
        return "持有(微亏)"
    else:
        return "持有(亏损中)"


def analyze_top20_tracking(signals_df, price_df):
    """主分析：每日Top20跟踪 + 买卖信号"""
    daily_top20 = get_daily_top20(signals_df)
    trading_days = sorted(price_df["time"].unique())

    all_results = []

    for date, top20_df in sorted(daily_top20.items()):
        date_str = date.strftime("%Y-%m-%d")

        # 信号日 = data_date (T日), 交易日在 trade_date (T+1日)
        # 买入价 = T+1日开盘价
        future_dates = [d for d in trading_days if d >= pd.Timestamp(date)]
        future_dates = [d for d in future_dates if d <= pd.Timestamp(TRACK_END)]

        for _, row in top20_df.iterrows():
            symbol = row["symbol"]
            pred_score = float(row["fusion_score"])
            rank = int(row["rank"])
            data_date = row["data_date"]

            # 买入价 = 信号日(即trade_date)的开盘价
            buy_price_info = get_price_for_symbol(price_df, symbol, date)
            buy_open = buy_price_info["open"] if buy_price_info else None
            buy_close = buy_price_info["close"] if buy_price_info else None
            symbol_full = get_symbol_with_suffix(price_df, symbol)

            track_data = {
                "signal_date": date_str,
                "data_date": data_date.strftime("%Y-%m-%d") if hasattr(data_date, 'strftime') else str(data_date),
                "symbol": symbol,
                "symbol_full": symbol_full,
                "rank": rank,
                "pred_score": round(pred_score, 6),
                "buy_open": buy_open,
                "buy_close": buy_close,
            }

            # 次日排名 (从信号数据中查找)
            next_dates = [d for d in sorted(signals_df["trade_date"].unique()) if d > date]
            if next_dates:
                next_day = next_dates[0]
                next_day_signals = signals_df[signals_df["trade_date"] == next_day]
                next_rank_df = next_day_signals.nlargest(TOP_N, "fusion_score")
                next_rank_rows = next_rank_df[next_rank_df["symbol"] == symbol]
                if len(next_rank_rows) > 0:
                    track_data["next_day_rank"] = int(next_rank_df.reset_index(drop=True).index[
                        next_rank_df.reset_index(drop=True)["symbol"] == symbol
                    ][0]) + 1
                else:
                    # Not in top20 next day
                    total_next = len(next_day_signals)
                    track_data["next_day_rank"] = f">{total_next}"

            # 次日价格
            next_trading_day = [d for d in trading_days if d > pd.Timestamp(date)]
            if next_trading_day:
                nd = next_trading_day[0]
                next_price = get_price_for_symbol(price_df, symbol, nd)
                if next_price:
                    track_data["next_day_open"] = next_price["open"]
                    track_data["next_day_close"] = next_price["close"]
                    if buy_close and buy_close > 0:
                        track_data["next_day_ret"] = round((next_price["close"] - buy_close) / buy_close, 4)
                else:
                    track_data["next_day_open"] = None
                    track_data["next_day_close"] = None
                    track_data["next_day_ret"] = None

            # 跟踪到8/4的价格变化
            price_changes = {}
            for fd in future_dates:
                fd_str = fd.strftime("%Y-%m-%d")
                fd_price = get_price_for_symbol(price_df, symbol, fd)
                if fd_price and buy_close and buy_close > 0:
                    price_changes[fd_str] = {
                        "close": fd_price["close"],
                        "ret_from_buy": round((fd_price["close"] - buy_close) / buy_close, 4),
                    }

            track_data["price_tracking"] = price_changes

            # 计算持有天数和最终信号
            track_dates = [d for d in future_dates if d > pd.Timestamp(date)]
            if track_dates and buy_close:
                last_track_date = track_dates[-1]
                hold_days = len(track_dates)
                last_price = get_price_for_symbol(price_df, symbol, last_track_date)
                last_close = last_price["close"] if last_price else None
                track_data["last_track_close"] = last_close
                track_data["hold_days"] = hold_days
                track_data["total_ret"] = round((last_close - buy_close) / buy_close, 4) if last_close and buy_close else None
                track_data["signal"] = generate_signal(buy_close, last_close, hold_days)
            else:
                track_data["last_track_close"] = None
                track_data["hold_days"] = 0
                track_data["total_ret"] = None
                track_data["signal"] = "无数据"

            all_results.append(track_data)

    return all_results, daily_top20


def build_daily_summary(all_results, daily_top20):
    """构建每日汇总表"""
    summaries = {}
    for date, top20_df in sorted(daily_top20.items()):
        date_str = date.strftime("%Y-%m-%d")
        day_results = [r for r in all_results if r["signal_date"] == date_str]

        summary_rows = []
        for r in day_results:
            row = {
                "排名": r["rank"],
                "股票代码": r["symbol_full"],
                "预测分数": r["pred_score"],
                "次日排名": r.get("next_day_rank"),
                "信号日收盘": r["buy_close"],
                "次日开盘": r.get("next_day_open"),
                "次日收盘": r.get("next_day_close"),
                "次日收益%": round(r.get("next_day_ret", 0) * 100, 2) if r.get("next_day_ret") is not None else None,
                "最终收益%": round(r["total_ret"] * 100, 2) if r.get("total_ret") is not None else None,
                "持有天数": r.get("hold_days", 0),
                "信号": r.get("signal", ""),
            }
            summary_rows.append(row)

        summaries[date_str] = pd.DataFrame(summary_rows)

    return summaries


def build_stock_aggregate(all_results):
    """构建股票聚合分析"""
    stock_stats = {}
    for r in all_results:
        sym = r["symbol_full"]
        if sym not in stock_stats:
            stock_stats[sym] = {
                "appearances": 0, "dates": [], "pred_scores": [],
                "next_day_rets": [], "total_rets": [], "signals": [],
            }
        stock_stats[sym]["appearances"] += 1
        stock_stats[sym]["dates"].append(r["signal_date"])
        stock_stats[sym]["pred_scores"].append(r["pred_score"])
        if r.get("next_day_ret") is not None:
            stock_stats[sym]["next_day_rets"].append(r["next_day_ret"])
        if r.get("total_ret") is not None:
            stock_stats[sym]["total_rets"].append(r["total_ret"])
        stock_stats[sym]["signals"].append(r.get("signal", ""))

    rows = []
    for sym, stats in sorted(stock_stats.items(), key=lambda x: -x[1]["appearances"]):
        rows.append({
            "股票代码": sym,
            "上榜次数": stats["appearances"],
            "上榜日期": ", ".join(stats["dates"]),
            "平均预测分": round(np.mean(stats["pred_scores"]), 6),
            "次日平均收益%": round(np.mean(stats["next_day_rets"]) * 100, 2) if stats["next_day_rets"] else None,
            "次日胜率%": round(sum(1 for r in stats["next_day_rets"] if r > 0) / len(stats["next_day_rets"]) * 100, 1) if stats["next_day_rets"] else None,
            "平均最终收益%": round(np.mean(stats["total_rets"]) * 100, 2) if stats["total_rets"] else None,
            "最终胜率%": round(sum(1 for r in stats["total_rets"] if r > 0) / len(stats["total_rets"]) * 100, 1) if stats["total_rets"] else None,
            "信号汇总": ", ".join(stats["signals"]),
        })

    return pd.DataFrame(rows)


def build_overall_stats(all_results):
    """整体统计"""
    total_picks = len(all_results)
    next_day_rets = [r["next_day_ret"] for r in all_results if r.get("next_day_ret") is not None]
    total_rets = [r["total_ret"] for r in all_results if r.get("total_ret") is not None]

    stats = {
        "分析日期范围": f"{SIGNAL_START} ~ {SIGNAL_END}",
        "价格跟踪截止": TRACK_END,
        "每日选股数": TOP_N,
        "总选股次数": total_picks,
        "唯一股票数": len(set(r["symbol"] for r in all_results)),
        "次日平均收益%": round(np.mean(next_day_rets) * 100, 2) if next_day_rets else None,
        "次日中位数收益%": round(np.median(next_day_rets) * 100, 2) if next_day_rets else None,
        "次日胜率%": round(sum(1 for r in next_day_rets if r > 0) / len(next_day_rets) * 100, 1) if next_day_rets else None,
        "跟踪期平均收益%": round(np.mean(total_rets) * 100, 2) if total_rets else None,
        "跟踪期胜率%": round(sum(1 for r in total_rets if r > 0) / len(total_rets) * 100, 1) if total_rets else None,
    }
    return stats


def main():
    print("=" * 60)
    print("XGBoost Alpha112 模型 Top20 股票跟踪分析 (2026)")
    print("=" * 60)

    # 1. 加载数据
    signals_df = load_signals_from_db()
    price_df = load_price_data(start_date=SIGNAL_START, end_date=TRACK_END)

    # 2. 分析
    print("\n分析每日 Top20 股票...")
    all_results, daily_top20 = analyze_top20_tracking(signals_df, price_df)

    # 3. 构建汇总
    print("构建汇总表...")
    daily_summaries = build_daily_summary(all_results, daily_top20)
    stock_aggregate = build_stock_aggregate(all_results)
    overall_stats = build_overall_stats(all_results)

    # 4. 输出
    print(f"\n保存结果到 {OUTPUT_DIR}...")

    for date_str, summary_df in daily_summaries.items():
        summary_df.to_csv(OUTPUT_DIR / f"top20_{date_str}.csv", index=False, encoding="utf-8-sig")

    all_daily = pd.concat(daily_summaries.values(), ignore_index=True)
    all_daily.to_csv(OUTPUT_DIR / "top20_all_daily.csv", index=False, encoding="utf-8-sig")

    stock_aggregate.to_csv(OUTPUT_DIR / "stock_aggregate.csv", index=False, encoding="utf-8-sig")

    with open(OUTPUT_DIR / "overall_stats.json", "w", encoding="utf-8") as f:
        json.dump(overall_stats, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "full_tracking.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    # 5. 打印摘要
    print("\n" + "=" * 60)
    print("整体统计")
    print("=" * 60)
    for k, v in overall_stats.items():
        print(f"  {k}: {v}")

    print(f"\n上榜3次以上的股票:")
    freq_stocks = stock_aggregate[stock_aggregate["上榜次数"] >= 3]
    if len(freq_stocks) > 0:
        for _, row in freq_stocks.iterrows():
            print(f"  {row['股票代码']}: 上榜{row['上榜次数']}次, "
                  f"次日均收{row['次日平均收益%']}%, "
                  f"最终均收{row['平均最终收益%']}%, "
                  f"次日胜率{row['次日胜率%']}%")

    print(f"\n结果已保存到: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
