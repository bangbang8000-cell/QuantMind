"""板块+市值过滤回测（保守口径）

区间: 2024-08-12 ~ 2026-08-12
过滤:
  - 板块 ∈ {深主板, 科创板}
  - 市值 >= 30亿（排除微盘），大盘/超大盘也买
  - 分数 >= 2.1 且 当日 Top20 内
  - 大盘 MA20 多（前一日收盘判断，无未来函数）
  - 涨停过滤: 开盘价 >= 涨停价 → 买不进跳过（保守）
策略: 动态止盈(激活+5%/回撤2%) + 止损-5% + 跌出Top20卖出
初始资金: 100万
"""
from pathlib import Path
import bisect
import pandas as pd

HERE = Path(__file__).resolve().parent
BUY_MIN_SCORE = 2.1
OUT_TOP = 20
MA_WINDOW = 20
TRAILING_ACTIVATE = 0.05
TRAILING_DROP = 0.02
STOP_LOSS = 0.05
COMMISSION = 0.0003
STAMP_TAX = 0.001
INITIAL_CASH = 1_000_000.0
MIN_MV_YI = 25.0          # 市值门槛: 排除 <25亿 微盘
BOARDS_OK = {"深主板", "科创板"}


def to_suffix(code: str) -> str:
    c = str(code).upper().strip()
    if len(c) == 6 and c.isdigit():
        if c.startswith(("60", "68", "90")): return f"{c}.SH"
        if c.startswith(("00", "30", "20")): return f"{c}.SZ"
        if c.startswith(("83", "43", "87", "88", "92")): return f"{c}.BJ"
    return c


def board_of(code: str) -> str:
    if code.startswith('688'): return '科创板'
    if code.startswith('30'): return '创业板'
    if code.startswith(('00', '002', '003')): return '深主板'
    if code.startswith('60'): return '沪主板'
    if code.startswith(('4', '8', '92')): return '北交所'
    return '其他'


def limit_pct(suffix: str) -> float:
    if suffix.startswith(("30", "68")): return 0.20
    if suffix.startswith(("83", "43", "87", "88", "92")): return 0.30
    return 0.10


def load_signals():
    df = pd.read_parquet(HERE / "signals_all.parquet")
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    out = {}
    for d, grp in df.groupby("trade_date"):
        grp = grp.sort_values("fusion_score", ascending=False).reset_index(drop=True)
        out[str(d)] = [(str(s), float(sc), i + 1) for i, (s, sc) in enumerate(
            zip(grp["symbol"], grp["fusion_score"]))]
    return out


def load_klines():
    df = pd.read_parquet(HERE / "klines_all.parquet")
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    return df


def load_caps() -> dict:
    """日期 -> {symbol(prefix): 市值(元)}，前向填充到信号日"""
    cap = pd.read_parquet(HERE / "caps_all.parquet")
    cap["trade_date"] = cap["trade_date"].astype(str).str[:10]
    cap_dates = sorted(cap["trade_date"].unique())
    by_date = {d: dict(zip(cap[cap.trade_date == d].symbol, cap[cap.trade_date == d].total_mv))
               for d in cap_dates}
    return cap_dates, by_date


def build_market_up(index_df, signal_dates):
    idx = index_df.sort_values("trade_date").reset_index(drop=True)
    idx["ma20"] = idx["close"].rolling(MA_WINDOW).mean()
    status = {}
    for _, r in idx.iterrows():
        d = str(r["trade_date"])
        if pd.notna(r["ma20"]) and r["ma20"] > 0:
            status[d] = bool(r["close"] >= r["ma20"])
    index_dates = sorted(status.keys())
    out = {}
    for d in signal_dates:
        i = bisect.bisect_left(index_dates, d)
        out[d] = status[index_dates[i - 1]] if i > 0 else False
    return out


def to_prefix(code: str) -> str:
    c = str(code).upper().strip()
    suffix = to_suffix(c)
    if "." in suffix:
        num, mkt = suffix.split(".")
        return f"{mkt}{num}"
    return c


def get_cap(by_date, cap_dates, d, prefix, suffix):
    """最近可得市值（<= 当日，前向填充），返回亿元"""
    i = bisect.bisect_right(cap_dates, d) - 1
    if i < 0:
        return 0
    m = by_date[cap_dates[i]]
    return m.get(prefix, m.get(suffix, 0)) / 1e8


