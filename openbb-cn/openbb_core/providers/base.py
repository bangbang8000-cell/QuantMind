"""
Provider 基类
所有数据源 Provider 必须继承此基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import pandas as pd
import asyncio
from functools import wraps
import time


@dataclass
class ProviderResponse:
    """Provider 响应数据封装"""
    data: Any
    provider: str
    timestamp: float
    cached: bool = False
    error: Optional[str] = None


class BaseProvider(ABC):
    """
    数据源 Provider 基类
    
    所有数据源（如 akshare、tushare、easyquotation）都需要实现此接口
    """
    
    name: str = "base"
    description: str = "Base Provider"
    supported_requests: List[str] = []
    
    def __init__(self, credentials: Optional[Any] = None):
        self.credentials = credentials
        self._cache: Dict[str, ProviderResponse] = {}
        self._cache_ttl: int = 60  # 缓存生存时间（秒）
    
    def cache_response(func):
        """缓存装饰器"""
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # 检查缓存
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if time.time() - cached.timestamp < self._cache_ttl:
                    cached.cached = True
                    return cached
            
            # 调用原函数
            result = await func(self, *args, **kwargs)
            
            # 存入缓存
            self._cache[cache_key] = ProviderResponse(
                data=result,
                provider=self.name,
                timestamp=time.time()
            )
            return result
        
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if time.time() - cached.timestamp < self._cache_ttl:
                    cached.cached = True
                    return cached
            
            result = func(self, *args, **kwargs)
            
            self._cache[cache_key] = ProviderResponse(
                data=result,
                provider=self.name,
                timestamp=time.time()
            )
            return result
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
    
    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取历史行情数据
        
        Args:
            symbol: 股票代码 (如 "000001.SZ")
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            **kwargs: 其他参数
        
        Returns:
            pd.DataFrame: 包含 OHLCV 数据的 DataFrame
        """
        pass
    
    @abstractmethod
    def get_realtime_quote(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
            **kwargs: 其他参数
        
        Returns:
            Dict: 实时行情数据
        """
        pass
    
    def get_financial_data(
        self,
        symbol: str,
        statement_type: str = "balance_sheet",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取财务报表数据（可选实现）
        
        Args:
            symbol: 股票代码
            statement_type: 报表类型 (balance_sheet/income_statement/cash_flow)
            **kwargs: 其他参数
        
        Returns:
            pd.DataFrame: 财务报表数据
        """
        raise NotImplementedError(f"{self.name} does not support financial data")
    
    def search_symbol(self, keyword: str, **kwargs) -> List[Dict[str, str]]:
        """
        搜索股票代码（可选实现）
        
        Args:
            keyword: 搜索关键词
            **kwargs: 其他参数
        
        Returns:
            List[Dict]: 匹配的股票列表
        """
        raise NotImplementedError(f"{self.name} does not support symbol search")


class ProviderRouter:
    """
    Provider 路由器
    管理多个 Provider 的统一访问
    """
    
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.default_provider: Optional[str] = None
    
    def register(self, provider: BaseProvider, set_default: bool = False):
        """注册 Provider"""
        self.providers[provider.name] = provider
        if set_default or not self.default_provider:
            self.default_provider = provider.name
    
    def get(self, name: str) -> Optional[BaseProvider]:
        """获取 Provider"""
        return self.providers.get(name)
    
    def list_providers(self) -> List[str]:
        """列出所有已注册的 Provider"""
        return list(self.providers.keys())
