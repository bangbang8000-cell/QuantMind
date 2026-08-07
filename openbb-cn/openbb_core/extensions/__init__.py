"""
扩展模块初始化
"""

from openbb_core.extensions.stocks import StocksExtension
from openbb_core.extensions.technical import TechnicalExtension
from openbb_core.extensions.fundamental import FundamentalExtension
from openbb_core.extensions.ai import AIExtension

__all__ = [
    "StocksExtension",
    "TechnicalExtension", 
    "FundamentalExtension",
    "AIExtension",
]
