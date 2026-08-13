"""回测对比：无过滤 vs 涨停过滤（买入日开盘≥涨停价 → 买不进跳过）"""
import importlib.util
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bl", HERE / "backtest_local.py")
bl = importlib.util.module_from_spec(spec)
import os
os.environ["BT_DIR"] = str(HERE)
spec.loader.exec_module(bl)


def limit_pct(suffix: str) -> float:
    if suffix.startswith(("30", "68")):
        return 0.20
    if suffix.startswith(("83", "43", "87", "88", "92")):
        return 0.30
    return 0.10


def build_prev_close() -> dict:
    kdf = pd.read_parquet(HERE / "klines.parquet")
    kdf["trade_date"] = kdf["trade_date"].astype(str).str[:10]
    kdf = kdf.sort_values(["symbol", "trade_date"])
    kdf["prev_close"] = kdf.groupby("symbol")["close"].shift(1)
    return {(r.symbol, r.trade_date): r.prev_close for r in kdf.itertuples()}


def run(filters: dict) -> dict:
    signals = bl.load_signals()
    klines = bl.load_klines()
    index_df = bl.load_index()
    mu = bl.build_market_up(index_df, sorted(signals.keys()), lookahead=False)
    prev_close = build_prev_close()
    filter_limit_up = filters.get("limit_up", False)

    needed = set()
    for items in signals.values():
        for sym, sc, rk in items[:bl.OUT_TOP]:
            needed.add(bl.to_suffix(sym))
    klines = {s: df for s, df in klines.items() if s in needed}

    price = {}
    for suffix, df in klines.items():
        for _, row in df.iterrows():
            d = str(row["trade_date"])[:10]
            price[(suffix, d)] = {"open": float(row["open"]), "high": float(row["high"]),
                                  "low": float(row["low"]), "close": float(row["close"])}

    dates = sorted(signals.keys())
    holdings, trades, eq = {}, [], []
    cash = bl.INITIAL_CASH
    skipped_limit = 0

    for d in dates:
        day_items = signals[d]
        top20set = set(sym for sym, sc, rk in day_items[:bl.OUT_TOP])
        market_up_d = mu.get(d, False)

        to_sell = []
        for suffix, h in list(holdings.items()):
            px = price.get((suffix, d))
            if not px:
                continue
            high, low = px["high"], px["low"]
            cost = h["cost"]
            h["highest"] = max(h.get("highest", cost), high)
            highest = h["highest"]
            if h.get("trailing_activated"):
                if low <= highest * (1 - bl.TRAILING_DROP):
                    to_sell.append((suffix, "trailing_stop", highest * (1 - bl.TRAILING_DROP))); continue
            else:
                if high >= cost * (1 + bl.TRAILING_ACTIVATE):
                    h["trailing_activated"] = True
                    if low <= highest * (1 - bl.TRAILING_DROP):
                        to_sell.append((suffix, "trailing_stop", highest * (1 - bl.TRAILING_DROP))); continue
                elif low <= cost * (1 - bl.STOP_LOSS):
                    to_sell.append((suffix, "stop_loss", cost * (1 - bl.STOP_LOSS))); continue
            if suffix not in top20set:
                to_sell.append((suffix, "drop_top20", px["close"]))

        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            fee = sell_px * h["shares"] * (bl.COMMISSION + bl.STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            trades.append({"date": d, "symbol": suffix, "action": "sell", "reason": reason,
                           "price": round(sell_px, 2), "fee": round(fee, 2),
                           "pnl": round((sell_px - h["cost"]) * h["shares"] - fee, 2)})

        if market_up_d:
            candidates = [s for s, sc, rk in day_items if sc >= bl.BUY_MIN_SCORE][:bl.TOP_N]
            for sym in candidates:
                suffix = bl.to_suffix(sym)
                if suffix in holdings:
                    continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0:
                    continue
                if filter_limit_up:
                    pc = prev_close.get((suffix, d))
                    if pc and pd.notna(pc) and pc > 0:
                        if px["open"] >= pc * (1 + limit_pct(suffix)) - 0.01:
                            skipped_limit += 1
                            continue
                shares = int(100_000 / px["open"] / 100) * 100
                if shares <= 0:
                    continue
                cost = px["open"]
                fee = cost * shares * bl.COMMISSION
                if cash < shares * cost + fee:
                    continue
                cash -= shares * cost + fee
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d}
                trades.append({"date": d, "symbol": suffix, "action": "buy", "reason": "top10",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        pos_val = 0
        for suffix, h in holdings.items():
            px = price.get((suffix, d))
            pos_val += h["shares"] * (px["close"] if px else h["cost"])
        eq.append((d, cash + pos_val))

    eqdf = pd.DataFrame(eq, columns=["date", "equity"])
    tot = (eqdf.equity.iloc[-1] / eqdf.equity.iloc[0] - 1) * 100
    ann = ((eqdf.equity.iloc[-1] / eqdf.equity.iloc[0]) ** (252 / max(len(eqdf), 1)) - 1) * 100
    mdd = (eqdf.equity / eqdf.equity.cummax() - 1).min() * 100
    sells = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sells if t["pnl"] > 0]
    return {
        "total": round(tot, 2), "annual": round(ann, 2), "mdd": round(mdd, 2),
        "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else 0,
        "n_buys": sum(1 for t in trades if t["action"] == "buy"),
        "n_sells": len(sells), "skipped": skipped_limit,
        "final": round(float(eqdf.equity.iloc[-1]), 2),
    }


if __name__ == "__main__":
    r0 = run({"limit_up": False})
    r1 = run({"limit_up": True})
    print("=" * 58)
    print(f"{'指标':<10}{'无过滤':>12}{'涨停过滤':>14}")
    print("=" * 58)
    for k, label in [("total", "总收益%"), ("annual", "年化%"), ("mdd", "最大回撤%"),
                     ("win_rate", "胜率%"), ("n_buys", "买入笔数"), ("n_sells", "卖出笔数"),
                     ("final", "最终权益")]:
        print(f"{label:<10}{r0[k]:>12,}{r1[k]:>14,}")
    print(f"\n涨停过滤跳过买入(买不进): {r1['skipped']} 次")
