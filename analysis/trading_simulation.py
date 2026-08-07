#!/usr/bin/env python3
"""
XGBoost Alpha112 模型交易模拟系统
===================================
基于回测策略自动选股、买入、卖出，模拟10万资金滚动操作

策略规则:
  买入条件:
    1. 分数0.12-0.20
    2. 今天分数 > 昨天分数 (上升趋势)
    3. 主板优先 (600/000开头)
    4. 排名前50内
    5. 排除ST股
    6. 前3名如果是ST股，次日跌出前20就卖出持仓

  卖出条件:
    1. 持有2-4天最优, 最多5天
    2. 止盈: +8% (日内最高触及)
    3. 止损: -5% (日内最低触及)
    4. 第5天收盘强制卖出
    5. 分数连续下降2天+排名跌出Top50 → 提前卖出
    6. 前3名出现ST且次日跌出前20 → 卖出该持仓

  仓位管理:
    - 最多5只股票
    - 每只等仓(总资金/5)
    - 卖出2只后次日补2只(如果符合条件)
    - 没有符合条件的就空仓
"""

import pandas as pd
import numpy as np
import psycopg2
import pickle
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
QUANTDB_DAILY = PROJECT_ROOT / "data/quantdb/1_kline_data/daily_unadjusted"
OUTPUT_DIR = PROJECT_ROOT / "analysis/top20_tracking"
MODEL_ID = "mdl_train_20260804025559_058f404d_49f72631"

INITIAL_CAPITAL = 100000
MAX_POSITIONS = 5
TAKE_PROFIT = 0.08
STOP_LOSS = 0.05
MAX_HOLD_DAYS = 5
SCORE_MIN = 0.12
SCORE_MAX = 0.20
MIN_RANK = 50


