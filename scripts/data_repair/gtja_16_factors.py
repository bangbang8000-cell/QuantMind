"""GTJA Alpha191 因子计算引擎 - 16 因子精选版。

实现用户指定的 16 个核心 GTJA 因子（含正向 / 反向 / 分行情 三类）:
  正向 6: Alpha 16, 32, 62, 83, 90, 99
  反向 6: Alpha 36, 70, 74, 150, 176, 179
  分行情 6: Alpha 42, 70, 95, 150, 158, 159  (70/150 与上重复)
  去重合计: 16 个

实现说明:
  1. 从仓库内 GTJA_Alpha191.py 移植，但做 3 项重写:
     - 把 wide-format (date × symbol pivot) 改为接受 long-format (symbol/date 主键) DataFrame
     - 修复 pandas 0.x 旧 API (pd.rolling_*, pd.ewma) → 现代 API
     - 把单日 iloc[-1,:] 改为滚动计算（每一天都输出因子值）
  2. 公式严格对照原研报 + 仓库 GTJA_Alpha191.py 双源校对
  3. 每个因子返回 pandas Series，index 与输入 (symbol, trade_date) 一致

使用:
    from gtja_16_factors import compute_gtja_16
    df = pd.read_parquet('model_features_2024.parquet')
    factors_df = compute_gtja_16(df)  # 输入 long-format OHLCV，输出 long-format 因子值

字段需求:
    必需: symbol, trade_date, open, high, low, close, volume, liq_amount
    派生: vwap = liq_amount / volume

参考:
  - 公式定义: docs OCR 国泰君安－基于短周期价量特征的多因子选股体系.md
  - 原代码: /home/dell/桌面/sata_drive/A_H/Alpha 101 & GTJA 191(1) (1)/Alpha 101 & GTJA 191/GTJA_Alpha191.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================================
# 工具函数（替代 GTJA 原代码里的 pd.rolling_*）
# ============================================================================

def _ts_corr(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    """rolling correlation of two wide-format DataFrames（每列单独算）."""
    return x.rolling(n).corr(y)


def _ts_cov(x: pd.DataFrame, y: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).cov(y)


def _ts_rank_pct(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """每列在过去 n 期的百分位排名（末位值的位置 / n）."""
    return x.rolling(n).apply(lambda v: pd.Series(v).rank(pct=True).iloc[-1], raw=False)


def _cross_rank(x: pd.DataFrame) -> pd.DataFrame:
    """横截面排名（按行 rank，pct=True）."""
    return x.rank(axis=1, pct=True)


def _ts_max(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).max()


def _ts_min(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).min()


def _ts_std(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).std()


def _ts_mean(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).mean()


def _ts_sum(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.rolling(n).sum()


# ============================================================================
# 16 个 GTJA 因子（输入: wide-format OHLCV DataFrames; 输出: wide-format 因子值）
# ============================================================================

class GTJA16:
    """GTJA Alpha191 的 16 个核心因子计算器（wide format）.

    构造时传入 wide-format DataFrames (index=trade_date, columns=symbol).
    """

    def __init__(self, open_: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                 close: pd.DataFrame, volume: pd.DataFrame, amount: pd.DataFrame):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.amount = amount
        # VWAP = amount / volume (单股累计 VWAP，近似)
        self.vwap = (amount / volume.replace(0, np.nan)).fillna(method="ffill")

    # ---------- 正向因子 6 个 ----------

    def alpha_016(self) -> pd.DataFrame:
        """Alpha16: (-1 * TSMAX(RANK(CORR(RANK(VOLUME), RANK(VWAP), 5)), 5))

        含义: 横截面 rank 的成交量 vs vwap 5 日相关系数，再取近 5 日最大值，反向。
        """
        vol_rank = _cross_rank(self.volume)
        vwap_rank = _cross_rank(self.vwap)
        corr_5 = _ts_corr(vol_rank, vwap_rank, 5)
        corr_rank = _cross_rank(corr_5)
        return -_ts_max(corr_rank, 5)

    def alpha_032(self) -> pd.DataFrame:
        """Alpha32: (-1 * SUM(RANK(CORR(RANK(HIGH), RANK(VOLUME), 3)), 3))

        含义: 横截面 rank 的高价 vs 成交量 3 日相关系数，3 日累加，反向。
        """
        high_rank = _cross_rank(self.high)
        vol_rank = _cross_rank(self.volume)
        corr_3 = _ts_corr(high_rank, vol_rank, 3)
        corr_rank = _cross_rank(corr_3)
        return -_ts_sum(corr_rank, 3)

    def alpha_062(self) -> pd.DataFrame:
        """Alpha62: (-1 * CORR(HIGH, RANK(VOLUME), 5))

        含义: 高价与成交量横截面 rank 的 5 日相关系数，反向。
        """
        vol_rank = _cross_rank(self.volume)
        return -_ts_corr(self.high, vol_rank, 5)

    def alpha_083(self) -> pd.DataFrame:
        """Alpha83: (-1 * RANK(COVARIANCE(RANK(HIGH), RANK(VOLUME), 5)))

        含义: 横截面 rank 的高价与成交量 5 日协方差，再横截面 rank，反向。
        """
        high_rank = _cross_rank(self.high)
        vol_rank = _cross_rank(self.volume)
        cov_5 = _ts_cov(high_rank, vol_rank, 5)
        return -_cross_rank(cov_5)

    def alpha_090(self) -> pd.DataFrame:
        """Alpha90: (RANK(CORR(RANK(VWAP), RANK(VOLUME), 5)) * -1)

        含义: 横截面 rank 的 VWAP 与成交量 5 日相关系数，再横截面 rank，反向。
        """
        vwap_rank = _cross_rank(self.vwap)
        vol_rank = _cross_rank(self.volume)
        corr_5 = _ts_corr(vwap_rank, vol_rank, 5)
        return -_cross_rank(corr_5)

    def alpha_099(self) -> pd.DataFrame:
        """Alpha99: (-1 * RANK(COVARIANCE(RANK(CLOSE), RANK(VOLUME), 5)))

        含义: 横截面 rank 的收盘价与成交量 5 日协方差，再横截面 rank，反向。
        """
        close_rank = _cross_rank(self.close)
        vol_rank = _cross_rank(self.volume)
        cov_5 = _ts_cov(close_rank, vol_rank, 5)
        return -_cross_rank(cov_5)

    # ---------- 反向因子 6 个 ----------

    def alpha_036(self) -> pd.DataFrame:
        """Alpha36: RANK(SUM(CORR(RANK(VOLUME), RANK(VWAP), 6), 2))

        含义: 横截面 rank 的成交量 vs vwap 6 日相关系数，2 日累加，再横截面 rank。
        """
        vol_rank = _cross_rank(self.volume)
        vwap_rank = _cross_rank(self.vwap)
        corr_6 = _ts_corr(vol_rank, vwap_rank, 6)
        return _cross_rank(_ts_sum(corr_6, 2))

    def alpha_070(self) -> pd.DataFrame:
        """Alpha70: STD(AMOUNT, 6)

        含义: 成交额 6 日标准差。
        """
        return _ts_std(self.amount, 6)

    def alpha_074(self) -> pd.DataFrame:
        """Alpha74: (RANK(CORR(SUM(LOW*0.35 + VWAP*0.65, 20), SUM(MEAN(VOLUME,40), 20), 7))
                    + RANK(CORR(RANK(VWAP), RANK(VOLUME), 6)))

        含义: 长期累积价量序列相关 + 短期排名价量序列相关，两者相加。
        """
        # 第一部分
        price_mix = self.low * 0.35 + self.vwap * 0.65
        sum_price = _ts_sum(price_mix, 20)
        sum_vol_mean = _ts_sum(_ts_mean(self.volume, 40), 20)
        corr_1 = _ts_corr(sum_price, sum_vol_mean, 7)
        # 第二部分
        vwap_rank = _cross_rank(self.vwap)
        vol_rank = _cross_rank(self.volume)
        corr_2 = _ts_corr(vwap_rank, vol_rank, 6)
        return _cross_rank(corr_1) + _cross_rank(corr_2)

    def alpha_150(self) -> pd.DataFrame:
        """Alpha150: (CLOSE + HIGH + LOW) / 3 * VOLUME

        含义: 平均价格 × 成交量，量价综合指标。
        """
        return (self.close + self.high + self.low) / 3 * self.volume

    def alpha_176(self) -> pd.DataFrame:
        """Alpha176: CORR(RANK((CLOSE - TSMIN(LOW, 12)) / (TSMAX(HIGH, 12) - TSMIN(LOW, 12))),
                          RANK(VOLUME), 6)

        含义: 12 日 KDJ 相对位置（横截面 rank）与成交量 rank 的 6 日相关系数。
        """
        low_12 = _ts_min(self.low, 12)
        high_12 = _ts_max(self.high, 12)
        denom = (high_12 - low_12).replace(0, np.nan)
        rsv = (self.close - low_12) / denom
        rsv_rank = _cross_rank(rsv)
        vol_rank = _cross_rank(self.volume)
        return _ts_corr(rsv_rank, vol_rank, 6)

    def alpha_179(self) -> pd.DataFrame:
        """Alpha179: RANK(CORR(VWAP, VOLUME, 4)) * RANK(CORR(RANK(LOW), RANK(MEAN(VOLUME,50)), 12))

        含义: vwap 与成交量短期相关 × 低价 rank 与成交量均值 rank 长期相关。
        """
        corr_1 = _ts_corr(self.vwap, self.volume, 4)
        low_rank = _cross_rank(self.low)
        vol_mean_50 = _ts_mean(self.volume, 50)
        vol_mean_50_rank = _cross_rank(vol_mean_50)
        corr_2 = _ts_corr(low_rank, vol_mean_50_rank, 12)
        return _cross_rank(corr_1) * _cross_rank(corr_2)

    # ---------- 分行情因子 6 个（70, 150 与上重复，不重复实现）----------

    def alpha_042(self) -> pd.DataFrame:
        """Alpha42: (-1 * RANK(STD(HIGH, 10))) * CORR(HIGH, VOLUME, 10)

        含义: 高价波动率 × 价量相关性，复合信号。
        """
        std_high = _ts_std(self.high, 10)
        corr_hv = _ts_corr(self.high, self.volume, 10)
        return -_cross_rank(std_high) * corr_hv

    def alpha_095(self) -> pd.DataFrame:
        """Alpha95: STD(AMOUNT, 20)

        含义: 成交额 20 日标准差（与 alpha70 的 6 日呼应）。
        """
        return _ts_std(self.amount, 20)

    def alpha_158(self) -> pd.DataFrame:
        """Alpha158: (HIGH - SMA(CLOSE, 15, 2) - (LOW - SMA(CLOSE, 15, 2))) / CLOSE
                  = (HIGH - LOW) / CLOSE

        注: 数学上 SMA 项抵消，实际等于(HIGH-LOW)/CLOSE，但保留原始结构以反映公式。
        含义: 日内振幅占比。
        """
        ema_close = self.close.ewm(span=15, adjust=False).mean()
        return ((self.high - ema_close) - (self.low - ema_close)) / self.close.replace(0, np.nan)

    def alpha_159(self) -> pd.DataFrame:
        """Alpha159: ((CLOSE - SUM(MIN(LOW, DELAY(CLOSE,1)), 6))
                     / SUM(MAX(HIGH, DELAY(CLOSE,1)) - MIN(LOW, DELAY(CLOSE,1)), 6)
                     * 12 * 24
                     + ... 12 日 + 24 日加权平均) * 100 / (6*12 + 6*24 + 12*24)

        含义: 多周期 RSV (相对强弱位置) 加权平均，本质是改良版 KDJ。
        """
        prev_close = self.close.shift(1)
        true_low = np.minimum(self.low, prev_close)
        true_high = np.maximum(self.high, prev_close)
        true_range = true_high - true_low

        def _rsv_window(n):
            return (self.close - _ts_sum(true_low, n)) / _ts_sum(true_range, n).replace(0, np.nan)

        w6 = 12 * 24
        w12 = 6 * 24
        w24 = 6 * 12
        denom = w6 + w12 + w24
        return (_rsv_window(6) * w6 + _rsv_window(12) * w12 + _rsv_window(24) * w24) * 100 / denom

    # ---------- 全部 16 因子的 dispatch ----------

    def compute_all(self) -> dict[str, pd.DataFrame]:
        """返回 16 个因子 wide-format DataFrames 的字典."""
        return {
            "gtja_alpha_016": self.alpha_016(),
            "gtja_alpha_032": self.alpha_032(),
            "gtja_alpha_036": self.alpha_036(),
            "gtja_alpha_042": self.alpha_042(),
            "gtja_alpha_062": self.alpha_062(),
            "gtja_alpha_070": self.alpha_070(),
            "gtja_alpha_074": self.alpha_074(),
            "gtja_alpha_083": self.alpha_083(),
            "gtja_alpha_090": self.alpha_090(),
            "gtja_alpha_095": self.alpha_095(),
            "gtja_alpha_099": self.alpha_099(),
            "gtja_alpha_150": self.alpha_150(),
            "gtja_alpha_158": self.alpha_158(),
            "gtja_alpha_159": self.alpha_159(),
            "gtja_alpha_176": self.alpha_176(),
            "gtja_alpha_179": self.alpha_179(),
        }


# ============================================================================
# Long-format API（推荐使用）
# ============================================================================

def compute_gtja_16(df_long: pd.DataFrame) -> pd.DataFrame:
    """从 long-format DataFrame 计算 16 个 GTJA 因子。

    Args:
        df_long: DataFrame with columns:
            - symbol (str): 股票代码
            - trade_date (datetime): 交易日
            - open, high, low, close, volume (float): OHLCV
            - liq_amount (float): 成交额（对应 GTJA 中的 amount）

    Returns:
        long-format DataFrame with columns:
            symbol, trade_date, gtja_alpha_016, ..., gtja_alpha_179
    """
    required = {"symbol", "trade_date", "open", "high", "low", "close", "volume", "liq_amount"}
    missing = required - set(df_long.columns)
    if missing:
        raise ValueError(f"缺少必需列: {missing}")

    # 排序后 pivot
    df = df_long[list(required)].copy()
    df = df.sort_values(["trade_date", "symbol"])

    def _piv(col):
        return df.pivot(index="trade_date", columns="symbol", values=col).astype(float)

    open_ = _piv("open")
    high = _piv("high")
    low = _piv("low")
    close = _piv("close")
    volume = _piv("volume")
    amount = _piv("liq_amount")

    gtja = GTJA16(open_, high, low, close, volume, amount)
    factor_dict = gtja.compute_all()

    # 把 wide-format 因子 melt 回 long-format
    pieces = []
    for fname, fdf in factor_dict.items():
        f_long = fdf.stack().rename(fname).reset_index()
        if "level_1" in f_long.columns:
            f_long = f_long.rename(columns={"level_1": "symbol"})
        pieces.append(f_long.set_index(["trade_date", "symbol"])[fname])

    result = pd.concat(pieces, axis=1).reset_index()
    return result


if __name__ == "__main__":
    # 简单冒烟测试
    import sys
    parquet = "/app/db/feature_snapshots/model_features_2024.parquet"
    print(f"读取 {parquet}...")
    df = pd.read_parquet(parquet, columns=[
        "symbol", "trade_date", "open", "high", "low", "close", "volume", "liq_amount"
    ])
    print(f"  原始: {len(df):,} 行 × {df['symbol'].nunique():,} 票 × {df['trade_date'].nunique()} 天")

    # 限量测试（前 100 只票，加速）
    if "--full" not in sys.argv:
        symbols = df["symbol"].unique()[:100]
        df = df[df["symbol"].isin(symbols)]
        print(f"  限量: {len(df):,} 行 (前 100 票)")

    print("\n计算 16 因子...")
    import time
    t0 = time.time()
    factors = compute_gtja_16(df)
    print(f"  耗时: {time.time()-t0:.1f}s")
    print(f"  输出: {len(factors):,} 行 × {factors.shape[1]} 列")

    print("\n各因子覆盖率:")
    for col in [c for c in factors.columns if c.startswith("gtja_")]:
        n = factors[col].notna().sum()
        cov = n / len(factors) * 100
        print(f"  {col}: {n:,} 非空 ({cov:.1f}%)")

    print("\n样本 (前 5 行非空数据):")
    fcols = [c for c in factors.columns if c.startswith("gtja_")]
    sample = factors.dropna(subset=fcols, how="all").head(5)
    print(sample.to_string())