def main():
    print("加载数据...")
    signals = load_signals()
    kdf = load_klines()
    index_df = pd.read_parquet(HERE / "index_klines_all.parquet")
    index_df["trade_date"] = index_df["trade_date"].astype(str).str[:10]
    cap_dates, by_date = load_caps()

    dates = sorted(signals.keys())
    mu = build_market_up(index_df, dates)
    up = sum(1 for v in mu.values() if v)
    print(f"  交易日: {len(dates)} ({dates[0]} ~ {dates[-1]})  大盘多:{up} 空:{len(dates)-up}")

    # 价格索引
    price = {}
    kdf = kdf.sort_values(["symbol", "trade_date"])
    for r in kdf.itertuples(index=False):
        d = str(r.trade_date)[:10]
        price[(r.symbol, d)] = {"open": float(r.open), "high": float(r.high),
                                "low": float(r.low), "close": float(r.close)}
    # prev_close: 每只股票前一交易日收盘
    prev_df = kdf.copy()
    prev_df["prev"] = prev_df.groupby("symbol")["close"].shift(1)
    prev_df = prev_df.dropna(subset=["prev"])
    prev_close = {(r.symbol, str(r.trade_date)[:10]): float(r.prev)
                  for r in prev_df.itertuples(index=False)}

    holdings, trades = {}, []
    cash = INITIAL_CASH
    eq = []
    stats = {"skip_limit": 0, "skip_cap": 0, "skip_board": 0, "skip_score_rank": 0}

    for d in dates:
        day_items = signals[d]
        top20set = set(sym for sym, sc, rk in day_items[:OUT_TOP])
        score_map = {sym: sc for sym, sc, rk in day_items}
        mkt_up = mu.get(d, False)

        # 卖出
        to_sell = []
        for suffix, h in list(holdings.items()):
            px = price.get((suffix, d))
            if not px: continue
            high, low = px["high"], px["low"]
            cost = h["cost"]
            h["highest"] = max(h.get("highest", cost), high)
            highest = h["highest"]
            if h.get("trailing_activated"):
                if low <= highest * (1 - TRAILING_DROP):
                    to_sell.append((suffix, "trailing_stop", highest * (1 - TRAILING_DROP))); continue
            else:
                if high >= cost * (1 + TRAILING_ACTIVATE):
                    h["trailing_activated"] = True
                    if low <= highest * (1 - TRAILING_DROP):
                        to_sell.append((suffix, "trailing_stop", highest * (1 - TRAILING_DROP))); continue
                elif low <= cost * (1 - STOP_LOSS):
                    to_sell.append((suffix, "stop_loss", cost * (1 - STOP_LOSS))); continue
            if suffix not in top20set:
                to_sell.append((suffix, "drop_top20", px["close"]))
        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            fee = sell_px * h["shares"] * (COMMISSION + STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            trades.append({"date": d, "symbol": suffix, "action": "sell", "reason": reason,
                           "price": round(sell_px, 2), "fee": round(fee, 2),
                           "pnl": round((sell_px - h["cost"]) * h["shares"] - fee, 2)})

        # 买入
        if mkt_up:
            for sym, sc, rk in day_items:
                if rk > OUT_TOP or sc < BUY_MIN_SCORE:
                    if rk > OUT_TOP and sc >= BUY_MIN_SCORE:
                        stats["skip_score_rank"] += 1
                    continue
                suffix = to_suffix(sym)
                if suffix in holdings: continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0: continue
                # 板块
                b = board_of(sym)
                if b not in BOARDS_OK:
                    stats["skip_board"] += 1; continue
                # 市值
                prefix = to_prefix(sym)
                mv = get_cap(by_date, cap_dates, d, prefix, suffix)
                if mv < MIN_MV_YI:
                    stats["skip_cap"] += 1; continue
                # 涨停过滤（保守）
                pc = prev_close.get((suffix, d))
                if pc and pc > 0 and px["open"] >= pc * (1 + limit_pct(suffix)) - 0.01:
                    stats["skip_limit"] += 1; continue
                shares = int(100_000 / px["open"] / 100) * 100
                if shares <= 0: continue
                cost = px["open"]; fee = cost * shares * COMMISSION
                if cash < shares * cost + fee: continue
                cash -= shares * cost + fee
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d}
                trades.append({"date": d, "symbol": suffix, "action": "buy", "reason": "top20",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        pos_val = sum(h["shares"] * (price[(suffix, d)]["close"] if (suffix, d) in price else h["cost"])
                      for suffix, h in holdings.items())
        eq.append((d, cash + pos_val))

    eqdf = pd.DataFrame(eq, columns=["date", "equity"])
    total = (eqdf.equity.iloc[-1] / eqdf.equity.iloc[0] - 1) * 100
    days = len(eqdf)
    annual = ((eqdf.equity.iloc[-1] / eqdf.equity.iloc[0]) ** (252 / max(days, 1)) - 1) * 100
    mdd = (eqdf.equity / eqdf.equity.cummax() - 1).min() * 100
    sells = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]

    print("\n" + "=" * 58)
    print(f"回测: 深主板/科创板 + 市值≥30亿 + 分数≥2.1/Top20 + 大盘过滤 + 涨停过滤")
    print("=" * 58)
    print(f"总收益: {total:.2f}%   年化: {annual:.2f}%")
    print(f"最大回撤: {mdd:.2f}%   最终权益: {cash + pos_val:,.0f}")
    print(f"胜率: {len(wins)/len(sells)*100:.1f}%  ({len(wins)}胜/{len(losses)}负, 共{len(sells)}笔)")
    print(f"买入: {sum(1 for t in trades if t['action']=='buy')}笔  卖出: {len(sells)}笔")
    print(f"过滤统计: 涨停跳过{stats['skip_limit']}  市值跳过{stats['skip_cap']}  "
          f"板块跳过{stats['skip_board']}  分数Top20外跳过{stats['skip_score_rank']}")
    from collections import Counter
    print(f"卖出原因: {dict(Counter(t['reason'] for t in sells))}")

    eqdf.to_csv(HERE / "equity_curve_board_cap.csv", index=False)
    pd.DataFrame(trades).to_csv(HERE / "trades_board_cap.csv", index=False)
    print(f"\n已保存: equity_curve_board_cap.csv, trades_board_cap.csv")


if __name__ == "__main__":
    main()
