"""对比：板块市值过滤 vs 不过滤"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ensemble_backtest import load_signals, load_klines, load_index_ma20, backtest
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

    # 1. 不过滤（基准）
    r_base = backtest(signals, klines, index_ma, buy_min_score=2.2, caps=caps)

    # 2. 深主板+科创板 中小盘
    f1 = {"boards": {"深主板", "科创板"}, "caps": {"小盘", "中盘"}}
    r1 = backtest(signals, klines, index_ma, buy_min_score=2.2, caps=caps, board_cap_filter=f1)

    # 3. 深主板 中小盘
    f2 = {"boards": {"深主板"}, "caps": {"小盘", "中盘"}}
    r2 = backtest(signals, klines, index_ma, buy_min_score=2.2, caps=caps, board_cap_filter=f2)

    # 4. 深主板 小盘
    f3 = {"boards": {"深主板"}, "caps": {"小盘"}}
    r3 = backtest(signals, klines, index_ma, buy_min_score=2.2, caps=caps, board_cap_filter=f3)

    print("\n=== 对比(买入≥2.2 + 大盘过滤) ===")
    print(f"  不过滤:        收益{r_base['total_return_pct']}% 年化{r_base['annual_return_pct']}% 回撤{r_base['max_drawdown_pct']}% 胜率{r_base['win_rate_pct']}% 交易{r_base['n_trades']}")
    print(f"  深主+科创中小盘: 收益{r1['total_return_pct']}% 年化{r1['annual_return_pct']}% 回撤{r1['max_drawdown_pct']}% 胜率{r1['win_rate_pct']}% 交易{r1['n_trades']}")
    print(f"  深主板中小盘:   收益{r2['total_return_pct']}% 年化{r2['annual_return_pct']}% 回撤{r2['max_drawdown_pct']}% 胜率{r2['win_rate_pct']}% 交易{r2['n_trades']}")
    print(f"  深主板小盘:     收益{r3['total_return_pct']}% 年化{r3['annual_return_pct']}% 回撤{r3['max_drawdown_pct']}% 胜率{r3['win_rate_pct']}% 交易{r3['n_trades']}")


if __name__ == "__main__":
    main()
