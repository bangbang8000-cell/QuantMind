"""
2025年 XGBoost Alpha112 全年回测 + 板块轮动分析
=================================================
策略：每日取 Top1 股票，T+1 开盘买入，持有3天卖出（T+3收盘）
      涨停/跌停过滤，ST排除
板块：沪主板(600/601/603/605), 深主板(000/001/003), 中小板(002),
      创业板(300/301), 科创板(688/689)
"""

import pandas as pd
import numpy as np
import json
import pickle
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
QUANTDB_DAILY = PROJECT_ROOT / "data/quantdb/1_kline_data/daily_unadjusted"
INFERENCE_DIR = PROJECT_ROOT / "analysis/2025_backtest"
OUTPUT_DIR = PROJECT_ROOT / "analysis/2025_backtest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INITIAL_CAPITAL = 100000
HOLD_DAYS = 3
TOP_N = 1  # 每日只买Top1


def classify_sector(sym_num):
    """根据股票代码数字部分分类板块"""
    prefix = sym_num[:3] if len(sym_num) >= 3 else sym_num[:2]
    if prefix in ("688", "689"):
        return "科创板"
    elif prefix in ("300", "301"):
        return "创业板"
    elif prefix == "002":
        return "中小板"
    elif prefix in ("000", "001", "003"):
        return "深主板"
    elif prefix in ("600", "601", "603", "605"):
        return "沪主板"
    elif prefix.startswith("4") or prefix.startswith("8"):
        return "北交所"
    else:
        return "其他"


def load_all_inference():
    """加载2025年全部12个月推理数据"""
    all_data = {}
    for m in range(1, 13):
        fname = INFERENCE_DIR / f"2025_{m:02d}_inference.json"
        with open(fname) as f:
            data = json.load(f)
        for date, stocks in data.items():
            all_data[date] = stocks
    return all_data


def load_price_lookup():
    """加载2025年全年价格数据，构建查找表"""
    print("加载2025年价格数据...")
    all_dfs = []
    for dt_dir in sorted(QUANTDB_DAILY.iterdir()):
        if not dt_dir.name.startswith("dt=2025"):
            continue
        try:
            df = pd.read_parquet(
                dt_dir,
                columns=["symbol", "time", "open", "high", "low", "close", "volume", "amount"],
            )
            all_dfs.append(df)
        except Exception as e:
            print(f"  跳过 {dt_dir.name}: {e}")

    if not all_dfs:
        raise RuntimeError("没有加载到2025年价格数据")

    price_df = pd.concat(all_dfs, ignore_index=True)
    price_df["time"] = pd.to_datetime(price_df["time"])
    price_df["symbol_num"] = price_df["symbol"].str.replace(r"\.(SH|SZ|BJ)$", "", regex=True)

    # 构建查找字典: (symbol_num, date) -> {open, high, low, close, volume, amount}
    lookup = {}
    for _, row in price_df.iterrows():
        key = (row["symbol_num"], row["time"])
        if key not in lookup:
            lookup[key] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
            }

    # 交易日列表
    trading_days = sorted(price_df["time"].unique())

    print(f"  加载 {len(trading_days)} 天, {len(lookup)} 条价格记录")
    return lookup, trading_days


def get_price(lookup, sym_num, date):
    """获取价格"""
    if isinstance(date, str):
        date = pd.Timestamp(date)
    return lookup.get((sym_num, date))


def get_trading_day_offset(trading_days, date, offset=1):
    """获取偏移交易日"""
    if isinstance(date, str):
        date = pd.Timestamp(date)
    idx = None
    for i, td in enumerate(trading_days):
        if td == date:
            idx = i
            break
    if idx is None:
        return None
    target_idx = idx + offset
    if 0 <= target_idx < len(trading_days):
        return trading_days[target_idx]
    return None


