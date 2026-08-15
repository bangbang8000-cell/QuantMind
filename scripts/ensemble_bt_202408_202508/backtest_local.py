"""融合模型动态止盈回测（本地数据版）

区间: 2024-08-02 ~ 2025-08-29（信号期 262 交易日）
策略:
  买入: 分数 >= BUY_MIN_SCORE (2.2) 且 大盘 MA20 多（T+1 开盘买入，无未来函数）
  止盈: 涨 +5% 后激活移动止盈，从最高点回撤 2% 卖出
  止损: -5%（未激活时）
  跌出: Top20 卖出
"""
import bisect
from pathlib import Path
import pandas as pd

import os
HERE = Path(os.environ.get("BT_DIR", Path(".").resolve()))
BUY_MIN_SCORE = 2.2
TOP_N = 10
OUT_TOP = 20
MA_WINDOW = 20
TRAILING_ACTIVATE = 0.05   # 激活: 涨 +5%
TRAILING_DROP = 0.02       # 回撤 2% 卖出
STOP_LOSS = 0.05           # 未激活时止损 -5%
COMMISSION = 0.0003
STAMP_TAX = 0.001
INITIAL_CASH = 1_000_000.0


def load_signals():
    df = pd.read_parquet(HERE / "signals.parquet")
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    out = {}
    for d, grp in df.groupby("trade_date"):
        grp = grp.sort_values("fusion_score", ascending=False).reset_index(drop=True)
        items = [(str(s), float(sc), i + 1) for i, (s, sc) in enumerate(
            zip(grp["symbol"], grp["fusion_score"]))]
        out[str(d)] = items
    return out


def load_klines():
    df = pd.read_parquet(HERE / "klines.parquet")
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    out = {}
    for suffix, grp in df.groupby("symbol"):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        out[suffix] = grp[["trade_date", "open", "high", "low", "close"]]
    return out


def load_index():
    df = pd.read_parquet(HERE / "index_klines.parquet")
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    return df.sort_values("trade_date").reset_index(drop=True)


def build_market_up(index_df, signal_dates, lookahead=False):
    """market_up[d] = 指数收盘 >= MA20（用 d 前一天收盘判断，避免未来函数）"""
    idx = index_df.copy()
    idx["ma20"] = idx["close"].rolling(MA_WINDOW).mean()
    status = {}
    for _, r in idx.iterrows():
        d = str(r["trade_date"])
        m = r["ma20"]
        if pd.notna(m) and m > 0:
            status[d] = bool(r["close"] >= m)
    index_dates = sorted(status.keys())
    out = {}
    if lookahead:
        for d in signal_dates:
            out[d] = status.get(d, False)
    else:
        for d in signal_dates:
            i = bisect.bisect_left(index_dates, d)
            out[d] = status[index_dates[i - 1]] if i > 0 else False
    return out


def to_suffix(code: str) -> str:
    code = str(code).upper().strip()
    if len(code) == 6 and code.isdigit():
        if code.startswith(("60", "68", "90")):
            return f"{code}.SH"
        if code.startswith(("00", "30", "20")):
            return f"{code}.SZ"
        if code.startswith(("83", "43", "87", "88", "92")):
            return f"{code}.BJ"
    return code


