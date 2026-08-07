"""
Providers 模块
数据源提供者集合
"""

from openbb_core.providers.base import BaseProvider, ProviderRouter, ProviderResponse
from openbb_core.providers.akshare_provider import AkShareProvider
from openbb_core.providers.easyquotation_provider import EasyQuotationProvider
from openbb_core.providers.tushare_provider import TushareProvider
from openbb_core.providers.eastmoney_provider import EastMoneyProvider

__all__ = [
    "BaseProvider",
    "ProviderRouter",
    "ProviderResponse",
    "AkShareProvider",
    "EasyQuotationProvider",
    "TushareProvider",
    "EastMoneyProvider",
]


def get_provider(name: str, credentials=None) -> BaseProvider:
    """
    获取指定名称的 Provider 实例
    
    Args:
        name: Provider 名称
        credentials: 凭证信息
    
    Returns:
        BaseProvider: Provider 实例
    
    Raises:
        ValueError: 不支持的 Provider
    """
    providers = {
        "akshare": AkShareProvider,
        "easyquotation": EasyQuotationProvider,
        "tushare": TushareProvider,
        "eastmoney": EastMoneyProvider,
    }
    
    if name not in providers:
        raise ValueError(
            f"Provider '{name}' not found. "
            f"Supported providers: {list(providers.keys())}"
        )
    
    return providers[name](credentials)
