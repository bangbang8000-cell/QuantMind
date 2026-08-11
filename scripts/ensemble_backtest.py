"""融合模型策略回测：前10买入 + MA20大盘过滤 + 止盈止损

策略规则（用户定义）：
1. 每日收盘取模型分数 Top10 作为候选
2. T+1 开盘买入：仅当大盘多（上证指数 >= MA20）时才买入
3. 持仓每日检查（盘中价触发）：
   - 盘中 high >= 成本 × 1.08  → +8% 止盈卖出
   - 盘中 low  <= 成本 × 0.95  → -5% 止损卖出
   - 当日分数跌出 Top20       → 卖出
4. 滚动：每天买入新入选的 Top10，卖出触发止盈止损/跌出前20的
5. 大盘空（上证 < MA20）时不新开仓，但持仓按止盈止损正常管理

输出：逐日持仓、交易记录、收益曲线、年化/最大回撤等统计。
"""
import sys
from datetime import date
from pathlib import Path
from collections import defaultdict

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL_ID = "mdl_cn_ensemble_20260811112341_3d65b4c1"
TOP_N = 10
TAKE_PROFIT = 0.08   # +8% 止盈
STOP_LOSS = 0.05     # -5% 止损
OUT_TOP = 20         # 跌出前20卖出
MA_WINDOW = 20
COMMISSION = 0.0003  # 佣金 万3
STAMP_TAX = 0.001    # 印花税 0.1%（卖出）

from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub
from backend.shared.database_manager_v2 import get_session
from backend.shared.stock_utils import StockCodeUtil
from sqlalchemy import text


def load_signals() -> dict[str, list[tuple[str, float, int]]]:
    """加载该模型全部信号: trade_date -> [(symbol, score, rank)]"""
    import asyncio

    async def _load():
        async with get_session(read_only=True) as s:
            res = await s.execute(text("""
                SELECT trade_date, symbol, fusion_score
                FROM engine_signal_scores
                WHERE run_id IN (SELECT run_id FROM qm_model_inference_runs
                                 WHERE model_id=:mid AND status='completed')
                ORDER BY trade_date, fusion_score DESC
            """), {"mid": MODEL_ID})
            rows = res.fetchall()  # 一次性取回，避免逐行迭代慢
        # pandas 高效分组
        df = pd.DataFrame(rows, columns=["trade_date", "symbol", "score"])
        out: dict[str, list[tuple[str, float, int]]] = {}
        for d, grp in df.groupby("trade_date"):
            grp = grp.reset_index(drop=True)
            items = [(str(s).upper(), float(sc), i + 1)
                     for i, (s, sc) in enumerate(zip(grp["symbol"], grp["score"]))]
            out[str(d)] = items
        return out
    return asyncio.run(_load())


def load_klines(all_symbols: set[str]) -> dict[str, pd.DataFrame]:
    """用 Arrow filters 高效读取 K线（只读信号涉及的股票，下推过滤）。"""
    import pyarrow.parquet as pq
    import os

    data_root = Path(os.getenv("QM_QUANTDB_DATA_DIR", "/data/quantdb"))
    daily_dir = data_root / "1_kline_data" / "daily_unadjusted"
    suffix_list = sorted(StockCodeUtil.to_suffix(s) for s in all_symbols)

    # 收集 2025-07 ~ 2026-08 的分区文件
    partitions = []
    for p in sorted(daily_dir.glob("dt=2025*")):
        if int(str(p.name)[3:]) >= 202507:
            partitions.append(p / "data.parquet")
    for p in sorted(daily_dir.glob("dt=2026*")):
        partitions.append(p / "data.parquet")

    # 用 filters 下推，只读需要的股票
    filters = [("symbol", "in", suffix_list)]
    all_dfs = []
    for f in partitions:
        try:
            t = pq.read_table(f, columns=["symbol", "time", "open", "high", "low", "close"],
                              filters=filters)
            if t.num_rows > 0:
                all_dfs.append(t.to_pandas())
        except Exception:
            continue

    if not all_dfs:
        return {}
    full = pd.concat(all_dfs, ignore_index=True)
    full = full.rename(columns={"time": "trade_date"})
    full["trade_date"] = full["trade_date"].astype(str).str[:10]
    full = full[(full["trade_date"] >= "2025-07-01") & (full["trade_date"] <= "2026-08-10")]

    klines = {}
    for suffix, grp in full.groupby("symbol"):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        klines[suffix] = grp[["trade_date", "open", "high", "low", "close"]]
    return klines


