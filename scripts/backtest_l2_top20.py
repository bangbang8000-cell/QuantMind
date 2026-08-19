"""L2 CatBoost T+5 策略回测：Top20 每日滚动 + 每只100股 + 涨跌停禁买卖。

模型: mdl_cn_train_20260819100559_9163cb84_ac5c5b2e (L2 CatBoost T+5 2023-2025)
策略规则（用户定义）:
1. 从 2026-08-04 起，每日按模型分数排序取 Top20 为目标持仓
2. 每只买入 100 股
3. 涨停/跌停的股票不能买入、不能卖出
4. 每日滚动换股：
   - 持仓跌出次日 Top20 且被分数更高的新股替代 → 卖出旧、买入新（保持20只）
   - 未跌出则继续持有
   - 当前持仓分数为负 → 卖出
5. 交易时点：当日分数 → 次日开盘价交易（避免前视偏差）

输出：每日持仓、交易、收益/回撤统计。
"""
import sys
import math
from datetime import date, timedelta
from pathlib import Path
from decimal import Decimal

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL_ID = "mdl_cn_train_20260819100559_9163cb84_ac5c5b2e"
TOP_N = 20
SHARES = 100          # 每只 100 股
START_DATE = date(2026, 8, 4)
COMMISSION = 0.0003   # 佣金万三
STAMP_TAX = 0.001     # 印花税卖出 0.1%

from backend.shared.database_manager_v2 import get_session
from backend.shared.stock_utils import StockCodeUtil
from backend.shared.logging_config import get_logger
from backend.services.trade.simulation.services.local_market_data import compute_limits
from sqlalchemy import text

logger = get_logger(__name__)


def load_signals() -> dict[str, list[tuple[str, float]]]:
    """加载模型信号: trade_date -> [(symbol, score)] 按分数降序"""
    import asyncio

    async def _load():
        async with get_session(read_only=True) as s:
            res = await s.execute(text("""
                SELECT trade_date, symbol, fusion_score
                FROM engine_signal_scores
                WHERE run_id IN (SELECT run_id FROM qm_model_inference_runs
                                 WHERE model_id=:mid AND status='completed')
                  AND trade_date >= :start
                ORDER BY trade_date, fusion_score DESC
            """), {"mid": MODEL_ID, "start": START_DATE})
            rows = res.fetchall()
        df = pd.DataFrame(rows, columns=["trade_date", "symbol", "score"])
        out: dict[str, list[tuple[str, float]]] = {}
        for d, grp in df.groupby("trade_date"):
            grp = grp.reset_index(drop=True)
            # 信号 symbol 是纯数字（300649），统一转 suffix（300649.SZ）与K线匹配
            out[str(d)] = [(StockCodeUtil.to_suffix(str(x).strip().upper()), float(s))
                           for x, s in zip(grp["symbol"], grp["score"])]
        return out
    return asyncio.run(_load())


def load_klines(symbols: set[str]) -> dict[str, pd.DataFrame]:
    """读日线 parquet（open/high/low/close），symbol 用 suffix 格式"""
    import pyarrow.parquet as pq
    import os

    data_root = Path(os.getenv("QM_QUANTDB_DATA_DIR", "/data/quantdb"))
    daily_dir = data_root / "1_kline_data" / "daily_unadjusted"
    suffix_list = sorted(StockCodeUtil.to_suffix(s) for s in symbols)
    if not suffix_list:
        return {}

    partitions = []
    for p in sorted(daily_dir.glob("dt=2026*")):
        partitions.append(p / "data.parquet")

    filters = [("symbol", "in", suffix_list)]
    all_dfs = []
    for f in partitions:
        try:
            t = pq.read_table(f, columns=["symbol", "time", "open", "high", "low", "close"], filters=filters)
            if t.num_rows > 0:
                all_dfs.append(t.to_pandas())
        except Exception:
            continue
    if not all_dfs:
        return {}
    full = pd.concat(all_dfs, ignore_index=True)
    full = full.rename(columns={"time": "trade_date"})
    full["trade_date"] = full["trade_date"].astype(str).str[:10]
    full = full[full["trade_date"] >= "2026-07-28"]  # 含 8/1 前一交易日算昨收
    klines = {}
    for suffix, grp in full.groupby("symbol"):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        klines[suffix] = grp[["trade_date", "open", "high", "low", "close"]]
    return klines


def _trading_days(dates: list[str]) -> list[str]:
    """按日期排序的交易日（信号日），策略在信号日用当日分数。"""
    return sorted(dates)


