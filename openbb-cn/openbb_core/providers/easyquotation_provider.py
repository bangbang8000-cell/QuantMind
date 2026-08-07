"""
EasyQuotation Provider
集成 easyquotation (通达信) 数据源的 Provider 实现

EasyQuotation 是一个免费实时行情获取工具，支持通达信等数据源
项目地址: https://github.com/利益关系/easyquotation
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from datetime import datetime

from openbb_core.providers.base import BaseProvider


class EasyQuotationProvider(BaseProvider):
    """
    EasyQuotation (通达信) 数据源 Provider
    
    核心功能:
    - 实时行情获取（免费）
    - 支持A股、港股、期货等
    - 数据延迟低
    """
    
    name = "easyquotation"
    description = "EasyQuotation - 通达信实时行情"
    supported_requests = [
        "realtime_quote",
        "realtime_quotes_batch",
    ]
    
    def __init__(self, credentials: Optional[Any] = None):
        super().__init__(credentials)
        self._client = None
        self._init_client()
    
    def _init_client(self):
        """初始化 easyquotation 客户端"""
        try:
            import easyquotation
            # 使用新浪行情源（默认免费）
            self._client = easyquotation.use("sina")
        except ImportError:
            raise ImportError(
                "easyquotation is not installed. "
                "Please install it with: pip install easyquotation"
            )
    
    def get_realtime_quote(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        获取单只股票实时行情
        
        Args:
            symbol: 股票代码
                - A股: 600000 (上证) / 000001 (深证)
                - 港股: hk001 (前缀 hk)
                - 美国: usAAPL (前缀 us)
        
        Returns:
            Dict: 实时行情数据，包含:
                - name: 股票名称
                - code: 代码
                - price: 现价
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - volume: 成交量
                - amount: 成交额
                - bid: 买价
                - ask: 卖价
                - timestamp: 时间戳
        """
        if self._client is None:
            self._init_client()
        
        try:
            # 标准化代码
            symbol = self._normalize_symbol(symbol)
            
            # 获取行情
            result = self._client.real(symbol)
            
            if symbol in result:
                data = result[symbol]
                # 添加时间戳
                data["timestamp"] = datetime.now().isoformat()
                return data
            else:
                raise ValueError(f"Symbol {symbol} not found")
                
        except Exception as e:
            raise RuntimeError(f"Failed to fetch realtime quote for {symbol}: {str(e)}")
    
    def get_realtime_quotes_batch(
        self,
        symbols: List[str],
        **kwargs
    ) -> pd.DataFrame:
        """
        批量获取实时行情
        
        Args:
            symbols: 股票代码列表
        
        Returns:
            pd.DataFrame: 批量行情数据
        """
        if self._client is None:
            self._init_client()
        
        try:
            # 标准化代码列表
            symbols = [self._normalize_symbol(s) for s in symbols]
            
            # 批量获取
            result = self._client.real(symbols)
            
            # 转换为 DataFrame
            df = pd.DataFrame(result).T
            
            # 重命名列
            df = df.reset_index().rename(columns={"index": "symbol"})
            
            return df
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch realtime quotes: {str(e)}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取历史行情（EasyQuotation 不直接支持，建议使用 AkShare）
        
        此方法仅作为占位符，建议使用 AkShare 获取历史数据
        """
        raise NotImplementedError(
            "EasyQuotation is optimized for realtime quotes only. "
            "For historical data, please use the 'akshare' provider instead."
        )
    
    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化股票代码
        
        Args:
            symbol: 原始代码
        
        Returns:
            str: 标准化后的代码
        """
        symbol = symbol.strip().upper()
        
        # 移除后缀
        for suffix in [".SH", ".SZ", ".HK", ".US"]:
            if suffix in symbol:
                symbol = symbol.replace(suffix, "")
        
        # 添加正确的前缀
        if symbol.startswith(("60", "688")):
            return symbol  # 新浪格式不需要前缀
        elif symbol.startswith(("00", "30")):
            return symbol  # 新浪格式不需要前缀
        elif symbol.startswith("HK"):
            return symbol.lower()  # 港股
        elif symbol.startswith("US"):
            return symbol.upper()  # 美股
        
        return symbol


def get_provider(credentials: Optional[Any] = None) -> EasyQuotationProvider:
    """创建 EasyQuotation Provider 实例"""
    return EasyQuotationProvider(credentials)
