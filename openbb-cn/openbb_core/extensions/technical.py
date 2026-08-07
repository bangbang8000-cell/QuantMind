"""
技术分析扩展
提供常用的技术指标计算功能
"""

from typing import Optional, Union, List
import pandas as pd
import numpy as np


class TechnicalExtension:
    """
    技术分析扩展
    
    支持的技术指标:
    - MA: 移动平均线
    - EMA: 指数移动平均线
    - MACD: 指数平滑异同移动平均线
    - KDJ: 随机指标
    - RSI: 相对强弱指数
    - BOLL: 布林带
    - OBV: 能量潮
    - ATR: 平均真实波幅
    """
    
    def __init__(self, openbb_instance):
        self.openbb = openbb_instance
    
    def ma(
        self,
        symbol: str,
        period: int = 20,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算移动平均线 (MA)
        
        Args:
            symbol: 股票代码
            period: 周期 (默认 20)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 date, close, ma 的 DataFrame
        """
        # 获取数据
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 计算 MA
        df[f"ma{period}"] = df["close"].rolling(window=period).mean()
        
        return df[["date", "close", f"ma{period}"]].dropna()
    
    def ema(
        self,
        symbol: str,
        period: int = 20,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算指数移动平均线 (EMA)
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        df[f"ema{period}"] = df["close"].ewm(span=period, adjust=False).mean()
        
        return df[["date", "close", f"ema{period}"]].dropna()
    
    def macd(
        self,
        symbol: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算 MACD 指标
        
        Args:
            symbol: 股票代码
            fast: 快线周期 (默认 12)
            slow: 慢线周期 (默认 26)
            signal: 信号线周期 (默认 9)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 DIF, DEA, MACD (柱状图)
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 计算 EMA
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        
        # DIF = EMA(fast) - EMA(slow)
        df["dif"] = ema_fast - ema_slow
        
        # DEA = EMA(DIF, signal)
        df["dea"] = df["dif"].ewm(span=signal, adjust=False).mean()
        
        # MACD 柱状图 = (DIF - DEA) * 2
        df["macd"] = (df["dif"] - df["dea"]) * 2
        
        return df[["date", "close", "dif", "dea", "macd"]].dropna()
    
    def kdj(
        self,
        symbol: str,
        n: int = 9,
        m1: int = 3,
        m2: int = 3,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算 KDJ 指标
        
        Args:
            symbol: 股票代码
            n: RSV 周期 (默认 9)
            m1: K 周期 (默认 3)
            m2: D 周期 (默认 3)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 K, D, J 值
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 计算 RSV
        low_n = df["low"].rolling(window=n).min()
        high_n = df["high"].rolling(window=n).max()
        rsv = (df["close"] - low_n) / (high_n - low_n) * 100
        
        # 计算 K, D, J
        df["k"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        df["d"] = df["k"].ewm(com=m2 - 1, adjust=False).mean()
        df["j"] = 3 * df["k"] - 2 * df["d"]
        
        return df[["date", "close", "k", "d", "j"]].dropna()
    
    def rsi(
        self,
        symbol: str,
        period: int = 14,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算 RSI 指标
        
        Args:
            symbol: 股票代码
            period: 周期 (默认 14)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 RSI 值
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 计算涨跌
        delta = df["close"].diff()
        
        # 分离涨跌
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        # 计算平均涨跌
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # 计算 RS 和 RSI
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        return df[["date", "close", "rsi"]].dropna()
    
    def boll(
        self,
        symbol: str,
        period: int = 20,
        std_dev: float = 2.0,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算布林带
        
        Args:
            symbol: 股票代码
            period: 周期 (默认 20)
            std_dev: 标准差倍数 (默认 2.0)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 upper, middle, lower 通道
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 中轨 = MA
        df["middle"] = df["close"].rolling(window=period).mean()
        
        # 标准差
        std = df["close"].rolling(window=period).std()
        
        # 上轨和下轨
        df["upper"] = df["middle"] + std_dev * std
        df["lower"] = df["middle"] - std_dev * std
        
        return df[["date", "close", "upper", "middle", "lower"]].dropna()
    
    def volume_profile(
        self,
        symbol: str,
        bins: int = 50,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        计算成交量分布
        
        Args:
            symbol: 股票代码
            bins: 分箱数量 (默认 50)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 包含 price_range, volume, cum_volume
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        # 创建价格区间
        price_min = df["low"].min()
        price_max = df["high"].max()
        bins_array = np.linspace(price_min, price_max, bins)
        
        # 计算每个区间的成交量
        df["price_bin"] = pd.cut(df["close"], bins=bins_array)
        volume_profile = df.groupby("price_bin")["volume"].sum()
        
        # 转换为 DataFrame
        result = pd.DataFrame({
            "price_range": volume_profile.index.astype(str),
            "volume": volume_profile.values
        })
        result["cum_volume"] = result["volume"].cumsum()
        
        return result
    
    def support_resistance(
        self,
        symbol: str,
        lookback: int = 60,
        threshold: float = 0.02,
        provider: str = "akshare",
        **kwargs
    ) -> dict:
        """
        识别支撑位和阻力位
        
        Args:
            symbol: 股票代码
            lookback: 回溯周期 (默认 60)
            threshold: 阈值，默认价格触及次数的比例
            provider: 数据源
        
        Returns:
            dict: 包含 support_levels 和 resistance_levels
        """
        provider_instance = self.openbb.get_provider(provider)
        df = provider_instance.get_historical_data(symbol, **kwargs)
        
        df = df.tail(lookback)
        
        # 简单的支撑阻力识别
        # 基于局部极值
        df["local_max"] = (df["high"].shift(1) < df["high"]) & (df["high"].shift(-1) < df["high"])
        df["local_min"] = (df["low"].shift(1) > df["low"]) & (df["low"].shift(-1) > df["low"])
        
        resistance_levels = df[df["local_max"]]["high"].values
        support_levels = df[df["local_min"]]["low"].values
        
        return {
            "support_levels": sorted(support_levels),
            "resistance_levels": sorted(resistance_levels, reverse=True)
        }
