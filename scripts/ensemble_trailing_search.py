"""动态止盈搜索：不同激活点 + 回撤幅度的组合"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ensemble_backtest import (
    load_signals, load_klines, load_index_ma20, backtest,
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

    print("\n=== 买入≥2.2 + 大盘过滤，动态止盈搜索 ===")
    # activate: 涨到多少激活移动止盈; drop: 从最高点回撤多少卖
    for act in [0.05, 0.08, 0.10, 0.12, 0.15]:
        for drop in [0.02, 0.03, 0.05, 0.08]:
            r = backtest(signals, klines, index_ma, buy_min_score=2.2, caps=caps,
                         trailing_activate=act, trailing_drop=drop)
            print(f"  激活+{act*100:.0f}% 回撤{drop*100:.0f}%: "
                  f"收益{r['total_return_pct']}% 年化{r['annual_return_pct']}% "
                  f"回撤{r['max_drawdown_pct']}% 胜率{r['win_rate_pct']}% 交易{r['n_trades']}")


if __name__ == "__main__":
    main()
