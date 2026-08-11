"""做多 vs 做空 收益对比"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ensemble_backtest import (
    load_signals, load_klines, load_index_ma20, backtest, backtest_short,
)
from scripts.ensemble_board_cap_analysis import load_caps


def main():
    print("加载数据...")
    signals = load_signals()
    all_symbols = set()
    for items in signals.values():
        for sym, sc, rk in items[:20]:
            all_symbols.add(sym)
    klines = load_klines(all_symbols)
    index_ma = load_index_ma20()
    caps = load_caps()

    print("\n=== 做多（买高分）===")
    for thr in [1.5, 2.0, 2.2]:
        r = backtest(signals, klines, index_ma, buy_min_score=thr, caps=caps)
        print(f"  买≥{thr}: 收益{r['total_return_pct']}% 年化{r['annual_return_pct']}% 回撤{r['max_drawdown_pct']}% 胜率{r['win_rate_pct']}% 交易{r['n_trades']}")

    print("\n=== 做空（卖低分，分数≤阈值）===")
    for thr in [-1.0, -1.5, -2.0, -2.5]:
        r = backtest_short(signals, klines, index_ma, short_max_score=thr, caps=caps)
        print(f"  空≤{thr}: 收益{r['total_return_pct']}% 年化{r['annual_return_pct']}% 回撤{r['max_drawdown_pct']}% 胜率{r['win_rate_pct']}% 交易{r['n_trades']}")


if __name__ == "__main__":
    main()
