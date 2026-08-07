#!/usr/bin/env python3
"""
2026年策略回测：三层过滤策略
- 第1层：行业avg Top1 ≥ 0.10 入场，< 0.08 空仓
- 第2层：个股分数 0.10-0.12 黄金区间
- 第3层：主板优先，涨停/跌停过滤
- 仓位：强行业数≥5满仓，3-5半仓，1.5-3轻仓，<1.5空仓
- 止盈8%，止损5%，最长持有5天
- T+1开盘买，收盘卖
- 从2025年12月开始（需要前几天判断趋势），2026年1-7月回测
"""
import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── 配置 ──────────────────────────────────────────────────────────────
INITIAL_CAPITAL = 100000
INDUSTRY_ENTRY_THRESHOLD = 0.10   # 行业avg Top1入场线
INDUSTRY_EXIT_THRESHOLD = 0.08    # 行业avg Top1空仓线
SCORE_MIN = 0.10                  # 个股分数下限
SCORE_MAX = 0.12                  # 个股分数上限
TAKE_PROFIT = 0.08                # 止盈8%
STOP_LOSS = 0.05                  # 止损5%
MAX_HOLD_DAYS = 5                 # 最长持有5天
BUY_DELAY = 1                     # T+1买入
MAIN_BOARDS = {'沪主板', '深主板', '中小板'}  # 主板优先

# ── 路径 ──────────────────────────────────────────────────────────────
INFERENCE_DIR = Path('/app/db/feature_snapshots')
DETAIL_PATH = '/data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet'
PRICE_PARQUET_2025 = '/app/db/feature_snapshots/model_features_2025.parquet'
PRICE_PARQUET_2026 = '/app/db/feature_snapshots/model_features_2026.parquet'
OUTPUT_DIR = Path('/app/db/feature_snapshots/strategy_backtest')

# ── 行业映射 ──────────────────────────────────────────────────────────
def load_industry_map():
    detail = pd.read_parquet(DETAIL_PATH, columns=['Symbol', 'rs_hyname'])
    detail['symbol_num'] = detail['Symbol'].str.replace(r'\.(SH|SZ|BJ)$', '', regex=True)
    return dict(zip(detail['symbol_num'], detail['rs_hyname']))

# ── 板块分类 ──────────────────────────────────────────────────────────
def classify_board(sym):
    prefix = sym[:3] if len(sym) >= 3 else sym[:2]
    if prefix in ('600', '601', '603', '605'):
        return '沪主板'
    elif prefix in ('000', '001', '003'):
        return '深主板'
    elif prefix == '002':
        return '中小板'
    elif prefix in ('300', '301'):
        return '创业板'
    elif prefix in ('688', '689'):
        return '科创板'
    elif prefix.startswith('4') or prefix.startswith('8') or prefix.startswith('9'):
        return '北交所'
    return '其他'

# ── 价格数据 ──────────────────────────────────────────────────────────
def load_price_data():
    """加载价格数据，用pct_change修正除权跳变，返回 {date: {symbol: {open, close, high, low, prev_close, pct_change}}}"""
    prices = {}

    for pq_path in [PRICE_PARQUET_2025, PRICE_PARQUET_2026]:
        if not os.path.exists(pq_path):
            continue
        df = pd.read_parquet(pq_path, columns=['trade_date', 'symbol', 'open', 'close', 'high', 'low', 'pct_change'])
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')

        # 按symbol和date排序，计算前收
        df = df.sort_values(['symbol', 'trade_date'])
        df['prev_close'] = df.groupby('symbol')['close'].shift(1)

        for date, group in df.groupby('trade_date'):
            if date not in prices:
                prices[date] = {}
            for _, row in group.iterrows():
                sym = row['symbol']
                prices[date][sym] = {
                    'open': float(row['open']) if pd.notna(row['open']) else None,
                    'close': float(row['close']) if pd.notna(row['close']) else None,
                    'high': float(row['high']) if pd.notna(row['high']) else None,
                    'low': float(row['low']) if pd.notna(row['low']) else None,
                    'prev_close': float(row['prev_close']) if pd.notna(row['prev_close']) else None,
                    'pct_change': float(row['pct_change']) if pd.notna(row['pct_change']) else None,
                }
    return prices

