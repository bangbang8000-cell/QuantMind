"""
2024-2026 跨年数据加载器：统一加载全市场推理分数 + 价格 + 行业/板块映射

数据源：
- 2024/2025 分数: db/feature_snapshots/{2024,2025}_inference/*_full_inference.json
  （结构 {date: [{symbol, score}, ...]}，每天约5300只）
- 2026 分数: analysis/top20_tracking/*_inference.json + full_ranking_2026.parquet
  （结构 {date: [[symbol, score], ...]}）
- 价格: db/feature_snapshots/model_features_20XX.parquet（2024-2025全年 OHLC）
        analysis/top20_tracking/price_lookup_full_v2.pkl（2025-12-25起）
- 行业/板块: data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet

统一输出：
- scores_by_date: {date_str: DataFrame(symbol, score)}
- price_lookup: {date: {symbol: {open, close, ...}}} 或统一接口
- trading_days: 交易日序列
"""

import json
import glob
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path("/home/zbox/projects/quantmind")
SNAPSHOT_DIR = PROJECT_ROOT / "db/feature_snapshots"
TOP20_DIR = PROJECT_ROOT / "analysis/top20_tracking"
QUANTDB_INSTRUMENT = PROJECT_ROOT / "data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet"


# ══════════════════════════════════════════════════════════════════
# 市场板块分类（对应正分v2）
# ══════════════════════════════════════════════════════════════════
def market_board(sym: str) -> str:
    s = sym.split(".")[0]
    if s.startswith(("688", "689")):
        return "科创板"
    if s.startswith("920"):
        return "北交所"
    if s.startswith(("4", "8")):
        return "北交所"
    if s.startswith("3"):
        return "创业板"
    if s.startswith(("6", "9")):
        return "沪主板"
    if s.startswith(("0", "2")):
        return "深主板"
    return "其他"


def load_scores_2024_2025() -> dict[str, pd.DataFrame]:
    """加载 2024-2025 全市场推理分数 {date: DataFrame(symbol, score)}"""
    all_scores = {}
    for year in ["2024", "2025"]:
        # 优先用年度合并文件，其次按月文件
        year_file = SNAPSHOT_DIR / f"{year}_inference/{year}_full_inference.json"
        month_files = sorted(glob.glob(str(SNAPSHOT_DIR / f"{year}_inference/{year}-*_full_inference.json")))

        files = [year_file] if year_file.exists() else month_files
        for f in files:
            with open(f) as fh:
                d = json.load(fh)
            for date, rows in d.items():
                if isinstance(rows, list) and len(rows) > 0:
                    # 支持两种结构：[{symbol,score}] 和 [[symbol,score]]
                    if isinstance(rows[0], dict):
                        all_scores[date] = pd.DataFrame(rows)[["symbol", "score"]]
                    else:
                        all_scores[date] = pd.DataFrame(rows, columns=["symbol", "score"])
    return all_scores


def load_scores_2026() -> dict[str, pd.DataFrame]:
    """加载 2026 全市场推理分数"""
    all_scores = {}
    for f in sorted(glob.glob(str(TOP20_DIR / "*_inference.json"))):
        with open(f) as fh:
            d = json.load(fh)
        for date, rows in d.items():
            if isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], list):
                all_scores[date] = pd.DataFrame(rows, columns=["symbol", "score"])
    df7 = pd.read_parquet(TOP20_DIR / "full_ranking_2026.parquet")
    df7["trade_date"] = df7["trade_date"].astype(str)
    for date, grp in df7.groupby("trade_date"):
        if date not in all_scores:
            all_scores[date] = grp[["symbol", "fusion_score"]].rename(columns={"fusion_score": "score"})
    return all_scores


def load_all_scores() -> dict[str, pd.DataFrame]:
    """合并 2024-2026 全市场分数"""
    all_scores = {}
    all_scores.update(load_scores_2024_2025())
    all_scores.update(load_scores_2026())
    return all_scores


def load_prices_2024_2025() -> dict[str, dict[str, dict]]:
    """从 model_features parquet 加载价格 {date: {symbol: {open, close, high, low}}}"""
    price = {}
    for year in ["2024", "2025"]:
        pq = SNAPSHOT_DIR / f"model_features_{year}.parquet"
        if not pq.exists():
            continue
        df = pd.read_parquet(pq, columns=["symbol", "trade_date", "open", "high", "low", "close"])
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        for date, grp in df.groupby("trade_date"):
            if date not in price:
                price[date] = {}
            for _, row in grp.iterrows():
                price[date][str(row["symbol"])] = {
                    "open": float(row["open"]), "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"]),
                }
    return price