def load_index_ma20() -> dict[str, bool]:
    """上证指数每日是否 >= MA20（大盘多）"""
    hub = QuantDBDataHub()
    df = hub.fetch_index_kline("000001.SH", date(2025, 6, 1), date(2026, 8, 10))
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["ma20"] = df["close"].rolling(MA_WINDOW).mean()
    out = {}
    for _, row in df.iterrows():
        d = str(row["trade_date"])[:10]
        c = float(row["close"])
        m = row["ma20"]
        if pd.notna(m) and m > 0:
            out[d] = bool(c >= m)
    return out


def backtest(signals, klines, index_ma, buy_min_score: float = 0.0, sell_below_score: float = 0.0,
             board_cap_filter: dict | None = None, caps: dict | None = None,
             trailing_activate: float = 0.08, trailing_drop: float = 0.03) -> dict:
    """board_cap_filter: {'boards': set, 'caps': set} 只买指定板块+市值；caps 为市值映射
    trailing_activate: 涨到成本+该比例后激活移动止盈；trailing_drop: 从最高点回撤该比例卖出"""
    def _board_of(code: str) -> str:
        if code.startswith('688'): return '科创板'
        if code.startswith('30'): return '创业板'
        if code.startswith('00') or code.startswith('002') or code.startswith('003'): return '深主板'
        if code.startswith('60'): return '沪主板'
        return '其他'
    def _cap_of(mv_yi: float) -> str:
        if mv_yi < 30: return '微盘'
        if mv_yi < 100: return '小盘'
        if mv_yi < 300: return '中盘'
        if mv_yi < 1000: return '大盘'
        return '超大盘'
    dates = sorted(signals.keys())
    # 价格索引: (suffix, date) -> dict(open, high, low, close)
    price = {}
    for suffix, df in klines.items():
        for _, row in df.iterrows():
            d = str(row["trade_date"])[:10]
            price[(suffix, d)] = {
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
            }

    holdings: dict[str, dict] = {}  # suffix -> {cost, shares, buy_date}
    trades = []
    equity_curve = []
    cash = 1_000_000.0
    position_value = 0.0
    daily_positions = {}

    for i, d in enumerate(dates):
        day_items = signals[d]
        top10 = [sym for sym, sc, rk in day_items[:TOP_N]]
        top20set = set(sym for sym, sc, rk in day_items[:OUT_TOP])
        score_map = {sym: sc for sym, sc, rk in day_items}
        market_up = index_ma.get(d, False)

        # ── 卖出检查（动态止盈 + 止损）──
        to_sell = []
        for suffix, h in list(holdings.items()):
            px = price.get((suffix, d))
            if not px:
                continue
            high, low = px["high"], px["low"]
            cost = h["cost"]
            # 更新持仓最高价
            h["highest"] = max(h.get("highest", cost), px["high"])
            highest = h["highest"]
            if h.get("trailing_activated"):
                # 已激活：从最高点回撤 trailing_drop 卖出（锁利润）
                if low <= highest * (1 - trailing_drop):
                    to_sell.append((suffix, "trailing_stop", highest * (1 - trailing_drop)))
                    continue
            else:
                # 未激活：涨到成本*(1+activate) 后激活移动止盈
                if high >= cost * (1 + trailing_activate):
                    h["trailing_activated"] = True
                    if low <= highest * (1 - trailing_drop):
                        to_sell.append((suffix, "trailing_stop", highest * (1 - trailing_drop)))
                        continue
                elif low <= cost * (1 - STOP_LOSS):
                    to_sell.append((suffix, "stop_loss", cost * (1 - STOP_LOSS)))
                    continue
            if sell_below_score > 0 and score_map.get(suffix, 0) < sell_below_score:
                to_sell.append((suffix, "below_score", px["close"]))
            elif suffix not in top20set:
                to_sell.append((suffix, "drop_top20", px["close"]))
        for suffix, reason, sell_px in to_sell:
            h = holdings.pop(suffix)
            # 卖出成本: 佣金 + 印花税
            fee = sell_px * h["shares"] * (COMMISSION + STAMP_TAX)
            cash += h["shares"] * sell_px - fee
            trades.append({"date": d, "symbol": suffix, "action": "sell", "reason": reason,
                           "price": round(sell_px, 2), "fee": round(fee, 2),
                           "pnl": round((sell_px - h["cost"]) * h["shares"] - fee, 2)})

        # ── 买入检查（大盘多才买，买入价用当日开盘；分数 ≥ buy_min_score）──
        if market_up:
            # 当日分数 ≥ 阈值的股票（从高到低取前TOP_N）
            candidates = [s for s, sc, rk in day_items if sc >= buy_min_score][:TOP_N]
            # 板块/市值过滤（可选）
            if board_cap_filter and caps:
                boards_ok = board_cap_filter.get("boards")
                caps_ok = board_cap_filter.get("caps")
                filtered = []
                for sym in candidates:
                    if boards_ok:
                        b = _board_of(sym)
                        if b not in boards_ok:
                            continue
                    if caps_ok:
                        suffix = StockCodeUtil.to_suffix(sym)
                        prefix = StockCodeUtil.to_prefix(sym)
                        mv = caps.get(prefix, caps.get(suffix, 0)) / 1e8
                        cap = _cap_of(mv) if mv > 0 else "未知"
                        if cap not in caps_ok:
                            continue
                    filtered.append(sym)
                candidates = filtered
            for sym in candidates:
                suffix = StockCodeUtil.to_suffix(sym)
                if suffix in holdings:
                    continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0:
                    continue
                shares = int(100_000 / px["open"] / 100) * 100  # 每只约10万，整手
                if shares <= 0:
                    continue
                cost = px["open"]
                # 买入成本: 佣金
                fee = cost * shares * COMMISSION
                if cash < shares * cost + fee:
                    continue
                cash -= shares * cost + fee
                holdings[suffix] = {"cost": cost, "shares": shares, "buy_date": d}
                trades.append({"date": d, "symbol": suffix, "action": "buy", "reason": "top10",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        # ── 当日市值 ──
        pos_val = 0
        for suffix, h in list(holdings.items()):
            px = price.get((suffix, d))
            if px:
                pos_val += h["shares"] * px["close"]
            else:
                # 无当日价，用成本
                pos_val += h["shares"] * h["cost"]
        total = cash + pos_val
        position_value = pos_val
        daily_positions[d] = {"cash": round(cash, 2), "pos": round(pos_val, 2),
                              "total": round(total, 2), "n": len(holdings), "market_up": market_up}
        equity_curve.append((d, total))

    # 统计
    eq = pd.DataFrame(equity_curve, columns=["date", "equity"])
    eq["ret"] = eq["equity"].pct_change()
    total_ret = (eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1) * 100
    days = len(eq)
    annual = ((eq["equity"].iloc[-1] / eq["equity"].iloc[0]) ** (252 / max(days, 1)) - 1) * 100
    max_dd = (eq["equity"] / eq["equity"].cummax() - 1).min() * 100

    # 交易盈亏统计
    sell_trades = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sell_trades if t["pnl"] > 0]
    losses = [t for t in sell_trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(sell_trades) * 100 if sell_trades else 0

    return {
        "equity_curve": eq, "trades": trades, "daily_positions": daily_positions,
        "total_return_pct": round(total_ret, 2), "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(max_dd, 2), "win_rate_pct": round(win_rate, 1),
        "n_trades": len(trades), "n_sells": len(sell_trades),
        "n_wins": len(wins), "n_losses": len(losses),
        "final_equity": round(float(eq["equity"].iloc[-1]), 2),
        "avg_win_pct": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss_pct": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
        "market_up_days": sum(1 for v in index_ma.values() if v),
        "market_down_days": sum(1 for v in index_ma.values() if not v),
    }


def backtest_short(signals, klines, index_ma, short_max_score: float = -1.0, board_cap_filter: dict | None = None,
                   caps: dict | None = None) -> dict:
    """做空回测：低分股票做空（分数 ≤ short_max_score）。

    做空逻辑（与做多相反）：
    - 分数 ≤ 阈值的低分股票 → 卖空（做空）
    - 做空收益 = 价格下跌则赚（买入价 - 卖出平仓价）
    - 止盈止损反转：价格跌 8% 止盈，涨 5% 止损
    """
    def _board_of(code: str) -> str:
        if code.startswith('688'): return '科创板'
        if code.startswith('30'): return '创业板'
        if code.startswith('00') or code.startswith('002') or code.startswith('003'): return '深主板'
        if code.startswith('60'): return '沪主板'
        return '其他'
    def _cap_of(mv_yi: float) -> str:
        if mv_yi < 30: return '微盘'
        if mv_yi < 100: return '小盘'
        if mv_yi < 300: return '中盘'
        if mv_yi < 1000: return '大盘'
        return '超大盘'

    dates = sorted(signals.keys())
    price = {}
    for suffix, df in klines.items():
        for _, row in df.iterrows():
            d = str(row["trade_date"])[:10]
            price[(suffix, d)] = {
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
            }

    short_positions: dict[str, dict] = {}  # suffix -> {cost(卖空价), shares, date}
    trades = []
    equity_curve = []
    cash = 1_000_000.0
    daily_positions = {}

    for i, d in enumerate(dates):
        day_items = signals[d]
        # 低分候选（分数从低到高，取前 TOP_N）
        low_scores = sorted([(s, sc) for s, sc, rk in day_items], key=lambda x: x[1])[:TOP_N]
        score_map = {s: sc for s, sc, rk in day_items}
        market_up = index_ma.get(d, False)
        # 做空在"大盘空"更有利，但这里统一测试；也可用 market_down
        use_short = market_up  # 保持与做多同条件对比

        # ── 平仓检查（做空：价格跌止盈，涨止损）──
        to_close = []
        for suffix, h in list(short_positions.items()):
            px = price.get((suffix, d))
            if not px:
                continue
            high, low = px["high"], px["low"]
            cost = h["cost"]  # 卖空价
            # 做空止盈 = 价格跌到成本*0.92（赚8%）；止损 = 涨到成本*1.05
            if low <= cost * (1 - TAKE_PROFIT):
                to_close.append((suffix, "short_take_profit", cost * (1 - TAKE_PROFIT)))
            elif high >= cost * (1 + STOP_LOSS):
                to_close.append((suffix, "short_stop_loss", cost * (1 + STOP_LOSS)))
            elif score_map.get(suffix, 0) > short_max_score * 0.8:
                to_close.append((suffix, "score_rise", px["close"]))
        for suffix, reason, close_px in to_close:
            h = short_positions.pop(suffix)
            # 做空盈亏 = (卖空价 - 平仓价) * 股数
            fee = close_px * h["shares"] * (COMMISSION + STAMP_TAX)
            pnl = (h["cost"] - close_px) * h["shares"] - fee
            cash += pnl  # 平仓只结算已实现盈亏
            trades.append({"date": d, "symbol": suffix, "action": "close_short", "reason": reason,
                           "price": round(close_px, 2), "fee": round(fee, 2), "pnl": round(pnl, 2)})

        # ── 开空（分数 ≤ 阈值）──
        if market_up:  # 与做多同条件
            candidates = [s for s, sc in low_scores if sc <= short_max_score]
            if board_cap_filter and caps:
                boards_ok = board_cap_filter.get("boards")
                caps_ok = board_cap_filter.get("caps")
                filtered = []
                for sym in candidates:
                    if boards_ok and _board_of(sym) not in boards_ok:
                        continue
                    if caps_ok:
                        suffix = StockCodeUtil.to_suffix(sym)
                        prefix = StockCodeUtil.to_prefix(sym)
                        mv = caps.get(prefix, caps.get(suffix, 0)) / 1e8
                        cap = _cap_of(mv) if mv > 0 else "未知"
                        if cap not in caps_ok:
                            continue
                    filtered.append(sym)
                candidates = filtered
            for sym in candidates:
                suffix = StockCodeUtil.to_suffix(sym)
                if suffix in short_positions:
                    continue
                px = price.get((suffix, d))
                if not px or px["open"] <= 0:
                    continue
                shares = int(100_000 / px["open"] / 100) * 100
                if shares <= 0:
                    continue
                cost = px["open"]  # 卖空价
                fee = cost * shares * COMMISSION
                if cash < shares * cost * 0.5 + fee:  # 卖空保证金约50%
                    continue
                cash -= fee  # 只扣佣金，借券卖出不增加净资产
                short_positions[suffix] = {"cost": cost, "shares": shares, "date": d}
                trades.append({"date": d, "symbol": suffix, "action": "short", "reason": "low_score",
                               "price": round(cost, 2), "fee": round(fee, 2), "pnl": 0})

        # ── 当日权益 ──
        pos_val = 0
        for suffix, h in list(short_positions.items()):
            px = price.get((suffix, d))
            cur = px["close"] if px else h["cost"]
            # 空头市值 = 卖空收到的资金 - 当前需还券成本（浮盈/浮亏）
            pos_val += (h["cost"] - cur) * h["shares"]
        total = cash + pos_val
        daily_positions[d] = {"cash": round(cash, 2), "pos": round(pos_val, 2),
                              "total": round(total, 2), "n": len(short_positions), "market_up": market_up}
        equity_curve.append((d, total))

    eq = pd.DataFrame(equity_curve, columns=["date", "equity"])
    eq["ret"] = eq["equity"].pct_change()
    total_ret = (eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1) * 100
    days = len(eq)
    annual = ((eq["equity"].iloc[-1] / eq["equity"].iloc[0]) ** (252 / max(days, 1)) - 1) * 100
    max_dd = (eq["equity"] / eq["equity"].cummax() - 1).min() * 100

    close_trades = [t for t in trades if t["action"] == "close_short"]
    wins = [t for t in close_trades if t["pnl"] > 0]
    losses = [t for t in close_trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(close_trades) * 100 if close_trades else 0

    return {
        "equity_curve": eq, "trades": trades, "daily_positions": daily_positions,
        "total_return_pct": round(total_ret, 2), "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(max_dd, 2), "win_rate_pct": round(win_rate, 1),
        "n_trades": len(trades), "n_sells": len(close_trades),
        "n_wins": len(wins), "n_losses": len(losses),
        "final_equity": round(float(eq["equity"].iloc[-1]), 2),
        "avg_win_pct": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss_pct": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
    }


def main():
    print(f"加载模型 {MODEL_ID} 信号...")
    signals = load_signals()
    dates = sorted(signals.keys())
    print(f"  交易日: {len(dates)} ({dates[0]} ~ {dates[-1]})")

    all_symbols = set()
    # 只收集出现在每日 Top20 的股票（买入/持仓/止盈止损都来自 Top20）
    for items in signals.values():
        for sym, sc, rk in items[:OUT_TOP]:
            all_symbols.add(sym)
    print(f"  涉及股票(Top{OUT_TOP}): {len(all_symbols)} 只, 加载 K线...")
    klines = load_klines(all_symbols)
    print(f"  K线加载: {len(klines)} 只")

    print("加载上证指数 MA20...")
    index_ma = load_index_ma20()
    print(f"  MA20 大盘多天数: {sum(1 for v in index_ma.values() if v)}, 空: {sum(1 for v in index_ma.values() if not v)}")

    print("运行回测...")
    result = backtest(signals, klines, index_ma)

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"总收益: {result['total_return_pct']}%  年化: {result['annual_return_pct']}%")
    print(f"最大回撤: {result['max_drawdown_pct']}%  最终权益: {result['final_equity']:,}")
    print(f"胜率: {result['win_rate_pct']}%  ({result['n_wins']}胜/{result['n_losses']}负, 共{result['n_sells']}笔卖出)")
    print(f"平均盈利: {result['avg_win_pct']}  平均亏损: {result['avg_loss_pct']}")

    print("\n近30个交易日持仓:")
    eq = result["equity_curve"]
    dps = result["daily_positions"]
    for d in dates[-30:]:
        if d in dps:
            dp = dps[d]
            print(f"  {d} 持仓{dp['n']}只 现金{dp['cash']:>12,} 持仓值{dp['pos']:>12,} 总{dp['total']:>12,} "
                  f"{'大盘多' if dp['market_up'] else '大盘空'}")

    # 输出最近卖出交易
    print("\n最近10笔卖出:")
    sells = [t for t in result["trades"] if t["action"] == "sell"][-10:]
    for t in sells:
        print(f"  {t['date']} {t['symbol']} {t['reason']} @{t['price']} pnl={t['pnl']}")

    # 保存收益曲线 CSV
    out_path = Path(__file__).resolve().parents[1] / "data" / "ensemble_backtest_curve.csv"
    eq.to_csv(out_path, index=False)
    print(f"\n收益曲线已保存: {out_path}")


if __name__ == "__main__":
    main()
