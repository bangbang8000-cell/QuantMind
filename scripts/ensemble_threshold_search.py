"""分数阈值优化：搜索最优买入/卖出分数阈值。

对买入分数阈值 × 卖出分数阈值组合跑回测，比较收益/胜率/交易成本，
找出交易次数少、收益好的参数（减少频繁换手的手续费）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ensemble_backtest import (
    load_signals, load_klines, load_index_ma20, backtest, OUT_TOP,
)

# 买入阈值搜索范围（融合模型 Top20 分数 1.5~3.0）
BUY_THRESHOLDS = [1.5, 1.6, 1.7, 1.75, 1.8, 1.9, 2.0, 2.2]
# 卖出阈值（0 = 用跌出Top20规则）
SELL_THRESHOLDS = [0, 1.5, 1.6, 1.7, 1.8]

def main():
    print("加载数据...")
    signals = load_signals()
    all_symbols = set()
    for items in signals.values():
        for sym, sc, rk in items[:OUT_TOP]:
            all_symbols.add(sym)
    klines = load_klines(all_symbols)
    index_ma = load_index_ma20()
    print(f"信号 {len(signals)} 天, K线 {len(klines)} 只")

    results = []
    for buy_thr in BUY_THRESHOLDS:
        for sell_thr in SELL_THRESHOLDS:
            if sell_thr > 0 and sell_thr > buy_thr:
                continue  # 卖出阈值应 ≤ 买入阈值
            r = backtest(signals, klines, index_ma,
                         buy_min_score=buy_thr, sell_below_score=sell_thr)
            results.append({
                "buy_thr": buy_thr, "sell_thr": sell_thr,
                "total_ret": r["total_return_pct"], "annual": r["annual_return_pct"],
                "max_dd": r["max_drawdown_pct"], "win_rate": r["win_rate_pct"],
                "n_trades": r["n_trades"], "n_sells": r["n_sells"],
                "final": r["final_equity"],
            })
            print(f"买>={buy_thr} 卖<{sell_thr or 'Top20'}: 收益{r['total_return_pct']}% "
                  f"年化{r['annual_return_pct']}% 回撤{r['max_drawdown_pct']}% "
                  f"胜率{r['win_rate_pct']}% 交易{r['n_trades']}")

    # 排序：收益优先，其次交易次数少
    print("\n" + "=" * 80)
    print("按收益排序 Top10:")
    ranked = sorted(results, key=lambda x: -x["total_ret"])
    for i, r in enumerate(ranked[:10]):
        print(f"  {i+1}. 买>={r['buy_thr']} 卖<{r['sell_thr'] or 'Top20'}: "
              f"收益{r['total_ret']}% 年化{r['annual']}% 回撤{r['max_dd']}% "
              f"胜率{r['win_rate']}% 交易{r['n_trades']}")

    print("\n按'收益/交易次数'性价比排序 Top10:")
    ranked2 = sorted(results, key=lambda x: -(x["total_ret"] / max(x["n_trades"], 1)))
    for i, r in enumerate(ranked2[:10]):
        print(f"  {i+1}. 买>={r['buy_thr']} 卖<{r['sell_thr'] or 'Top20'}: "
              f"收益{r['total_ret']}% 交易{r['n_trades']} 每次交易赚{r['total_ret']/max(r['n_trades'],1):.2f}%")

if __name__ == "__main__":
    main()