def load_st_stocks():
    """从parquet加载ST股票集合"""
    print("加载ST股票列表...")
    st_set = set()
    for dt_dir in sorted(QUANTDB_DAILY.iterdir()):
        if not dt_dir.name.startswith("dt=2025"):
            continue
        try:
            df = pd.read_parquet(dt_dir, columns=["symbol"])
            # ST股票在推理时已过滤，这里用parquet的is_st列
            break
        except Exception:
            continue

    # 从feature parquet获取ST信息
    feat_df = pd.read_parquet(
        PROJECT_ROOT / "data/quantdb/feature_snapshots/model_features_2025.parquet"
        if (PROJECT_ROOT / "data/quantdb/feature_snapshots/model_features_2025.parquet").exists()
        else "/app/db/feature_snapshots/model_features_2025.parquet",
        columns=["symbol", "is_st"],
    )
    st_df = feat_df[pd.to_numeric(feat_df["is_st"], errors="coerce") == 1]
    for sym in st_df["symbol"].unique():
        st_set.add(sym)
    print(f"  ST股票: {len(st_set)} 只")
    return st_set


def is_unbuyable(lookup, trading_days, sym, date, st_set):
    """一字板 或 涨停封板 → 买不进"""
    p = get_price(lookup, sym, date)
    if not p:
        return True
    o, h, l, c = p["open"], p["high"], p["low"], p["close"]

    # 一字板: open=high=low=close
    if abs(o - h) < 0.01 and abs(h - l) < 0.01 and abs(l - c) < 0.01:
        return True

    # 涨停封板: open=high=close, 涨幅 >= 涨停板
    prev_date = get_trading_day_offset(trading_days, date, -1)
    if not prev_date:
        return False
    prev_p = get_price(lookup, sym, prev_date)
    if not prev_p or prev_p["close"] <= 0:
        return False
    pct = (o - prev_p["close"]) / prev_p["close"]
    is_st = sym in st_set
    prefix = sym[:3] if len(sym) >= 3 else sym[:2]
    if is_st:
        limit = 0.045
    elif prefix in ("688", "300", "301"):
        limit = 0.195
    else:
        limit = 0.095
    if pct >= limit and abs(o - h) < 0.01 and abs(o - c) < 0.01:
        return True
    return False


def is_limit_down(lookup, trading_days, sym, date, st_set):
    """跌停封板 → 卖不出"""
    p = get_price(lookup, sym, date)
    if not p:
        return True
    o, h, l, c = p["open"], p["high"], p["low"], p["close"]

    # 一字跌停
    if abs(o - h) < 0.01 and abs(h - l) < 0.01 and abs(l - c) < 0.01:
        if o <= c:
            return True

    # 跌停封板: open=low=close, 跌幅 >= 跌停板
    prev_date = get_trading_day_offset(trading_days, date, -1)
    if not prev_date:
        return False
    prev_p = get_price(lookup, sym, prev_date)
    if not prev_p or prev_p["close"] <= 0:
        return False
    pct = (o - prev_p["close"]) / prev_p["close"]
    is_st = sym in st_set
    prefix = sym[:3] if len(sym) >= 3 else sym[:2]
    if is_st:
        limit = -0.045
    elif prefix in ("688", "300", "301"):
        limit = -0.195
    else:
        limit = -0.095
    if pct <= limit and abs(o - l) < 0.01 and abs(o - c) < 0.01:
        return True
    return False