def run_backtest(signals, klines, commission=COMMISSION, stamp_tax=STAMP_TAX, initial_cash=100000.0):
    # 交易日列表
    dates = _trading_days(signals.keys())
    date_set = set(dates)

    # 价格索引: (suffix, date) -> {open, high, low, close}
    price: dict[tuple[str, str], dict] = {}
    for suffix, df in klines.items():
        for _, row in df.iterrows():
            d = str(row["trade_date"])[:10]
            price[(suffix, d)] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }

    # 上一交易日收盘价（用于算涨跌停基准）：遍历每日，维护 suffix -> pre_close
    def _prev_close(target_day: str):
        """返回 target_day 的前 1 个自然交易日（用日线里该股的前一条）。"""
        # 简化：从 price 构造，按股票取其 < target_day 的最近 close
        pass

    holdings: dict[str, dict] = {}   # suffix -> {shares, buy_px, buy_date, last_score}
    trades: list[dict] = []
    daily: dict[str, dict] = {}
    cash = initial_cash

    # 逐日价格序列辅助：suffix -> {date: close}，供算昨收
    close_by_sym_date: dict[str, dict[str, float]] = {}
    for (suffix, d), p in price.items():
        close_by_sym_date.setdefault(suffix, {})[d] = p["close"]

    def _limit_prices(suffix: str, day: str) -> tuple[float, float] | None:
        """返回 (limit_up, limit_down)，无昨收/停牌返回 None（无法交易）"""
        sym_close_map = close_by_sym_date.get(suffix)
        if not sym_close_map:
            return None
        # 找 day 之前的最近 close 作为昨收
        day_dates = sorted(d for d in sym_close_map if d < day)
        if not day_dates:
            return None
        pre_close = sym_close_map[day_dates[-1]]
        code = suffix.split(".")[0]
        try:
            lu, ld = compute_limits(code, pre_close, is_st=False, trade_date=date.fromisoformat(day))
        except Exception:
            return None
        return float(lu), float(ld)

    def _is_limit_open(suffix: str, day: str) -> tuple[bool, bool]:
        """返回 (是否一字涨停无法买入, 是否一字跌停无法卖出)"""
        lim = _limit_prices(suffix, day)
        px = price.get((suffix, day))
        if lim is None or px is None:
            return False, False
        lu, ld = lim
        o = px["open"]
        h = px["high"]
        l = px["low"]
        # 一字涨停：open >= limit_up（开盘即封涨停，可能买不到）
        cannot_buy = o >= lu - 0.001 and h <= lu + 0.001
        # 一字跌停：open <= limit_down（开盘即封跌停，卖不出）
        cannot_sell = o <= ld + 0.001 and l >= ld - 0.001
        return cannot_buy, cannot_sell

    # 逐日模拟
    # 先预计算每个交易日 -> 次日交易日
    next_day = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}

    # 初始资金按买入成本估算（不设固定现金，用 100 股*价格累积）
    for i, d in enumerate(dates):
        day_items = signals.get(d, [])
        today_top20 = [sym for sym, sc in day_items[:TOP_N]]
        score_map = {sym: sc for sym, sc in day_items}
        tgt_day = next_day.get(d)   # 次日交易

        # 若无次日（最后一天），只做卖出信号记录，不交易
        if not tgt_day or tgt_day not in date_set:
            # 记录当日持仓估值
            total_val = 0
            for suffix, h in holdings.items():
                px = price.get((suffix, d))
                v = px["close"] * h["shares"] if px else h["buy_px"] * h["shares"]
                total_val += v
            daily[d] = {"holdings": list(holdings.keys()), "value": total_val + cash,
                        "top20": today_top20, "cash": cash, "n": len(holdings)}
            continue

        # ── 卖出决策（在 tgt_day 开盘执行）──
        # 1) 分数为负 或 跌出 top20 且被新股替代
        current_syms = set(holdings.keys())
        # 目标持有 = 分数最高的20只（正分优先；分数为负的剔除）
        score_ranked = sorted(day_items, key=lambda x: -x[1])
        target_set = set(sym for sym, sc in score_ranked[:TOP_N] if sc > 0)
        # 卖出：持仓不在 target 或分数为负
        to_sell = []
        for suffix in current_syms:
            sc = score_map.get(suffix, 0)
            if sc <= 0 or suffix not in target_set:
                to_sell.append(suffix)

        for suffix in to_sell:
            px = price.get((suffix, tgt_day))
            cannot_buy, cannot_sell = _is_limit_open(suffix, tgt_day)
            if not px or cannot_sell:
                continue  # 无行情或一字跌停卖不出，继续持有
            h = holdings.pop(suffix)
            sell_px = px["open"]
            fee = sell_px * h["shares"] * (commission + stamp_tax)
            cash += h["shares"] * sell_px - fee
            trades.append({"day": tgt_day, "symbol": suffix, "action": "SELL",
                           "px": round(sell_px, 3), "shares": h["shares"],
                           "reason": "out_of_top" if sc <= 0 else "replaced",
                           "score": round(sc, 4)})

        # ── 买入决策：补足到 Top20 ──
        new_targets = [sym for sym, sc in score_ranked[:TOP_N] if sc > 0 and sym not in holdings]
        # 优先买分数最高的
        for suffix in new_targets:
            if len(holdings) >= TOP_N or cash <= 0:
                break
            px = price.get((suffix, tgt_day))
            cannot_buy, _ = _is_limit_open(suffix, tgt_day)
            if not px or cannot_buy:
                continue  # 无行情或一字涨停买不进
            buy_px = px["open"]
            cost = buy_px * SHARES
            if cost * (1 + commission) > cash:
                continue  # 现金不足则跳过（不融资买入）
            cash -= cost * (1 + commission)
            holdings[suffix] = {"shares": SHARES, "buy_px": buy_px, "buy_date": tgt_day}
            trades.append({"day": tgt_day, "symbol": suffix, "action": "BUY",
                           "px": round(buy_px, 3), "shares": SHARES,
                           "reason": "new_entry", "score": round(score_map.get(suffix, 0), 4)})

        # 当日组合估值（收盘）
        total_val = 0
        for suffix, h in holdings.items():
            px = price.get((suffix, tgt_day))
            v = px["close"] * h["shares"] if px else h["buy_px"] * h["shares"]
            total_val += v
        daily[tgt_day] = {"holdings": list(holdings.keys()), "value": total_val + cash,
                          "top20": today_top20, "cash": cash, "n": len(holdings)}

    return {"dates": sorted(daily.keys()), "daily": daily, "trades": trades}