def load_data():
    """加载信号和价格数据"""
    # 信号数据
    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="quantmind", user="quantmind", password="quantmind2026",
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT s.trade_date, s.symbol, s.fusion_score, s.signal_side, r.data_trade_date
        FROM engine_signal_scores s
        JOIN qm_model_inference_runs r ON s.run_id = r.run_id
        WHERE r.model_id = %s AND s.signal_side = 'BUY'
        ORDER BY s.trade_date, s.fusion_score DESC
    """, (MODEL_ID,))
    rows = cur.fetchall()
    conn.close()

    signals = pd.DataFrame(rows, columns=["trade_date", "symbol", "fusion_score", "signal_side", "data_date"])
    signals["trade_date"] = pd.to_datetime(signals["trade_date"])
    signals["data_date"] = pd.to_datetime(signals["data_date"])

    # ST股票列表 (从stocks表获取)
    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="quantmind", user="quantmind", password="quantmind2026",
    )
    cur = conn.cursor()
    cur.execute("SELECT symbol, name FROM stocks WHERE name LIKE '%%ST%%' OR name LIKE '%%*ST%%'")
    st_rows = cur.fetchall()
    conn.close()

    # 转成纯数字格式
    st_set = set()
    for sym, name in st_rows:
        num = sym.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        st_set.add(num)

    # 价格数据
    pkl_path = OUTPUT_DIR / "price_lookup_full.pkl"
    if not pkl_path.exists():
        pkl_path = OUTPUT_DIR / "price_lookup.pkl"

    with open(pkl_path, "rb") as f:
        price_lookup = pickle.load(f)

    # 补充6/26-7/19的价格数据(如果用的是旧缓存)
    all_price_dates = sorted(set(k[1] for k in price_lookup.keys()))
    if all_price_dates[0] > pd.Timestamp("2026-06-29"):
        print("补充6/26-7/19价格数据...")
        current = pd.Timestamp("2026-06-26")
        end = pd.Timestamp("2026-07-19")
        while current <= end:
            dt_str = current.strftime("%Y%m%d")
            partition = QUANTDB_DAILY / f"dt={dt_str}"
            if partition.exists():
                try:
                    df = pd.read_parquet(partition, columns=["symbol", "time", "open", "high", "low", "close", "volume", "amount"])
                    df["time"] = pd.to_datetime(df["time"])
                    df["symbol_num"] = df["symbol"].str.replace(r"\.(SH|SZ|BJ)$", "", regex=True)
                    for _, row in df.iterrows():
                        key = (row["symbol_num"], pd.Timestamp(row["time"]))
                        if key not in price_lookup:
                            price_lookup[key] = {
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": float(row["volume"]),
                                "amount": float(row["amount"]),
                            }
                except Exception:
                    pass
            current += pd.Timedelta(days=1)

        with open(OUTPUT_DIR / "price_lookup_full.pkl", "wb") as f:
            pickle.dump(price_lookup, f)

    # 构建每日排名
    all_dates = sorted(signals["trade_date"].unique())
    daily_rank = {}
    for d in all_dates:
        day_df = signals[signals["trade_date"] == d].copy()
        day_df = day_df.sort_values("fusion_score", ascending=False).reset_index(drop=True)
        day_df["rank"] = range(1, len(day_df) + 1)
        daily_rank[d] = day_df.set_index("symbol")

    return signals, price_lookup, daily_rank, st_set, all_dates


def get_price(price_lookup, sym, date):
    """获取价格"""
    return price_lookup.get((sym, pd.Timestamp(date)), {})


class Position:
    """持仓"""
    def __init__(self, symbol, buy_date, buy_price, shares, score_at_buy):
        self.symbol = symbol
        self.buy_date = buy_date
        self.buy_price = buy_price
        self.shares = shares
        self.score_at_buy = score_at_buy
        self.hold_days = 0
        self.sell_reason = None
        self.sell_price = None
        self.sell_date = None
        self.profit = 0
        self.profit_pct = 0

    def current_value(self, price_lookup, date):
        p = get_price(price_lookup, self.symbol, date)
        current_price = p.get("close", self.buy_price)
        return self.shares * current_price

    def check_sell(self, price_lookup, date, daily_rank, all_dates, st_set):
        """检查是否应该卖出, 返回 (should_sell, reason)"""
        self.hold_days += 1
        p = get_price(price_lookup, self.symbol, date)

        if not p or p.get("close", 0) <= 0:
            return False, None

        current_price = p.get("close", self.buy_price)
        high = p.get("high", current_price)
        low = p.get("low", current_price)

        profit_pct = (current_price - self.buy_price) / self.buy_price
        high_pct = (high - self.buy_price) / self.buy_price
        low_pct = (low - self.buy_price) / self.buy_price

        # 1. 止盈
        if high_pct >= TAKE_PROFIT:
            return True, f"止盈+{high_pct*100:.1f}%"

        # 2. 止损
        if low_pct <= -STOP_LOSS:
            return True, f"止损{low_pct*100:.1f}%"

        # 3. 最大持仓天数
        if self.hold_days >= MAX_HOLD_DAYS:
            return True, f"到期{profit_pct*100:+.1f}%"

        # 4. 分数连续下降+排名跌出Top50
        date_idx = all_dates.index(date) if date in all_dates else -1
        if date_idx >= 0 and self.symbol in daily_rank[date].index:
            curr_rank = daily_rank[date].loc[self.symbol, "rank"]
            curr_score = daily_rank[date].loc[self.symbol, "fusion_score"]

            if curr_rank > MIN_RANK and self.score_at_buy > curr_score:
                # 排名跌出Top50且分数下降
                if date_idx > 0:
                    prev_date = all_dates[date_idx - 1]
                    if self.symbol in daily_rank[prev_date].index:
                        prev_score = daily_rank[prev_date].loc[self.symbol, "fusion_score"]
                        if prev_score > curr_score:
                            return True, f"排名{curr_rank}+分数连降"

        # 5. 前3名ST股规则: 如果当前股票在前3名且是ST, 次日跌出前20就卖
        if date_idx >= 0:
            curr_rk = daily_rank[date]
            if self.symbol in curr_rk.index:
                rank = curr_rk.loc[self.symbol, "rank"]
                if rank <= 3 and self.symbol in st_set:
                    # ST股在前3, 检查次日是否跌出前20
                    if date_idx + 1 < len(all_dates):
                        next_date = all_dates[date_idx + 1]
                        if self.symbol in daily_rank[next_date].index:
                            next_rank = daily_rank[next_date].loc[self.symbol, "rank"]
                            if next_rank > 20:
                                return True, f"ST股跌出前20(排名{next_rank})"

        return False, None


def select_candidates(sig_date, daily_rank, all_dates, st_set, price_lookup, existing_positions, num_needed):
    """选出符合条件的买入候选"""
    if num_needed <= 0:
        return []

    date_idx = all_dates.index(sig_date) if sig_date in all_dates else -1
    if date_idx < 1:
        return []

    prev_date = all_dates[date_idx - 1]
    curr_rk = daily_rank[sig_date]
    prev_rk = daily_rank[prev_date]

    existing_syms = {p.symbol for p in existing_positions}

    candidates = []
    for sym, row in curr_rk.head(MIN_RANK).iterrows():
        score = row["fusion_score"]
        rank = row["rank"]

        # 条件1: 分数0.12-0.20
        if score < SCORE_MIN or score >= SCORE_MAX:
            continue

        # 条件2: 只做主板 (600/000开头), 排除创业板(30/301)和科创板(688)
        code_prefix = sym[:3] if len(sym) >= 3 else sym[:2]
        if code_prefix not in ("600", "601", "603", "605", "000", "001", "002", "003"):
            continue

        # 条件3: 排除ST
        if sym in st_set:
            continue

        # 条件4: 今天分数 > 昨天分数
        if sym not in prev_rk.index:
            continue
        if score <= prev_rk.loc[sym, "fusion_score"]:
            continue

        # 条件4b: 分数涨幅不过大 (防过热: 涨幅超50%不追)
        prev_score = prev_rk.loc[sym, "fusion_score"]
        if prev_score > 0 and (score - prev_score) / prev_score > 0.5:
            continue

        # 条件4c: 昨天分数不能太低 (要求有基础: 昨天分数>=0.10)
        if prev_score < 0.10:
            continue

        # 条件4d: 排除"连续上升"模式 (3天连续上升=过热)
        # 需要3天数据: 前前天、昨天、今天
        date_idx = all_dates.index(sig_date) if sig_date in all_dates else -1
        if date_idx >= 2:
            prev_prev_date = all_dates[date_idx - 2]
            if sym in daily_rank[prev_prev_date].index:
                prev_prev_score = daily_rank[prev_prev_date].loc[sym, "fusion_score"]
                if prev_prev_score > 0 and prev_score > prev_prev_score and score > prev_score:
                    continue  # 连续3天上升, 过热

        # 条件5: 已经持仓的不重复买
        if sym in existing_syms:
            continue

        # 条件6: 有开盘价可买
        t_open = get_price(price_lookup, sym, sig_date).get("open")
        if t_open is None or t_open <= 0:
            continue

        # 涨停板检查 (开盘价=最高价=最低价=收盘价, 或开盘涨幅>9.5%)
        t_close = get_price(price_lookup, sym, sig_date).get("close")
        if t_close and (t_close - t_open) / t_open > 0.095:
            continue  # 涨停无法买入

        candidates.append({
            "symbol": sym,
            "score": score,
            "prev_score": prev_rk.loc[sym, "fusion_score"],
            "rank": rank,
            "buy_price": t_open,
        })

    # 按分数降序排列, 取前num_needed个
    candidates.sort(key=lambda x: -x["score"])
    return candidates[:num_needed]


def run_simulation(start_date_str, end_date_str):
    """运行交易模拟"""
    signals, price_lookup, daily_rank, st_set, all_dates = load_data()

    start_date = pd.Timestamp(start_date_str)
    end_date = pd.Timestamp(end_date_str)

    # 筛选交易日
    sim_dates = [d for d in all_dates if start_date <= d <= end_date]
    if not sim_dates:
        print(f"无信号数据: {start_date_str} ~ {end_date_str}")
        return

    print(f"模拟区间: {sim_dates[0].strftime('%Y-%m-%d')} ~ {sim_dates[-1].strftime('%Y-%m-%d')}, 共{len(sim_dates)}个交易日")
    print(f"初始资金: {INITIAL_CAPITAL:,.0f}")
    print(f"最大持仓: {MAX_POSITIONS}只, 止盈{TAKE_PROFIT*100:.0f}%, 止损{STOP_LOSS*100:.0f}%, 最长持{MAX_HOLD_DAYS}天")
    print(f"选股条件: 分数{SCORE_MIN}-{SCORE_MAX} + 主板 + 上升趋势 + 非ST")
    print()

    # 获取价格日历
    all_price_dates = sorted(set(k[1] for k in price_lookup.keys()))

    # 初始化
    cash = INITIAL_CAPITAL
    positions = []
    trade_log = []
    daily_log = []
    total_buys = 0
    total_sells = 0

    for day_idx, sig_date in enumerate(sim_dates):
        date_str = sig_date.strftime("%Y-%m-%d")

        # 当日价格日期
        price_dates_from_sig = [d for d in all_price_dates if d >= sig_date]
        if not price_dates_from_sig:
            continue

        # === 1. ST前3名预警: 如果当天前3名有ST股, 标记为危险信号 ===
        st_top3_warning = False
        if sig_date in daily_rank:
            top3 = daily_rank[sig_date].head(3)
            for sym_t3, row_t3 in top3.iterrows():
                if sym_t3 in st_set:
                    st_top3_warning = True
                    break

        # === 2. 检查持仓卖出 ===
        sells_today = []
        for pos in positions:
            should_sell, reason = pos.check_sell(price_lookup, sig_date, daily_rank, all_dates, st_set)
            if not should_sell and st_top3_warning:
                # ST前3预警: 检查持仓中有没有前一天在前3的ST股, 今天跌出前20
                date_idx = all_dates.index(sig_date) if sig_date in all_dates else -1
                if date_idx > 0:
                    prev_d = all_dates[date_idx - 1]
                    prev_top3 = daily_rank[prev_d].head(3)
                    for sym_t3, row_t3 in prev_top3.iterrows():
                        if sym_t3 in st_set and pos.symbol == sym_t3:
                            # ST股从前3跌出前20
                            curr_rank_val = daily_rank[sig_date].loc[pos.symbol, "rank"] if pos.symbol in daily_rank[sig_date].index else 999
                            if curr_rank_val > 20:
                                should_sell = True
                                reason = f"ST股{pos.symbol}从前3跌出前20(排名{curr_rank_val})"
                                break

            if should_sell:
                p = get_price(price_lookup, pos.symbol, sig_date)
                # 止盈/止损用触发价, 其他用收盘价
                if "止盈" in reason:
                    sell_price = pos.buy_price * (1 + TAKE_PROFIT)
                elif "止损" in reason:
                    sell_price = pos.buy_price * (1 - STOP_LOSS)
                else:
                    sell_price = p.get("close", pos.buy_price)

                sell_amount = pos.shares * sell_price
                profit = sell_amount - pos.shares * pos.buy_price
                profit_pct = (sell_price - pos.buy_price) / pos.buy_price

                pos.sell_price = sell_price
                pos.sell_date = sig_date
                pos.sell_reason = reason
                pos.profit = profit
                pos.profit_pct = profit_pct

                cash += sell_amount
                sells_today.append(pos)
                total_sells += 1

                trade_log.append({
                    "date": date_str,
                    "action": "卖出",
                    "symbol": pos.symbol,
                    "price": round(sell_price, 2),
                    "shares": pos.shares,
                    "amount": round(sell_amount, 2),
                    "profit": round(profit, 2),
                    "profit_pct": f"{profit_pct*100:+.1f}%",
                    "reason": reason,
                    "hold_days": pos.hold_days,
                    "score_at_buy": f"{pos.score_at_buy:.3f}",
                })

        for pos in sells_today:
            positions.remove(pos)

        # === 3. 选股买入 ===
        # ST前3预警: 如果前3有ST且今天该ST跌出前20, 不开新仓
        skip_buy = False
        date_idx_chk = all_dates.index(sig_date) if sig_date in all_dates else -1
        if date_idx_chk > 0 and st_top3_warning:
            prev_d = all_dates[date_idx_chk - 1]
            prev_top3 = daily_rank[prev_d].head(3)
            for sym_t3, row_t3 in prev_top3.iterrows():
                if sym_t3 in st_set:
                    curr_rank_val = daily_rank[sig_date].loc[sym_t3, "rank"] if sym_t3 in daily_rank[sig_date].index else 999
                    if curr_rank_val > 20:
                        skip_buy = True
                        trade_log.append({
                            "date": date_str,
                            "action": "跳过",
                            "symbol": sym_t3,
                            "price": "",
                            "shares": "",
                            "amount": "",
                            "profit": "",
                            "profit_pct": "",
                            "reason": f"ST股{sym_t3}从前3跌出前20, 不开新仓",
                            "hold_days": "",
                            "score_at_buy": "",
                        })
                        break

        num_to_buy = MAX_POSITIONS - len(positions)
        if num_to_buy > 0 and not skip_buy:
            candidates = select_candidates(
                sig_date, daily_rank, all_dates, st_set, price_lookup, positions, num_to_buy
            )

            for cand in candidates:
                # 等权分配: 用总资金/5作为每只的买入金额
                buy_amount = INITIAL_CAPITAL / MAX_POSITIONS
                if cash < buy_amount * 0.5:  # 资金不足一半就不买
                    continue

                buy_price = cand["buy_price"]
                # 检查涨停 (无法买入)
                p = get_price(price_lookup, cand["symbol"], sig_date)
                if p.get("high") and p.get("low"):
                    if p["high"] == p["low"] == buy_price:  # 一字板
                        continue

                shares = int(buy_amount / buy_price / 100) * 100  # 整百股
                if shares <= 0:
                    shares = 100  # 最少100股

                actual_amount = shares * buy_price
                if actual_amount > cash:
                    shares = int(cash / buy_price / 100) * 100
                    if shares <= 0:
                        continue
                    actual_amount = shares * buy_price

                cash -= actual_amount
                pos = Position(
                    symbol=cand["symbol"],
                    buy_date=sig_date,
                    buy_price=buy_price,
                    shares=shares,
                    score_at_buy=cand["score"],
                )
                positions.append(pos)
                total_buys += 1

                trade_log.append({
                    "date": date_str,
                    "action": "买入",
                    "symbol": cand["symbol"],
                    "price": round(buy_price, 2),
                    "shares": shares,
                    "amount": round(actual_amount, 2),
                    "profit": "",
                    "profit_pct": "",
                    "reason": f"分数{cand['score']:.3f}(昨{cand['prev_score']:.3f}) 排名{cand['rank']}",
                    "hold_days": "",
                    "score_at_buy": f"{cand['score']:.3f}",
                })

        # === 3. 日志 ===
        portfolio_value = cash + sum(p.current_value(price_lookup, sig_date) for p in positions)
        total_return = (portfolio_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

        pos_info = ""
        for p in positions:
            cp = get_price(price_lookup, p.symbol, sig_date).get("close", p.buy_price)
            pnl = (cp - p.buy_price) / p.buy_price * 100
            pos_info += f"\n    {p.symbol} 买入{p.buy_price:.2f} 现{cp:.2f} ({pnl:+.1f}%) 持{p.hold_days}天"

        daily_log.append({
            "date": date_str,
            "cash": round(cash, 2),
            "positions": len(positions),
            "portfolio_value": round(portfolio_value, 2),
            "total_return_pct": round(total_return, 2),
        })

        print(f"{date_str} | 现金{cash:>10,.0f} | 持仓{len(positions)}只 | 总资产{portfolio_value:>10,.0f} | 收益{total_return:>+.2f}%{pos_info}")

    # === 最终平仓 ===
    print(f"\n{'='*80}")
    print("模拟结束, 强制平仓剩余持仓")
    last_date = sim_dates[-1]

    for pos in positions:
        p = get_price(price_lookup, pos.symbol, last_date)
        sell_price = p.get("close", pos.buy_price)
        sell_amount = pos.shares * sell_price
        profit = sell_amount - pos.shares * pos.buy_price
        profit_pct = (sell_price - pos.buy_price) / pos.buy_price

        cash += sell_amount
        total_sells += 1

        trade_log.append({
            "date": last_date.strftime("%Y-%m-%d"),
            "action": "清仓",
            "symbol": pos.symbol,
            "price": round(sell_price, 2),
            "shares": pos.shares,
            "amount": round(sell_amount, 2),
            "profit": round(profit, 2),
            "profit_pct": f"{profit_pct*100:+.1f}%",
            "reason": "模拟结束清仓",
            "hold_days": pos.hold_days,
            "score_at_buy": f"{pos.score_at_buy:.3f}",
        })

    # === 统计 ===
    final_value = cash
    final_return = (final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    sells = [t for t in trade_log if t["action"] in ("卖出", "清仓")]
    buys = [t for t in trade_log if t["action"] == "买入"]

    print(f"\n{'='*80}")
    print("交易统计")
    print(f"{'='*80}")
    print(f"  初始资金:   {INITIAL_CAPITAL:>12,.0f}")
    print(f"  最终资产:   {final_value:>12,.0f}")
    print(f"  总收益:     {final_return:>+.2f}%")
    print(f"  总买入:     {total_buys:>6} 次")
    print(f"  总卖出:     {total_sells:>6} 次")

    if sells:
        profits = []
        for s in sells:
            try:
                profits.append(float(s["profit_pct"].replace("%", "").replace("+", "")))
            except (ValueError, AttributeError):
                pass

        if profits:
            wins = [p for p in profits if p > 0]
            losses = [p for p in profits if p < 0]
            print(f"\n  交易统计 (已完成{len(profits)}笔):")
            print(f"    胜率:     {len(wins)/len(profits)*100:.1f}% ({len(wins)}/{len(profits)})")
            print(f"    均收:     {np.mean(profits):+.2f}%")
            print(f"    最大盈利: {max(profits):+.2f}%")
            print(f"    最大亏损: {min(profits):+.2f}%")
            print(f"    盈亏比:   {np.mean(wins)/abs(np.mean(losses)) if losses else float('inf'):.2f}")

    # 卖出原因统计
    reasons = {}
    for s in sells:
        r = s["reason"].split("+")[0].split("跌出")[0].strip()  # 简化
        if "止盈" in s["reason"]:
            r = "止盈"
        elif "止损" in s["reason"]:
            r = "止损"
        elif "到期" in s["reason"]:
            r = "到期"
        elif "排名" in s["reason"]:
            r = "分数连降"
        elif "ST" in s["reason"]:
            r = "ST股跌出"
        elif "清仓" in s["reason"]:
            r = "模拟结束"
        else:
            r = s["reason"]
        reasons[r] = reasons.get(r, 0) + 1

    print(f"\n  卖出原因分布:")
    for r, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {r}: {count}次")

    # 保存
    trade_df = pd.DataFrame(trade_log)
    trade_df.to_csv(OUTPUT_DIR / "trade_simulation.csv", index=False, encoding="utf-8-sig")

    daily_df = pd.DataFrame(daily_log)
    daily_df.to_csv(OUTPUT_DIR / "daily_portfolio.csv", index=False, encoding="utf-8-sig")

    print(f"\n交易记录已保存到 {OUTPUT_DIR}/trade_simulation.csv")
    print(f"每日资产已保存到 {OUTPUT_DIR}/daily_portfolio.csv")

    return trade_log, daily_log


if __name__ == "__main__":
    # 6/29开始(6/26是周末无信号), 到8/4
    run_simulation("2026-06-29", "2026-08-04")