def run_backtest(inference, lookup, trading_days, st_set):
    """运行回测"""
    dates = sorted(inference.keys())
    capital = INITIAL_CAPITAL
    position = None  # {symbol, buy_date, buy_price, buy_open}
    trades = []
    monthly_stats = {}

    for date_str in dates:
        date = pd.Timestamp(date_str)
        month_key = date.strftime("%Y-%m")

        # 1. 检查持仓是否到期卖出
        if position:
            sell_date = get_trading_day_offset(trading_days, position["buy_date"], HOLD_DAYS)
            if sell_date and date >= sell_date:
                # 卖出
                sell_p = get_price(lookup, position["symbol"], date)
                if sell_p and not is_limit_down(lookup, trading_days, position["symbol"], date, st_set):
                    sell_price = sell_p["close"]
                    profit = (sell_price - position["buy_price"]) / position["buy_price"]
                    profit_amt = position["shares"] * (sell_price - position["buy_price"])
                    capital += position["shares"] * sell_price
                    trades.append({
                        "buy_date": position["buy_date"].strftime("%Y-%m-%d"),
                        "sell_date": date.strftime("%Y-%m-%d"),
                        "symbol": position["symbol"],
                        "sector": classify_sector(position["symbol"]),
                        "buy_price": round(position["buy_price"], 2),
                        "sell_price": round(sell_price, 2),
                        "shares": position["shares"],
                        "profit_pct": round(profit * 100, 2),
                        "profit_amt": round(profit_amt, 2),
                        "score": position["score"],
                        "hold_days": (date - position["buy_date"]).days,
                    })
                    position = None
                elif sell_p and is_limit_down(lookup, trading_days, position["symbol"], date, st_set):
                    # 跌停卖不出，继续持有
                    pass

        # 2. 如果空仓，买入Top1
        if position is None:
            top_stocks = inference[date_str]
            for sym, score in top_stocks[:5]:  # 尝试前5名
                # 检查是否涨停买不进
                next_date = get_trading_day_offset(trading_days, date, 1)
                if not next_date:
                    continue
                if is_unbuyable(lookup, trading_days, sym, next_date, st_set):
                    continue
                # 买入价 = T+1开盘价
                buy_p = get_price(lookup, sym, next_date)
                if not buy_p or buy_p["open"] <= 0:
                    continue
                buy_price = buy_p["open"]
                shares = int(capital / buy_price / 100) * 100  # 整手
                if shares <= 0:
                    shares = 100  # 最少1手
                cost = shares * buy_price
                if cost > capital:
                    shares = int(capital / buy_price / 100) * 100
                    if shares <= 0:
                        continue
                    cost = shares * buy_price
                capital -= cost
                position = {
                    "symbol": sym,
                    "buy_date": next_date,
                    "buy_price": buy_price,
                    "shares": shares,
                    "score": score,
                }
                break

        # 3. 记录月末统计
        if month_key not in monthly_stats:
            monthly_stats[month_key] = {
                "start_capital": capital + (position["shares"] * get_price(lookup, position["symbol"], date)["close"] if position and get_price(lookup, position["symbol"], date) else capital),
                "trades": [],
            }

    # 最后如果还持仓，按最后一天收盘价清仓
    if position:
        last_date = trading_days[-1]
        sell_p = get_price(lookup, position["symbol"], last_date)
        if sell_p:
            sell_price = sell_p["close"]
            profit = (sell_price - position["buy_price"]) / position["buy_price"]
            profit_amt = position["shares"] * (sell_price - position["buy_price"])
            capital += position["shares"] * sell_price
            trades.append({
                "buy_date": position["buy_date"].strftime("%Y-%m-%d"),
                "sell_date": last_date.strftime("%Y-%m-%d"),
                "symbol": position["symbol"],
                "sector": classify_sector(position["symbol"]),
                "buy_price": round(position["buy_price"], 2),
                "sell_price": round(sell_price, 2),
                "shares": position["shares"],
                "profit_pct": round(profit * 100, 2),
                "profit_amt": round(profit_amt, 2),
                "score": position["score"],
                "hold_days": (last_date - position["buy_date"]).days,
            })

    return trades, capital


