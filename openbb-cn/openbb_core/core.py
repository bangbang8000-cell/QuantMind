"""
OPENBB-CN 核心类
参考 OpenBB Platform 架构设计的中国版金融数据平台
"""

import os
from typing import Any, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

# 版本信息
__version__ = "0.1.0"

# 默认 providers 配置
DEFAULT_PROVIDERS = ["akshare", "easyquotation", "tushare", "eastmoney"]


@dataclass
class ProviderCredentials:
    """数据源凭证配置"""
    name: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None


class OpenBB:
    """
    OPENBB-CN 主类
    
    提供统一的 Python API 访问各种金融数据
    """
    
    def __init__(
        self,
        providers: Optional[list[str]] = None,
        credentials: Optional[Dict[str, ProviderCredentials]] = None,
        cache: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        初始化 OpenBB-CN 实例
        
        Args:
            providers: 启用的数据源列表，默认使用 akshare, easyquotation, tushare
            credentials: 数据源凭证字典
            cache: 是否启用缓存
            cache_dir: 缓存目录路径
        """
        self.providers = providers or DEFAULT_PROVIDERS
        self.credentials = credentials or {}
        self.cache = cache
        self.cache_dir = cache_dir or Path.home() / ".openbb-cn" / "cache"
        
        # 初始化各模块
        self._stocks = None
        self._technical = None
        self._fundamental = None
        self._ai = None
        
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def stocks(self):
        """股票数据接口"""
        if self._stocks is None:
            from openbb_core.extensions.stocks import StocksExtension
            self._stocks = StocksExtension(self)
        return self._stocks
    
    @property
    def technical(self):
        """技术分析接口"""
        if self._technical is None:
            from openbb_core.extensions.technical import TechnicalExtension
            self._technical = TechnicalExtension(self)
        return self._technical
    
    @property
    def fundamental(self):
        """基本面分析接口"""
        if self._fundamental is None:
            from openbb_core.extensions.fundamental import FundamentalExtension
            self._fundamental = FundamentalExtension(self)
        return self._fundamental
    
    @property
    def ai(self):
        """AI 助手接口"""
        if self._ai is None:
            from openbb_core.extensions.ai import AIExtension
            self._ai = AIExtension(self)
        return self._ai
    
    def set_provider_credentials(self, provider: str, **kwargs):
        """
        设置数据源凭证
        
        Args:
            provider: 数据源名称
            **kwargs: 凭证参数 (api_key, api_secret, base_url 等)
        """
        self.credentials[provider] = ProviderCredentials(
            name=provider,
            **kwargs
        )
    
    def get_provider(self, provider_name: str) -> Any:
        """
        获取指定数据源实例
        
        Args:
            provider_name: 数据源名称 (akshare, tushare, easyquotation 等)
        
        Returns:
            数据源实例
        """
        from openbb_core.providers import get_provider
        return get_provider(provider_name, self.credentials.get(provider_name))
    
    def __repr__(self) -> str:
        return f"OpenBB-CN(v0.1.0, providers={self.providers})"


def main():
    """CLI 入口"""
    import sys
    print("OPENBB-CN - 面向中国市场的开源金融数据平台")
    print(f"Version: {__version__}")
    print()
    print("Quick Start:")
    print("  from openbb_core import OpenBB")
    print("  obb = OpenBB()")
    print("  data = obb.stocks.historical('000001.SZ')")
    print()
    print("For more info: https://github.com/OPENBB-CN/OPENBB-CN")


if __name__ == "__main__":
    main()