# ── 推理数据加载 ──────────────────────────────────────────────────────
def load_all_inference():
    """加载所有推理数据，返回 {date: {symbol: score}}"""
    all_data = {}

    # 2025年12月全市场推理
    fp = INFERENCE_DIR / '2025_12_full_inference.json'
    if fp.exists():
        with open(fp) as f:
            d = json.load(f)
        for date, items in d.items():
            all_data[date] = {sym: score for sym, score in items}

    # 2026年1-6月推理（已有全市场JSON）
    for m, fname in [('jan', 'jan_inference.json'), ('feb', 'feb_inference.json'),
                     ('mar', 'mar_inference.json'), ('apr', 'apr_inference.json'),
                     ('may', 'may_inference.json'), ('june', 'june_inference.json')]:
        fp = INFERENCE_DIR / fname
        if fp.exists():
            with open(fp) as f:
                d = json.load(f)
            for date, items in d.items():
                if isinstance(items, list):
                    all_data[date] = {sym: score for sym, score in items}
                elif isinstance(items, dict):
                    all_data[date] = items

    # 2026年7月全市场推理
    fp = INFERENCE_DIR / '2026_07_full_inference.json'
    if fp.exists():
        with open(fp) as f:
            d = json.load(f)
        for date, items in d.items():
            all_data[date] = {sym: score for sym, score in items}

    return all_data

# ── 行业信号计算 ──────────────────────────────────────────────────────
def calc_industry_signals(date_scores, industry_map):
    """计算行业avg Top1和强行业数
    策略定义：行业avg Top1 = Top20中出现的各行业的Top1分数取平均
    不是所有128个行业取平均（弱行业会拉低均值）
    """
    # 先取Top20
    top20 = sorted(date_scores.items(), key=lambda x: -x[1])[:20]

    # 统计Top20中出现的行业的Top1（全市场该行业最高分）
    ind_top1_all = {}
    for sym, score in date_scores.items():
        ind = industry_map.get(sym, '未知')
        if ind not in ind_top1_all:
            ind_top1_all[ind] = score
        else:
            ind_top1_all[ind] = max(ind_top1_all[ind], score)

    # 只取Top20中出现的行业
    top20_inds = set()
    for sym, score in top20:
        ind = industry_map.get(sym, '未知')
        top20_inds.add(ind)

    top20_ind_top1 = {ind: ind_top1_all[ind] for ind in top20_inds if ind in ind_top1_all}
    avg_top1 = np.mean(list(top20_ind_top1.values())) if top20_ind_top1 else 0

    # 强行业数：全市场中Top1>=0.10的行业数
    strong_count = sum(1 for top1 in ind_top1_all.values() if top1 >= INDUSTRY_ENTRY_THRESHOLD)

    return avg_top1, strong_count, ind_top1_all

# ── 仓位计算 ──────────────────────────────────────────────────────────
def calc_position_ratio(avg_top1, strong_count):
    if avg_top1 >= 0.12 and strong_count >= 5:
        return 1.0   # 满仓
    elif avg_top1 >= 0.10 and strong_count >= 3:
        return 0.5   # 半仓
    elif avg_top1 >= 0.08 and strong_count >= 1.5:
        return 0.3   # 轻仓
    else:
        return 0.0   # 空仓

# ── 涨跌停判断 ────────────────────────────────────────────────────────
def is_limit_up(sym, close, prev_close, board):
    if prev_close is None or prev_close <= 0:
        return False
    pct = (close - prev_close) / prev_close
    if board in ('沪主板', '深主板', '中小板'):
        return pct >= 0.099
    elif board in ('创业板', '科创板'):
        return pct >= 0.199
    elif board == '北交所':
        return pct >= 0.299
    return False

def is_limit_down(sym, close, prev_close, board):
    if prev_close is None or prev_close <= 0:
        return False
    pct = (close - prev_close) / prev_close
    if board in ('沪主板', '深主板', '中小板'):
        return pct <= -0.099
    elif board in ('创业板', '科创板'):
        return pct <= -0.199
    elif board == '北交所':
        return pct <= -0.299
    return False

