"""策略回测详细导出：分数≥2.2买入 + 动态止盈(5%/2%) + 止损5% + 分数退出

区间: 2026-08-05 ~ 2026-08-12
卖出模式: score(分数<2.1卖) / top20(跌出Top20卖) / pure(只止盈止损)
导出到 scripts/ensemble_bt_202408_202508/:
  - trades_{mode}.csv            完整买卖明细(含分数/排名/持仓天数/盈亏)
  - pnl_{mode}.csv               每笔已实现盈亏(买入->卖出闭环)
  - positions_{mode}.csv         每日持仓快照(每只: 成本/现价/浮盈%/分数/排名)
  - equity_{mode}.csv            每日权益曲线
  - daily_summary_{mode}.csv     每日汇总(持仓数/现金/权益/买入卖出数)
"""
from pathlib import Path
import bisect
import pandas as pd

HERE = Path(__file__).resolve().parent
BUY_MIN_SCORE = 2.2
SELL_SCORE_LOW = 2.1
OUT_TOP = 20
MA_WINDOW = 20
TRAILING_ACTIVATE = 0.05
TRAILING_DROP = 0.02
STOP_LOSS = 0.05
COMMISSION = 0.0003
STAMP_TAX = 0.001
INITIAL_CASH = 1_000_000.0
POS_SIZE = 100_000
MAX_HOLDINGS = 20
SUFFICIENT_CASH = True   # True: 资金充足(1000万/50万/100只)，验证满仓效果
START_DATE = "2026-08-05"
END_DATE = "2026-08-12"

if SUFFICIENT_CASH:
    INITIAL_CASH = 10_000_000.0
    POS_SIZE = 50_000
    MAX_HOLDINGS = 200


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
        out[str(d)] = [(str(s), float(sc), i + 1) for i, (s, sc) in enumerate(
            zip(grp["symbol"], grp["fusion_score"]))]
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