def run_backtest(signals, klines, market_up):
    # 只保留信号涉及的股票 K线（提速）
    needed = set()
    for items in signals.values():
        for sym, sc, rk in items[:OUT_TOP]:
            needed.add(to_suffix(sym))
    klines = {s: df for s, df in klines.items() if s in needed}
    print(f"  持仓/买入涉及股票: {len(needed)} 只")

    # 价格索引: (suffix, date) -> OHLC
    price = {}
    for suffix, df in klines.items():
        for _, row in df.iterrows():
            d = str(row["trade_date"])[:10]
            price[(suffix, d)] = {
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"])}

    dates = sorted(signals.keys())
    holdings = {}   # suffix -> {cost, shares, buy_date, highest, trailing_activated}
    trades = []
    equity_curve = []
    cash = INITIAL_CASH

    for d in dates:
        day_items = signals[d]
        top10 = [sym for sym, sc, rk in day_items[:TOP_N]]
        top20set = set(sym for sym, sc, rk in day_items[:OUT_TOP])
        score_map = {sym: sc for sym, sc, rk in day_items}
        market_up_d = market_up.get(d, False)

        # ── 卖出检查 ──
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
                if low <= highest * (1 - TRAILING_DROP):
                    to_sell.append((suffix, "trailing_stop", highest * (1 - TRAILING_DROP)))
                    continue
            else:
                if high >= cost * (1 + TRAILING_ACTIVATE):
                    h["trailing_activated"] = True
                    if low <= highest * (1 - TRAILING_DROP):
                        to_sell.append((suffix, "trailing_stop", highest * (1 - TRAILING_DROP)))
                        continue
                elif low <= cost * (1 - STOP_LOSS):
                    to_sell.append((suffix, "stop_loss", cost * (1 - STOP_LOSS)))
                    continue
            if suffix not in top20set:
                to_sell.append((suffix, "drop_top20", px["close"]))

        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            fee = sell_px * h["shares"] * (COMMISSION + STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            trades.append({"date": d, "symbol": suffix, "action": "sell", "reason": reason,
                           "price": round(sell_px, 2), "fee": round(fee, 2),
                           "pnl": round((sell_px - h["cost"]) * h["shares"] - fee, 2)})

        # ── 买入检查（大盘多才买, 开盘价, 分数≥阈值）──
        if market_up_d:
            candidates = [s for s, sc, rk in day_items if sc >= BUY_MIN_SCORE][:TOP_N]
            for sym in candidates:
                suffix = to_suffix(sym)
                if suffix in holdings:
                    continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0:
                    continue
                shares = int(100_000 / px["open"] / 100) * 100
                if shares <= 0:
                    continue
                cost = px["open"]
                fee = cost * shares * COMMISSION
                if cash < shares * cost + fee:
                    continue
                cash -= shares * cost + fee
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d}
                trades.append({"date": d, "symbol": suffix, "action": "buy", "reason": "top10",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        # ── 当日权益 ──
        pos_val = 0
        for suffix, h in holdings.items():
            px = price.get((suffix, d))
            pos_val += h["shares"] * (px["close"] if px else h["cost"])
        total = cash + pos_val
        equity_curve.append((d, total))

    eq = pd.DataFrame(equity_curve, columns=["date", "equity"])
    total_ret = (eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1) * 100
    days = len(eq)
    annual = ((eq["equity"].iloc[-1] / eq["equity"].iloc[0]) ** (252 / max(days, 1)) - 1) * 100
    max_dd = (eq["equity"] / eq["equity"].cummax() - 1).min() * 100

    sells = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]
    win_rate = len(wins) / len(sells) * 100 if sells else 0

    return {
        "equity_curve": eq, "trades": trades,
        "total_return_pct": round(total_ret, 2), "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(max_dd, 2), "win_rate_pct": round(win_rate, 1),
        "n_sells": len(sells), "n_wins": len(wins), "n_losses": len(losses),
        "final_equity": round(float(eq["equity"].iloc[-1]), 2),
        "market_up_days": sum(1 for v in market_up.values() if v),
        "market_down_days": sum(1 for v in market_up.values() if not v),
    }


def print_result(label, r):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print(f"总收益: {r['total_return_pct']}%   年化: {r['annual_return_pct']}%")
    print(f"最大回撤: {r['max_drawdown_pct']}%   最终权益: {r['final_equity']:,.0f}")
    print(f"胜率: {r['win_rate_pct']}%  ({r['n_wins']}胜/{r['n_losses']}负, 共{r['n_sells']}笔)")
    print(f"大盘多:{r['market_up_days']}天  空:{r['market_down_days']}天")


def main():
    print("加载本地数据...")
    signals = load_signals()
    print(f"  信号交易日: {len(signals)}  ({min(signals)} ~ {max(signals)})")
    klines = load_klines()
    index_df = load_index()

    # 无未来函数（用前一天指数判断）
    print("计算大盘 MA20 过滤（前一日收盘判断，无未来函数）...")
    mu = build_market_up(index_df, sorted(signals.keys()), lookahead=False)
    print(f"  大盘多: {sum(1 for v in mu.values() if v)} 空: {sum(1 for v in mu.values() if not v)}")
    r1 = run_backtest(signals, klines, mu)
    print_result("策略: 分数≥2.2 + 大盘MA20多 + 激活5%/回撤2% + 止损5% + 跌出Top20", r1)

    # 对比: 当日收盘判断（原脚本口径，含1日未来函数）
    mu_l = build_market_up(index_df, sorted(signals.keys()), lookahead=True)
    r2 = run_backtest(signals, klines, mu_l)
    print_result("[对比] 大盘当日收盘判断（原脚本口径）", r2)

    # 卖出原因分布
    from collections import Counter
    c = Counter(t["reason"] for t in r1["trades"] if t["action"] == "sell")
    print("\n卖出原因分布（主策略）:", dict(c))

    # 保存
    r1["equity_curve"].to_csv(HERE / "equity_curve.csv", index=False)
    pd.DataFrame(r1["trades"]).to_csv(HERE / "trades.csv", index=False)
    print(f"\n已保存: {HERE / 'equity_curve.csv'} , {HERE / 'trades.csv'}")


if __name__ == "__main__":
    main()
