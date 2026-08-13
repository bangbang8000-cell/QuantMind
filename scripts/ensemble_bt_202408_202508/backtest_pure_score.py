"""纯分数策略回测：不限市值/不限Top20，严格止盈止损

区间: 2024-08-12 ~ 2026-08-12
买入: 分数 >= 2.1，大盘 MA20 多（前一日判断，无未来函数），T+1开盘买入
      涨停过滤: 开盘>=涨停价跳过（保守）
不设: 市值门槛、板块限制、Top20 排名限制、跌出Top20不卖
卖出: 动态止盈(激活+5%/回撤2%) + 止损-5%，严格
      （不因跌出Top20卖出）
初始: 100万
"""
from pathlib import Path
import bisect
import pandas as pd

HERE = Path(__file__).resolve().parent
BUY_MIN_SCORE = 2.1
MA_WINDOW = 20
TRAILING_ACTIVATE = 0.05
TRAILING_DROP = 0.02
STOP_LOSS = 0.05
COMMISSION = 0.0003
STAMP_TAX = 0.001
INITIAL_CASH = 1_000_000.0
MAX_HOLDINGS = 20   # 单一持仓上限，防止候选过多过度分散
POS_SIZE = 100_000  # 每只约10万


def to_suffix(code: str) -> str:
    c = str(code).upper().strip()
    if len(c) == 6 and c.isdigit():
        if c.startswith(("60", "68", "90")): return f"{c}.SH"
        if c.startswith(("00", "30", "20")): return f"{c}.SZ"
        if c.startswith(("83", "43", "87", "88", "92")): return f"{c}.BJ"
    return c


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
        out[str(d)] = [(str(s), float(sc)) for s, sc in zip(grp["symbol"], grp["fusion_score"])]
    return out


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


def main():
    print("加载数据...")
    signals = load_signals()
    kdf = pd.read_parquet(HERE / "klines_all.parquet")
    kdf["trade_date"] = kdf["trade_date"].astype(str).str[:10]
    index_df = pd.read_parquet(HERE / "index_klines_all.parquet")
    index_df["trade_date"] = index_df["trade_date"].astype(str).str[:10]

    dates = sorted(signals.keys())
    mu = build_market_up(index_df, dates)
    print(f"  交易日: {len(dates)} ({dates[0]} ~ {dates[-1]})  大盘多:{sum(1 for v in mu.values() if v)}")

    price = {}
    kdf = kdf.sort_values(["symbol", "trade_date"])
    for r in kdf.itertuples(index=False):
        d = str(r.trade_date)[:10]
        price[(r.symbol, d)] = {"open": float(r.open), "high": float(r.high),
                                "low": float(r.low), "close": float(r.close)}
    prev_df = kdf.copy()
    prev_df["prev"] = prev_df.groupby("symbol")["close"].shift(1)
    prev_df = prev_df.dropna(subset=["prev"])
    prev_close = {(r.symbol, str(r.trade_date)[:10]): float(r.prev)
                  for r in prev_df.itertuples(index=False)}

    holdings, trades = {}, []
    cash = INITIAL_CASH
    eq = []
    holdings_count = []
    stats = {"skip_limit": 0, "skip_cash": 0}

    for d in dates:
        day_items = signals[d]
        mkt_up = mu.get(d, False)

        # 卖出: 只按止盈止损（不因跌出Top20卖）
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
        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            fee = sell_px * h["shares"] * (COMMISSION + STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            trades.append({"date": d, "symbol": suffix, "action": "sell", "reason": reason,
                           "price": round(sell_px, 2), "fee": round(fee, 2),
                           "pnl": round((sell_px - h["cost"]) * h["shares"] - fee, 2)})

        # 买入: 分数>=2.1 全部，大盘多才买
        if mkt_up:
            cands = [s for s, sc in day_items if sc >= BUY_MIN_SCORE]
            for sym in cands:
                if len(holdings) >= MAX_HOLDINGS: break
                suffix = to_suffix(sym)
                if suffix in holdings: continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0: continue
                pc = prev_close.get((suffix, d))
                if pc and pc > 0 and px["open"] >= pc * (1 + limit_pct(suffix)) - 0.01:
                    stats["skip_limit"] += 1; continue
                shares = int(POS_SIZE / px["open"] / 100) * 100
                if shares <= 0: continue
                cost = px["open"]; fee = cost * shares * COMMISSION
                if cash < shares * cost + fee:
                    stats["skip_cash"] += 1; continue
                cash -= shares * cost + fee
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d}
                trades.append({"date": d, "symbol": suffix, "action": "buy", "reason": "score",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        pos_val = sum(h["shares"] * (price[(suffix, d)]["close"] if (suffix, d) in price else h["cost"])
                      for suffix, h in holdings.items())
        holdings_count.append(len(holdings))
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
    print("纯分数策略: 分数≥2.1 全买 + 大盘过滤 + 严格止盈止损 (不限市值/Top20)")
    print("=" * 58)
    print(f"总收益: {total:.2f}%   年化: {annual:.2f}%")
    print(f"最大回撤: {mdd:.2f}%   最终权益: {cash + pos_val:,.0f}")
    print(f"胜率: {len(wins)/len(sells)*100:.1f}%  ({len(wins)}胜/{len(losses)}负, 共{len(sells)}笔)")
    print(f"买入: {sum(1 for t in trades if t['action']=='buy')}笔  卖出: {len(sells)}笔")
    print(f"过滤: 涨停跳过{stats['skip_limit']}  现金不足跳过{stats['skip_cash']}")
    from collections import Counter
    from statistics import mean
    print(f"卖出原因: {dict(Counter(t['reason'] for t in sells))}")
    print(f"平均持仓数: {mean(holdings_count):.1f}  最大: {max(holdings_count)}")

    eqdf.to_csv(HERE / "equity_curve_pure_score.csv", index=False)
    pd.DataFrame(trades).to_csv(HERE / "trades_pure_score.csv", index=False)
    print(f"\n已保存: equity_curve_pure_score.csv, trades_pure_score.csv")


if __name__ == "__main__":
    main()