def analyze_sector_rotation(inference, lookup, trading_days):
    """板块轮动分析：每月各板块信号强度分布"""
    dates = sorted(inference.keys())

    # 每日各板块 Top1 分数和 ≥0.12 股票数
    daily_sector = {}
    for date_str in dates:
        stocks = inference[date_str]
        sector_stats = {}
        for sym, score in stocks:
            sector = classify_sector(sym)
            if sector not in sector_stats:
                sector_stats[sector] = {"top1": score, "count_ge_012": 0, "count_ge_010": 0, "scores": []}
            sector_stats[sector]["scores"].append(score)
            if score >= 0.12:
                sector_stats[sector]["count_ge_012"] += 1
            if score >= 0.10:
                sector_stats[sector]["count_ge_010"] += 1

        # 更新top1为该板块最高分
        for sector in sector_stats:
            sector_stats[sector]["top1"] = max(sector_stats[sector]["scores"])

        daily_sector[date_str] = sector_stats

    # 按月汇总
    monthly_sector = {}
    for date_str, sector_stats in daily_sector.items():
        month_key = date_str[:7]
        if month_key not in monthly_sector:
            monthly_sector[month_key] = {}
        for sector, stats in sector_stats.items():
            if sector not in monthly_sector[month_key]:
                monthly_sector[month_key][sector] = {
                    "top1_scores": [], "ge_012_counts": [], "ge_010_counts": [],
                }
            monthly_sector[month_key][sector]["top1_scores"].append(stats["top1"])
            monthly_sector[month_key][sector]["ge_012_counts"].append(stats["count_ge_012"])
            monthly_sector[month_key][sector]["ge_010_counts"].append(stats["count_ge_010"])

    # 计算月度均值
    result = {}
    for month, sectors in sorted(monthly_sector.items()):
        result[month] = {}
        for sector, data in sectors.items():
            result[month][sector] = {
                "avg_top1": round(np.mean(data["top1_scores"]), 4),
                "max_top1": round(max(data["top1_scores"]), 4),
                "avg_ge_012": round(np.mean(data["ge_012_counts"]), 1),
                "avg_ge_010": round(np.mean(data["ge_010_counts"]), 1),
            }

    return result, daily_sector


def identify_market_state(monthly_sector):
    """根据板块信号强度识别市场状态"""
    states = {}
    for month, sectors in sorted(monthly_sector.items()):
        # 综合所有板块的信号强度
        all_top1 = [s["avg_top1"] for s in sectors.values()]
        all_ge012 = [s["avg_ge_012"] for s in sectors.values()]
        avg_top1 = np.mean(all_top1) if all_top1 else 0
        avg_ge012 = np.mean(all_ge012) if all_ge012 else 0

        # 找出最强板块
        strongest = max(sectors.items(), key=lambda x: x[1]["avg_top1"])
        weakest = min(sectors.items(), key=lambda x: x[1]["avg_top1"])

        # 市场状态判断
        if avg_top1 >= 0.15 and avg_ge012 >= 3:
            state = "牛市"
        elif avg_top1 >= 0.12 and avg_ge012 >= 1.5:
            state = "震荡偏强"
        elif avg_top1 >= 0.10:
            state = "震荡"
        elif avg_top1 >= 0.08:
            state = "震荡偏弱"
        else:
            state = "熊市"

        states[month] = {
            "state": state,
            "avg_top1": round(avg_top1, 4),
            "avg_ge_012": round(avg_ge012, 1),
            "strongest_sector": strongest[0],
            "strongest_top1": strongest[1]["avg_top1"],
            "weakest_sector": weakest[0],
            "weakest_top1": weakest[1]["avg_top1"],
            "sector_details": sectors,
        }

    return states


