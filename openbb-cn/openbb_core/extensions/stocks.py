"""
股票数据扩展
提供股票行情相关的数据接口
"""

from typing import Optional, Union, List
import pandas as pd
from datetime import datetime, timedelta


class StocksExtension:
    """
    股票数据扩展
    
    提供:
    - historical: 历史行情
    - quote: 实时行情
    - search: 股票搜索
    - index: 指数数据
    - market_overview: 市场概览
    """
    
    def __init__(self, openbb_instance):
        self.openbb = openbb_instance
    
    def historical(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        adjust: str = "qfq",
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取历史行情数据
        
        Args:
            symbol: 股票代码 (如 "000001.SZ", "600000")
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: K线周期 (daily/weekly/monthly)
            adjust: 复权类型 (qfq/hfq/none)
            provider: 数据源
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        provider_instance = self.openbb.get_provider(provider)
        return provider_instance.get_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjust=adjust,
            **kwargs
        )
    
    def quote(
        self,
        symbol: Union[str, List[str]],
        provider: str = "easyquotation",
        **kwargs
    ) -> Union[dict, pd.DataFrame]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码或代码列表
            provider: 数据源 (easyquotation/akshare/eastmoney)
        
        Returns:
            dict 或 pd.DataFrame: 实时行情数据
        """
        provider_instance = self.openbb.get_provider(provider)
        
        if isinstance(symbol, list):
            # 列表情况：使用批量接口（如果支持）
            if hasattr(provider_instance, 'get_realtime_quotes_batch'):
                return provider_instance.get_realtime_quotes_batch(symbol, **kwargs)
            else:
                # 不支持批量，逐一获取
                results = []
                for s in symbol:
                    try:
                        result = provider_instance.get_realtime_quote(s, **kwargs)
                        results.append(result)
                    except Exception:
                        pass
                return pd.DataFrame(results)
        else:
            # 单个代码
            return provider_instance.get_realtime_quote(symbol, **kwargs)
    
    def search(
        self,
        keyword: str,
        provider: str = "akshare",
        limit: int = 20,
        **kwargs
    ) -> List[dict]:
        """
        搜索股票
        
        Args:
            keyword: 搜索关键词（代码或名称）
            provider: 数据源
            limit: 返回结果数量限制
        
        Returns:
            List[dict]: 匹配的股票列表
        """
        provider_instance = self.openbb.get_provider(provider)
        return provider_instance.search_symbol(keyword, limit=limit, **kwargs)
    
    def index(
        self,
        symbol: str = "000001",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取指数数据
        
        Args:
            symbol: 指数代码
                - 000001: 上证指数
                - 399001: 深证成指
                - 399006: 创业板指
                - 000300: 沪深300
            provider: 数据源
        
        Returns:
            pd.DataFrame: 指数数据
        """
        provider_instance = self.openbb.get_provider(provider)
        
        if hasattr(provider_instance, "get_index_data"):
            return provider_instance.get_index_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                **kwargs
            )
        else:
            # fallback: 使用股票接口
            return provider_instance.get_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                **kwargs
            )
    
    def market_overview(
        self,
        provider: str = "akshare",
        **kwargs
    ) -> dict:
        """
        获取市场概览
        
        Returns:
            dict: 包含主要指数涨跌、市场情绪等
        """
        provider_instance = self.openbb.get_provider(provider)
        
        indices = {
            "上证指数": "000001",
            "深证成指": "399001", 
            "创业板指": "399006",
            "沪深300": "000300",
            "科创50": "000688",
        }
        
        overview = {}
        for name, code in indices.items():
            try:
                quote = provider_instance.get_realtime_quote(code)
                overview[name] = {
                    "price": quote.get("close", quote.get("收盘", 0)),
                    "change": quote.get("pct_change", quote.get("涨跌幅", 0)),
                    "volume": quote.get("volume", quote.get("成交量", 0)),
                }
            except Exception:
                overview[name] = {"error": "数据获取失败"}
        
        return overview
    
    def stock_list(
        self,
        market: str = "A股",
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取股票列表
        
        Args:
            market: 市场 (A股/港股/美股)
            provider: 数据源
        
        Returns:
            pd.DataFrame: 股票列表
        """
        provider_instance = self.openbb.get_provider(provider)
        
        try:
            import akshare as ak
            
            if market == "A股":
                df = ak.stock_info_a_code_name()
            elif market == "港股":
                df = ak.stock_hk_spot_em()
            elif market == "美股":
                df = ak.stock_us_spot_em()
            else:
                raise ValueError(f"Unsupported market: {market}")
            
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch stock list: {str(e)}")
    
    def block_trading(
        self,
        date: Optional[str] = None,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取大宗交易数据
        
        Args:
            date: 日期 (YYYY-MM-DD)，默认今天
            provider: 数据源
        
        Returns:
            pd.DataFrame: 大宗交易数据
        """
        import akshare as ak
        
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        else:
            date = date.replace("-", "")
        
        try:
            df = ak.stock_block_trade_em(date=date)
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch block trading data: {str(e)}")