def report(result, klines):
    daily = result["daily"]
    trades = result["trades"]
    dates = result["dates"]
    if not daily:
        print("无交易日数据")
        return

    sells = [t for t in trades if t["action"] == "SELL"]

    # 收益：净值相对初始资金 initial_cash（首日全现金 = 净值1.0）
    init = 100000.0
    print(f"\n{'日期':12} {'持仓':>4} {'现金':>10} {'持仓市值':>10} {'净值':>8} {'Top5'}")
    net_values = []
    prev_val = None
    for d in dates:
        info = daily[d]
        val = info["value"]
        cash_d = info.get("cash", 0)
        hold_val = val - cash_d
        net = val / init if init > 0 else 0
        net_values.append(net)
        sample = ",".join(info["holdings"][:5])
        print(f"{d:12} {info['n']:>4} {cash_d:>10,.0f} {hold_val:>10,.0f} {net:>8.3f}  {sample}")

    if len(net_values) > 1:
        total_ret = net_values[-1] - 1
        # 日收益序列（用于最大回撤）
        daily_rets = []
        for i in range(1, len(net_values)):
            daily_rets.append(net_values[i] / net_values[i - 1] - 1)
        days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
        years = max(days, 1) / 365
        annual = (net_values[-1]) ** (1 / years) - 1 if years > 0 and net_values[-1] > 0 else None
        peak = -999999
        max_dd = 0
        eq = 1.0
        for r in daily_rets:
            eq *= (1 + r)
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        print("\n" + "=" * 60)
        print(f"累计收益: {total_ret * 100:+.2f}%")
        if annual is not None:
            print(f"年化收益: {annual * 100:+.2f}%")
        print(f"最大回撤: {max_dd * 100:.2f}%")
        print(f"卖出笔数: {len(sells)}")
        print(f"末日现金: {daily[dates[-1]].get('cash', 0):,.0f} 元")

    # 最终持仓
    final = daily.get(dates[-1], {})
    if final.get("holdings"):
        print(f"\n最终持仓 ({len(final['holdings'])} 只):")
        for suf in final["holdings"]:
            print(f"  {suf}")


if __name__ == "__main__":
    print("加载信号...")
    signals = load_signals()
    all_syms = set()
    for items in signals.values():
        for s, _ in items:
            all_syms.add(s)
    print(f"信号天数: {len(signals)}, 涉及股票: {len(all_syms)}")

    print("加载K线...")
    klines = load_klines(all_syms)
    print(f"K线股票数: {len(klines)}")

    result = run_backtest(signals, klines)
    report(result, klines)