def main():
    print("=" * 70)
    print("2025年 XGBoost Alpha112 全年回测 + 板块轮动分析")
    print("=" * 70)

    # 1. 加载数据
    inference = load_all_inference()
    print(f"推理数据: {len(inference)} 天")

    lookup, trading_days = load_price_lookup()
    print(f"交易日: {len(trading_days)} 天, {trading_days[0].date()} ~ {trading_days[-1].date()}")

    # ST股票 - 从推理数据中已排除，但价格查找时需要
    # 简化：用空集合（推理时已过滤ST）
    st_set = set()

    # 2. 运行回测
    print("\n运行回测...")
    trades, final_capital = run_backtest(inference, lookup, trading_days, st_set)

    # 3. 回测结果
    total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    win_trades = [t for t in trades if t["profit_pct"] > 0]
    lose_trades = [t for t in trades if t["profit_pct"] <= 0]

    print(f"\n{'='*70}")
    print(f"回测结果")
    print(f"{'='*70}")
    print(f"初始资金: {INITIAL_CAPITAL:,.0f}")
    print(f"最终资金: {final_capital:,.2f}")
    print(f"总收益率: {total_return:.2f}%")
    print(f"总交易次数: {len(trades)}")
    print(f"盈利次数: {len(win_trades)} ({len(win_trades)/len(trades)*100:.1f}%)" if trades else "")
    print(f"亏损次数: {len(lose_trades)} ({len(lose_trades)/len(trades)*100:.1f}%)" if trades else "")
    if win_trades:
        print(f"平均盈利: {np.mean([t['profit_pct'] for t in win_trades]):.2f}%")
    if lose_trades:
        print(f"平均亏损: {np.mean([t['profit_pct'] for t in lose_trades]):.2f}%")

    # 4. 按月统计
    print(f"\n{'='*70}")
    print(f"月度统计")
    print(f"{'='*70}")
    monthly_trades = {}
    for t in trades:
        month = t["sell_date"][:7]
        if month not in monthly_trades:
            monthly_trades[month] = []
        monthly_trades[month].append(t)

    for month in sorted(monthly_trades.keys()):
        mt = monthly_trades[month]
        month_profit = sum(t["profit_amt"] for t in mt)
        month_win = len([t for t in mt if t["profit_pct"] > 0])
        print(f"  {month}: {len(mt)}笔, 盈{month_win}亏{len(mt)-month_win}, "
              f"收益{month_profit:+,.2f}元, "
              f"均收{np.mean([t['profit_pct'] for t in mt]):+.2f}%")

    # 5. 板块轮动分析
    print(f"\n{'='*70}")
    print(f"板块轮动分析")
    print(f"{'='*70}")
    monthly_sector, daily_sector = analyze_sector_rotation(inference, lookup, trading_days)
    market_states = identify_market_state(monthly_sector)

    for month, state in sorted(market_states.items()):
        print(f"\n  {month}: {state['state']} (avg Top1={state['avg_top1']:.4f}, "
              f"≥0.12均{state['avg_ge_012']:.1f}只)")
        print(f"    最强: {state['strongest_sector']} (Top1={state['strongest_top1']:.4f})")
        print(f"    最弱: {state['weakest_sector']} (Top1={state['weakest_top1']:.4f})")
        # 各板块详情
        for sector, data in sorted(state["sector_details"].items(), key=lambda x: -x[1]["avg_top1"]):
            print(f"    {sector}: avg Top1={data['avg_top1']:.4f}, "
                  f"max Top1={data['max_top1']:.4f}, "
                  f"≥0.12均{data['avg_ge_012']:.1f}只, "
                  f"≥0.10均{data['avg_ge_010']:.1f}只")

    # 6. 交易板块分布
    print(f"\n{'='*70}")
    print(f"交易板块分布")
    print(f"{'='*70}")
    sector_trades = {}
    for t in trades:
        sector = t["sector"]
        if sector not in sector_trades:
            sector_trades[sector] = {"count": 0, "win": 0, "profit_amt": 0, "profit_pcts": []}
        sector_trades[sector]["count"] += 1
        if t["profit_pct"] > 0:
            sector_trades[sector]["win"] += 1
        sector_trades[sector]["profit_amt"] += t["profit_amt"]
        sector_trades[sector]["profit_pcts"].append(t["profit_pct"])

    for sector, data in sorted(sector_trades.items(), key=lambda x: -x[1]["profit_amt"]):
        win_rate = data["win"] / data["count"] * 100 if data["count"] > 0 else 0
        avg_pct = np.mean(data["profit_pcts"]) if data["profit_pcts"] else 0
        print(f"  {sector}: {data['count']}笔, 胜率{win_rate:.1f}%, "
              f"收益{data['profit_amt']:+,.2f}元, 均收{avg_pct:+.2f}%")

    # 7. 保存结果
    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(OUTPUT_DIR / "2025_backtest_trades.csv", index=False, encoding="utf-8-sig")

    with open(OUTPUT_DIR / "2025_market_states.json", "w", encoding="utf-8") as f:
        json.dump(market_states, f, ensure_ascii=False, indent=2, default=str)

    with open(OUTPUT_DIR / "2025_sector_rotation.json", "w", encoding="utf-8") as f:
        json.dump(monthly_sector, f, ensure_ascii=False, indent=2, default=str)

    # 8. 生成报告
    report = []
    report.append("=" * 70)
    report.append("2025年 XGBoost Alpha112 全年回测报告")
    report.append("=" * 70)
    report.append(f"策略: 每日Top1, T+1开盘买, 持有{HOLD_DAYS}天收盘卖")
    report.append(f"涨停/跌停过滤: 是")
    report.append(f"ST排除: 是(推理时已过滤)")
    report.append(f"")
    report.append(f"初始资金: {INITIAL_CAPITAL:,.0f}")
    report.append(f"最终资金: {final_capital:,.2f}")
    report.append(f"总收益率: {total_return:.2f}%")
    report.append(f"总交易次数: {len(trades)}")
    if trades:
        report.append(f"盈利次数: {len(win_trades)} ({len(win_trades)/len(trades)*100:.1f}%)")
        report.append(f"亏损次数: {len(lose_trades)} ({len(lose_trades)/len(trades)*100:.1f}%)")
    if win_trades:
        report.append(f"平均盈利: {np.mean([t['profit_pct'] for t in win_trades]):.2f}%")
        report.append(f"最大盈利: {max(t['profit_pct'] for t in win_trades):.2f}%")
    if lose_trades:
        report.append(f"平均亏损: {np.mean([t['profit_pct'] for t in lose_trades]):.2f}%")
        report.append(f"最大亏损: {min(t['profit_pct'] for t in lose_trades):.2f}%")

    report.append(f"")
    report.append(f"{'='*70}")
    report.append(f"月度收益")
    report.append(f"{'='*70}")
    running_capital = INITIAL_CAPITAL
    for month in sorted(monthly_trades.keys()):
        mt = monthly_trades[month]
        month_profit = sum(t["profit_amt"] for t in mt)
        month_win = len([t for t in mt if t["profit_pct"] > 0])
        running_capital += month_profit
        report.append(f"  {month}: {len(mt)}笔, 盈{month_win}亏{len(mt)-month_win}, "
                      f"收益{month_profit:+,.2f}元, 累计资金{running_capital:,.2f}元")

    report.append(f"")
    report.append(f"{'='*70}")
    report.append(f"市场状态 & 板块轮动")
    report.append(f"{'='*70}")
    for month, state in sorted(market_states.items()):
        report.append(f"  {month}: {state['state']} | "
                      f"最强={state['strongest_sector']}({state['strongest_top1']:.4f}) | "
                      f"最弱={state['weakest_sector']}({state['weakest_top1']:.4f})")

    report.append(f"")
    report.append(f"{'='*70}")
    report.append(f"全部交易明细")
    report.append(f"{'='*70}")
    for t in trades:
        report.append(f"  买{t['buy_date']} 卖{t['sell_date']} {t['symbol']}({t['sector']}) "
                      f"买{t['buy_price']:.2f} 卖{t['sell_price']:.2f} "
                      f"收{t['profit_pct']:+.2f}% 赚{t['profit_amt']:+,.2f}元 "
                      f"分{t['score']:.4f}")

    with open(OUTPUT_DIR / "2025_backtest_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print(f"\n结果已保存到: {OUTPUT_DIR}")
    print(f"  2025_backtest_trades.csv - 交易明细")
    print(f"  2025_market_states.json - 市场状态")
    print(f"  2025_sector_rotation.json - 板块轮动")
    print(f"  2025_backtest_report.txt - 完整报告")


if __name__ == "__main__":
    main()