def load_prices_2026() -> dict[str, dict[str, dict]]:
    """从 price_lookup pickle 加载 2026 价格"""
    with open(TOP20_DIR / "price_lookup_full_v2.pkl", "rb") as fh:
        p = pickle.load(fh)
    price = {}
    for (sym, ts), v in p.items():
        date = pd.Timestamp(ts).strftime("%Y-%m-%d")
        if date not in price:
            price[date] = {}
        price[date][str(sym)] = v
    return price


def load_all_prices() -> dict[str, dict[str, dict]]:
    """合并 2024-2026 价格 {date: {symbol: {open, close, high, low}}}"""
    price = {}
    price.update(load_prices_2024_2025())
    price.update(load_prices_2026())
    return price


def get_trading_days(price: dict) -> list[str]:
    return sorted(price.keys())


def load_industry() -> pd.DataFrame:
    """加载行业映射 DataFrame(sym_num, name, rs_hyname, board, is_st, total_mv)"""
    df = pd.read_parquet(QUANTDB_INSTRUMENT)
    df["sym_num"] = df["Symbol"].str.split(".").str[0]
    result = pd.DataFrame({
        "sym_num": df["sym_num"],
        "name": df["Name"],
        "industry": df["rs_hyname"],
        "board": df["sym_num"].map(market_board),
        "is_st": df["IsSTGP"].astype(str) == "1",
    })
    return result


def get_close(price: dict, sym: str, date: str) -> float | None:
    day = price.get(date, {})
    r = day.get(str(sym))
    return r["close"] if r else None


def t_plus_return(price: dict, trading_days: list, sym: str, signal_date: str, horizon: int) -> float | None:
    """T+horizon 收益（从信号日收盘到第horizon个交易日收盘）"""
    if signal_date not in trading_days:
        return None
    idx = trading_days.index(signal_date)
    if idx + horizon >= len(trading_days):
        return None
    target_date = trading_days[idx + horizon]
    c0 = get_close(price, sym, signal_date)
    cH = get_close(price, sym, target_date)
    if c0 and cH and c0 > 0:
        return (cH - c0) / c0
    return None


def main():
    print("=" * 60)
    print("2024-2026 跨年数据加载器 - 自检")
    print("=" * 60)

    print("\n[1] 加载 2024-2025 分数...")
    s2425 = load_scores_2024_2025()
    dates2425 = sorted(s2425.keys())
    print(f"  {len(dates2425)} 天: {dates2425[0]} ~ {dates2425[-1]}")
    if dates2425:
        day = s2425[dates2425[0]]
        print(f"  首日{dates2425[0]}: {len(day)}只, 负分{(day['score']<0).sum()}")

    print("[2] 加载 2026 分数...")
    s26 = load_scores_2026()
    dates26 = sorted(s26.keys())
    print(f"  {len(dates26)} 天: {dates26[0]} ~ {dates26[-1]}")

    all_scores = {**s2425, **s26}
    all_dates = sorted(all_scores.keys())
    print(f"[3] 合并后: {len(all_dates)} 天: {all_dates[0]} ~ {all_dates[-1]}")

    print("\n[4] 加载 2024-2025 价格...")
    p2425 = load_prices_2024_2025()
    pd2425 = sorted(p2425.keys())
    print(f"  {len(pd2425)} 天: {pd2425[0]} ~ {pd2425[-1]}")
    if pd2425:
        d0 = pd2425[0]
        syms = list(p2425[d0].keys())[:3]
        print(f"  首日样例: {[(s, p2425[d0][s]['close']) for s in syms]}")

    print("[5] 加载 2026 价格...")
    p26 = load_prices_2026()
    pd26 = sorted(p26.keys())
    print(f"  {len(pd26)} 天: {pd26[0]} ~ {pd26[-1]}")

    all_prices = {**p2425, **p26}
    all_tdays = sorted(all_prices.keys())
    print(f"[6] 合并价格: {len(all_tdays)} 天: {all_tdays[0]} ~ {all_tdays[-1]}")

    print("\n[7] 行业/板块映射...")
    ind = load_industry()
    print(f"  {len(ind)} 只, 行业{ind['industry'].nunique()}个, 板块{ind['board'].nunique()}个")

    print("\n自检完成 ✅")


if __name__ == "__main__":
    main()