# ── 主回测 ────────────────────────────────────────────────────────────
def run_backtest():
    print("加载行业映射...")
    industry_map = load_industry_map()
    print(f"  行业数: {len(set(industry_map.values()))}")

    print("加载推理数据...")
    inference = load_all_inference()
    dates = sorted(inference.keys())
    print(f"  推理天数: {len(dates)} ({dates[0]} ~ {dates[-1]})")

    print("加载价格数据...")
    prices = load_price_data()
    print(f"  价格天数: {len(prices)}")

    # 只回测2026年1-7月（2025年12月用于趋势判断）
    test_start = '2026-01-05'
    test_end = '2026-07-31'
    test_dates = [d for d in dates if test_start <= d <= test_end]
    print(f"  回测天数: {len(test_dates)}")

    # 持仓: {symbol: {buy_date, buy_price, shares, score, industry, board, cum_return}}
    # cum_return = 累计收益率（从买入日起，用每日pct_change累计）
    holdings = {}
    capital = INITIAL_CAPITAL
    cash = INITIAL_CAPITAL
    trades = []
    daily_stats = []

    # 交易日历（用于T+1买入）
    trading_days = sorted(dates)

    for i, date in enumerate(test_dates):
        date_scores = inference[date]
        avg_top1, strong_count, ind_top1 = calc_industry_signals(date_scores, industry_map)
        pos_ratio = calc_position_ratio(avg_top1, strong_count)

        # ── 每日更新持仓累计收益（用pct_change，避免除权问题）──
        for sym, h in list(holdings.items()):
            if date not in prices or sym not in prices[date]:
                continue
            today_price = prices[date][sym]
            pct = today_price.get('pct_change')
            if pct is not None:
                h['cum_return'] = h.get('cum_return', 0) + pct / 100

        # ── 卖出逻辑 ──
        symbols_to_sell = []
        for sym, h in list(holdings.items()):
            hold_days = trading_days.index(date) - trading_days.index(h['buy_date']) if h['buy_date'] in trading_days else 999

            if date not in prices or sym not in prices[date]:
                continue
            today_price = prices[date][sym]

            cum_ret = h.get('cum_return', 0)

            sell_reason = None

            # 止盈
            if cum_ret >= TAKE_PROFIT:
                sell_reason = f'止盈{TAKE_PROFIT:.0%}'

            # 止损
            if sell_reason is None and cum_ret <= -STOP_LOSS:
                sell_reason = f'止损{STOP_LOSS:.0%}'

            # 最长持有
            if sell_reason is None and hold_days >= MAX_HOLD_DAYS:
                sell_reason = f'到期{MAX_HOLD_DAYS}天'

            # 行业信号消失
            if sell_reason is None:
                ind = h.get('industry', '')
                if ind in ind_top1 and ind_top1[ind] < INDUSTRY_ENTRY_THRESHOLD:
                    if avg_top1 < INDUSTRY_ENTRY_THRESHOLD:
                        sell_reason = f'行业信号消失({ind})'

            # 跌停不卖（用pct_change判断）
            if sell_reason:
                pct = today_price.get('pct_change')
                board = h.get('board', '其他')
                if pct is not None:
                    if board in ('沪主板', '深主板', '中小板') and pct <= -9.9:
                        sell_reason = None
                    elif board in ('创业板', '科创板') and pct <= -19.9:
                        sell_reason = None
                    elif board == '北交所' and pct <= -29.9:
                        sell_reason = None

            if sell_reason:
                symbols_to_sell.append((sym, sell_reason))

        # 执行卖出（用累计收益率计算盈亏，不依赖价格）
        for sym, reason in symbols_to_sell:
            h = holdings[sym]
            cum_ret = h.get('cum_return', 0)
            sell_value = h['cost'] * (1 + cum_ret)  # 用收益率反推卖出金额
            pnl = sell_value - h['cost']
            pnl_pct = cum_ret
            cash += sell_value
            trades.append({
                'action': '卖',
                'date': date,
                'symbol': sym,
                'price': round(h['buy_price'] * (1 + cum_ret), 2),
                'reason': reason,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct * 100, 2),
                'buy_date': h['buy_date'],
                'buy_price': h['buy_price'],
                'score': h['score'],
                'industry': h.get('industry', ''),
                'board': h.get('board', ''),
                'hold_days': trading_days.index(date) - trading_days.index(h['buy_date']) if h['buy_date'] in trading_days else 0,
            })
            del holdings[sym]

        # ── 买入逻辑 ──
        if pos_ratio > 0:
            # 选股：行业Top1≥0.10 + 个股0.10-0.12 + 主板优先
            candidates = []
            for sym, score in date_scores.items():
                if not (SCORE_MIN <= score < SCORE_MAX):
                    continue
                ind = industry_map.get(sym, '未知')
                if ind not in ind_top1 or ind_top1[ind] < INDUSTRY_ENTRY_THRESHOLD:
                    continue
                board = classify_board(sym)
                # 排除已持有
                if sym in holdings:
                    continue
                # 排除北交所
                if board == '北交所':
                    continue
                candidates.append((sym, score, ind, board, ind_top1[ind]))

            # 主板优先排序
            candidates.sort(key=lambda x: (
                0 if x[3] in MAIN_BOARDS else 1,  # 主板优先
                -x[1],                              # 分数高优先
            ))

            # 计算可用资金和目标持仓数
            total_assets = cash + sum(h['cost'] * (1 + h.get('cum_return', 0))
                                       for sym, h in holdings.items())
            target_position = total_assets * pos_ratio
            current_position = total_assets - cash
            available_for_buy = target_position - current_position

            if available_for_buy > 0 and candidates:
                # 选3-5只
                n_buy = min(5, len(candidates), max(1, int(available_for_buy / (total_assets / 5))))
                per_stock_cash = available_for_buy / n_buy

                # T+1买入：明天开盘价
                buy_date_idx = trading_days.index(date) + 1 if date in trading_days else -1
                if buy_date_idx < len(trading_days):
                    buy_date = trading_days[buy_date_idx]
                else:
                    buy_date = None

                if buy_date and buy_date in prices:
                    for sym, score, ind, board, ind_t1 in candidates[:n_buy]:
                        if sym in holdings:
                            continue
                        buy_price_data = prices[buy_date].get(sym)
                        if not buy_price_data or buy_price_data.get('open') is None:
                            continue
                        buy_price = buy_price_data['open']

                        # 涨停不买
                        prev_date = trading_days[trading_days.index(date)] if date in trading_days else None
                        prev_close = prices.get(date, {}).get(sym, {}).get('close')
                        if is_limit_up(sym, buy_price, prev_close, board):
                            continue

                        shares = int(per_stock_cash / buy_price / 100) * 100  # 整手
                        if shares <= 0:
                            shares = 100  # 最少1手
                        cost = shares * buy_price
                        if cost > cash:
                            shares = int(cash / buy_price / 100) * 100
                            if shares <= 0:
                                continue
                            cost = shares * buy_price

                        cash -= cost
                        holdings[sym] = {
                            'buy_date': buy_date,
                            'buy_price': buy_price,
                            'score': score,
                            'industry': ind,
                            'board': board,
                            'shares': shares,
                            'cost': cost,
                            'cum_return': 0,  # 累计收益率（用pct_change计算）
                        }
                        trades.append({
                            'action': '买',
                            'date': buy_date,
                            'symbol': sym,
                            'price': round(buy_price, 2),
                            'reason': f'分{score:.4f}({ind})',
                            'pnl': 0,
                            'pnl_pct': 0,
                            'buy_date': buy_date,
                            'buy_price': buy_price,
                            'score': score,
                            'industry': ind,
                            'board': board,
                            'hold_days': 0,
                        })

        # ── 日统计 ──
        total_assets = cash
        for sym, h in holdings.items():
            cum_ret = h.get('cum_return', 0)
            total_assets += h['cost'] * (1 + cum_ret)

        daily_stats.append({
            'date': date,
            'avg_top1': round(avg_top1, 4),
            'strong_count': strong_count,
            'pos_ratio': pos_ratio,
            'holdings': len(holdings),
            'cash': round(cash, 2),
            'total_assets': round(total_assets, 2),
            'return_pct': round((total_assets / INITIAL_CAPITAL - 1) * 100, 2),
        })

    # ── 7月底强制清仓 ──
    last_date = test_dates[-1]
    for sym, h in list(holdings.items()):
        cum_ret = h.get('cum_return', 0)
        sell_value = h['cost'] * (1 + cum_ret)
        pnl = sell_value - h['cost']
        pnl_pct = cum_ret
        cash += sell_value
        trades.append({
            'action': '卖',
            'date': last_date,
            'symbol': sym,
            'price': round(sell_price, 2),
            'reason': '期末清仓',
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct * 100, 2),
            'buy_date': h['buy_date'],
            'buy_price': h['buy_price'],
            'score': h['score'],
            'industry': h.get('industry', ''),
            'board': h.get('board', ''),
            'hold_days': 0,
        })
        del holdings[sym]

    # ── 输出报告 ──
    final_assets = cash
    total_return = (final_assets / INITIAL_CAPITAL - 1) * 100

    # 买卖配对
    buy_trades = [t for t in trades if t['action'] == '买']
    sell_trades = [t for t in trades if t['action'] == '卖']

    # 统计
    win_trades = [t for t in sell_trades if t['pnl'] > 0]
    lose_trades = [t for t in sell_trades if t['pnl'] < 0]
    zero_trades = [t for t in sell_trades if t['pnl'] == 0]

    print()
    print('=' * 70)
    print('2026年 三层过滤策略回测报告')
    print('=' * 70)
    print(f'策略: 行业avg Top1≥0.10 + 个股0.10-0.12 + 主板优先')
    print(f'止盈: {TAKE_PROFIT:.0%}  止损: {STOP_LOSS:.0%}  最长持有: {MAX_HOLD_DAYS}天')
    print(f'回测期: {test_start} ~ {test_end}')
    print()
    print(f'初始资金: {INITIAL_CAPITAL:,.0f}')
    print(f'最终资金: {final_assets:,.2f}')
    print(f'总收益率: {total_return:.2f}%')
    print(f'买入次数: {len(buy_trades)}')
    print(f'卖出次数: {len(sell_trades)}')
    print(f'盈利次数: {len(win_trades)} ({len(win_trades)/max(1,len(sell_trades))*100:.1f}%)')
    print(f'亏损次数: {len(lose_trades)} ({len(lose_trades)/max(1,len(sell_trades))*100:.1f}%)')
    print(f'持平次数: {len(zero_trades)}')
    if win_trades:
        print(f'平均盈利: {np.mean([t["pnl_pct"] for t in win_trades]):.2f}%')
        print(f'最大盈利: {max(t["pnl_pct"] for t in win_trades):.2f}%')
    if lose_trades:
        print(f'平均亏损: {np.mean([t["pnl_pct"] for t in lose_trades]):.2f}%')
        print(f'最大亏损: {min(t["pnl_pct"] for t in lose_trades):.2f}%')

    # 月度统计
    print()
    print('=' * 70)
    print('月度收益')
    print('=' * 70)
    monthly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0})
    for t in sell_trades:
        month = t['date'][:7]
        monthly[month]['trades'] += 1
        monthly[month]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            monthly[month]['wins'] += 1
        elif t['pnl'] < 0:
            monthly[month]['losses'] += 1

    # 月度资产
    monthly_assets = {}
    for ds in daily_stats:
        month = ds['date'][:7]
        monthly_assets[month] = ds['total_assets']

    for month in sorted(monthly.keys()):
        m = monthly[month]
        assets = monthly_assets.get(month, INITIAL_CAPITAL)
        print(f'  {month}: {m["trades"]}笔, 盈{m["wins"]}亏{m["losses"]}, '
              f'盈亏{m["pnl"]:+,.0f}元, 资产{assets:,.0f}元')

    # 每日市场状态
    print()
    print('=' * 70)
    print('每日市场状态')
    print('=' * 70)
    for ds in daily_stats:
        state = '满仓' if ds['pos_ratio'] == 1.0 else '半仓' if ds['pos_ratio'] == 0.5 else '轻仓' if ds['pos_ratio'] == 0.3 else '空仓'
        print(f'  {ds["date"]}: avgTop1={ds["avg_top1"]:.4f} 强行业={ds["strong_count"]:>2} '
              f'{state:>4} 持{ds["holdings"]}只 资产{ds["total_assets"]:>10,.0f} 收{ds["return_pct"]:>+6.2f}%')

    # 交易明细
    print()
    print('=' * 70)
    print('全部交易明细')
    print('=' * 70)
    for t in trades:
        action = t['action']
        print(f'  {action} {t["date"]} {t["symbol"]}({t.get("board","")}) '
              f'价{t["price"]:.2f} {t["reason"]} '
              f'{"盈亏" + str(t["pnl"]):>10} ({t["pnl_pct"]:+.2f}%) '
              f'分{t.get("score",0):.4f} {t.get("industry","")}')

    # 保存CSV
    out_dir = OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(out_dir / 'strategy_trades.csv', index=False, encoding='utf-8-sig')

    daily_df = pd.DataFrame(daily_stats)
    daily_df.to_csv(out_dir / 'strategy_daily.csv', index=False, encoding='utf-8-sig')

    print(f'\n已保存: {out_dir / "strategy_trades.csv"}')
    print(f'已保存: {out_dir / "strategy_daily.csv"}')

if __name__ == '__main__':
    run_backtest()