def run(seil_mode: str) -> dict:
    print(f"\n===== 运行变体 {seil_mode} =====")
    signals = load_signals()
    kdf = pd.read_parquet(HERE / "klines_all.parquet")
    kdf["trade_date"] = kdf["trade_date"].astype(str).str[:10]
    index_df = pd.read_parquet(HERE / "index_klines_all.parquet")
    index_df["trade_date"] = index_df["trade_date"].astype(str).str[:10]

    dates = sorted(d for d in signals.keys() if START_DATE <= d <= END_DATE)
    mu = build_market_up(index_df, dates)
    print(f"  交易日: {dates[0]} ~ {dates[-1]}  共{len(dates)}天  大盘多:{sum(1 for v in mu.values() if v)}")

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
    eq, hcnt = [], []
    pos_snapshots = []  # 每日持仓快照
    daily_rows = []     # 每日汇总
    stats = {"skip_limit": 0, "skip_cash": 0, "exit_score": 0, "exit_top20": 0}

    for d in dates:
        day_items = signals[d]
        top20set = set(sym for sym, sc, rk in day_items[:OUT_TOP])
        score_map = {sym: sc for sym, sc, rk in day_items}
        rank_map = {sym: rk for sym, sc, rk in day_items}
        mkt_up = mu.get(d, False)

        # ── 卖出（hold 模式：一直持有到期末不卖）──
        to_sell = []
        if seil_mode != "hold":
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
                if seil_mode == "score":
                    sc = score_map.get(h["raw_sym"], score_map.get(suffix, 0))
                    if sc < SELL_SCORE_LOW:
                        to_sell.append((suffix, "score_low", px["close"])); stats["exit_score"] += 1; continue
                elif seil_mode == "top20":
                    if h["raw_sym"] not in top20set:
                        to_sell.append((suffix, "out_top20", px["close"])); stats["exit_top20"] += 1; continue
                # pure 模式：只止盈止损，无分数退出

        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            fee = sell_px * h["shares"] * (COMMISSION + STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            pnl = (sell_px - h["cost"]) * h["shares"] - fee
            holding_days = len([x for x in dates if h["buy_date"] <= x <= d])
            sell_score = score_map.get(h["raw_sym"], score_map.get(suffix, 0))
            sell_rank = rank_map.get(h["raw_sym"], rank_map.get(suffix, 0))
            trades.append({"date": d, "action": "sell", "symbol": suffix, "code": h["raw_sym"],
                           "reason": reason, "buy_date": h["buy_date"], "holding_days": holding_days,
                           "cost": round(h["cost"], 2), "sell_price": round(sell_px, 2),
                           "shares": h["shares"], "buy_score": round(h["buy_score"], 3),
                           "sell_score": round(sell_score, 3), "buy_rank": h["buy_rank"],
                           "sell_rank": int(sell_rank) if sell_rank else None,
                           "highest": round(h.get("highest", h["cost"]), 2),
                           "fee": round(fee, 2), "pnl": round(pnl, 2),
                           "pnl_pct": round(pnl / (h["cost"] * h["shares"]) * 100, 2)})

        # ── 买入 ──
        if mkt_up:
            cands = [s for s, sc, rk in day_items if sc >= BUY_MIN_SCORE]
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
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d,
                                    "raw_sym": sym, "buy_score": score_map.get(sym, 0),
                                    "buy_rank": rank_map.get(sym, 0)}
                trades.append({"date": d, "action": "buy", "symbol": suffix, "code": sym,
                               "reason": "score", "buy_date": d, "holding_days": 0,
                               "cost": round(cost, 2), "sell_price": None,
                               "shares": shares, "buy_score": round(score_map.get(sym, 0), 3),
                               "sell_score": None, "buy_rank": rank_map.get(sym, 0),
                               "sell_rank": None, "highest": round(cost, 2),
                               "fee": round(fee, 2), "pnl": 0, "pnl_pct": 0})

        # ── 当日持仓快照 ──
        for suffix, h in holdings.items():
            px = price.get((suffix, d))
            close = px["close"] if px else h["cost"]
            unrel = (close - h["cost"]) / h["cost"] * 100
            sc = score_map.get(h["raw_sym"], score_map.get(suffix, 0))
            rk = rank_map.get(h["raw_sym"], rank_map.get(suffix, 0))
            pos_snapshots.append({
                "date": d, "code": h["raw_sym"], "symbol": suffix,
                "buy_date": h["buy_date"], "cost": round(h["cost"], 2), "close": round(close, 2),
                "unrealized_pct": round(unrel, 2), "shares": h["shares"],
                "score": round(sc, 3), "rank": int(rk) if rk else None,
                "buy_score": round(h["buy_score"], 3), "buy_rank": h["buy_rank"],
                "trailing_activated": h.get("trailing_activated", False),
                "highest": round(h.get("highest", h["cost"]), 2)})

        pos_val = sum(h["shares"] * (price[(suffix, d)]["close"] if (suffix, d) in price else h["cost"])
                      for suffix, h in holdings.items())
        total = cash + pos_val
        hcnt.append(len(holdings))
        eq.append((d, total))
        n_buy_d = sum(1 for t in trades if t["action"] == "buy" and t["date"] == d)
        n_sell_d = sum(1 for t in trades if t["action"] == "sell" and t["date"] == d)
        daily_rows.append({"date": d, "cash": round(cash, 2), "pos_value": round(pos_val, 2),
                           "equity": round(total, 2), "n_holdings": len(holdings),
                           "n_buy": n_buy_d, "n_sell": n_sell_d, "market_up": mkt_up})

    eqdf = pd.DataFrame(eq, columns=["date", "equity"])
    total = (eqdf.equity.iloc[-1] / eqdf.equity.iloc[0] - 1) * 100
    days = len(eqdf)
    annual = ((eqdf.equity.iloc[-1] / eqdf.equity.iloc[0]) ** (252 / max(days, 1)) - 1) * 100
    mdd = (eqdf.equity / eqdf.equity.cummax() - 1).min() * 100
    sells = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]

    # 盈亏明细（买入->卖出闭环）
    pnl_rows = []
    buy_map = {t["symbol"]: t for t in trades if t["action"] == "buy"}
    for s in sells:
        b = buy_map.get(s["symbol"], {})
        pnl_rows.append({
            "sell_date": s["date"], "code": s["code"], "symbol": s["symbol"],
            "buy_date": s["buy_date"], "holding_days": s["holding_days"],
            "cost": s["cost"], "sell_price": s["sell_price"], "shares": s["shares"],
            "buy_score": s["buy_score"], "sell_score": s["sell_score"],
            "buy_rank": s["buy_rank"], "sell_rank": s["sell_rank"],
            "highest": s["highest"], "reason": s["reason"],
            "fee": s["fee"], "pnl": s["pnl"], "pnl_pct": s["pnl_pct"],
            "is_win": s["pnl"] > 0})

    from collections import Counter
    from statistics import mean
    return {"mode": seil_mode, "equity": eqdf, "trades": trades, "pnl": pnl_rows,
            "positions": pos_snapshots, "daily": daily_rows,
            "total": round(total, 2), "annual": round(annual, 2), "mdd": round(mdd, 2),
            "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else 0,
            "n_buys": sum(1 for t in trades if t["action"] == "buy"), "n_sells": len(sells),
            "n_wins": len(wins), "n_losses": len(losses),
            "final": round(float(eqdf.equity.iloc[-1]), 2),
            "avg_hold": round(mean(hcnt), 1), "max_hold": max(hcnt),
            "reasons": dict(Counter(t["reason"] for t in sells)),
            "stats": stats}


def print_r(r):
    print(f"\n===== 变体 {r['mode']} =====")
    print(f"总收益: {r['total']}%   年化: {r['annual']}%   最大回撤: {r['mdd']}%")
    print(f"最终权益: {r['final']:,.0f}   胜率: {r['win_rate']}% ({r['n_wins']}胜/{r['n_losses']}负/共{r['n_sells']}笔)")
    print(f"买入{r['n_buys']}笔  平均持仓{r['avg_hold']}只(最大{r['max_hold']})")
    print(f"卖出原因: {r['reasons']}")
    print(f"过滤: 涨停跳过{r['stats']['skip_limit']}  现金不足{r['stats']['skip_cash']}")


if __name__ == "__main__":
    for mode in ["score", "top20", "pure", "hold"]:
        r = run(mode)
        print_r(r)
        pd.DataFrame(r["trades"]).to_csv(HERE / f"trades_{mode}.csv", index=False)
        pd.DataFrame(r["pnl"]).to_csv(HERE / f"pnl_{mode}.csv", index=False)
        pd.DataFrame(r["positions"]).to_csv(HERE / f"positions_{mode}.csv", index=False)
        r["equity"].to_csv(HERE / f"equity_{mode}.csv", index=False)
        pd.DataFrame(r["daily"]).to_csv(HERE / f"daily_summary_{mode}.csv", index=False)
        print(f"  已导出 {mode}: trades/pnl/positions/equity/daily_summary")
