"""
基本面分析扩展
提供财务报表、估值、业绩等基本面数据
"""

from typing import Optional, List
import pandas as pd


class FundamentalExtension:
    """
    基本面分析扩展
    
    提供:
    - financial_statement: 财务报表
    - valuation: 估值指标
    - dividend: 分红送转
    - holder: 股东信息
    - forecast: 业绩预测
    """
    
    def __init__(self, openbb_instance):
        self.openbb = openbb_instance
    
    def balance_sheet(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取资产负债表
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 资产负债表数据
        """
        provider_instance = self.openbb.get_provider(provider)
        
        if hasattr(provider_instance, "get_financial_data"):
            return provider_instance.get_financial_data(
                symbol=symbol,
                statement_type="balance_sheet",
                **kwargs
            )
        else:
            raise NotImplementedError(f"Provider {provider} does not support financial data")
    
    def income_statement(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取利润表
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 利润表数据
        """
        provider_instance = self.openbb.get_provider(provider)
        
        if hasattr(provider_instance, "get_financial_data"):
            return provider_instance.get_financial_data(
                symbol=symbol,
                statement_type="income_statement",
                **kwargs
            )
        else:
            raise NotImplementedError(f"Provider {provider} does not support financial data")
    
    def cash_flow(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取现金流量表
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 现金流量表数据
        """
        provider_instance = self.openbb.get_provider(provider)
        
        if hasattr(provider_instance, "get_financial_data"):
            return provider_instance.get_financial_data(
                symbol=symbol,
                statement_type="cash_flow",
                **kwargs
            )
        else:
            raise NotImplementedError(f"Provider {provider} does not support financial data")
    
    def valuation(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> dict:
        """
        获取估值指标
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            dict: 估值指标 (PE, PB, PS, PCF, 毛利率, 净利率等)
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            # 获取实时估值
            df = ak.stock_a_indicator_lg(symbol=symbol)
            
            if df.empty:
                return {}
            
            # 提取最新估值
            latest = df.iloc[-1]
            
            return {
                "symbol": symbol,
                "pe_ttm": latest.get("市盈率(TTM)", None),
                "pe_lYR": latest.get("市盈率(LYR)", None),
                "pb": latest.get("市净率", None),
                "ps_ttm": latest.get("市销率(TTM)", None),
                "pcf": latest.get("市现率", None),
                "roe": latest.get("净资产收益率(%)", None),
                "gross_margin": latest.get("毛利率(%)", None),
                "net_margin": latest.get("净利率(%)", None),
                "date": latest.get("日期", None),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to fetch valuation for {symbol}: {str(e)}")
    
    def dividend(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取分红送转信息
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 分红送转历史
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            df = ak.stock_dividend_details(symbol=symbol)
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch dividend for {symbol}: {str(e)}")
    
    def holder_count(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取股东人数变化
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 股东人数变化
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            df = ak.stock_holder_number(symbol=symbol)
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch holder count for {symbol}: {str(e)}")
    
    def major_shareholder(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取主要股东信息
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            pd.DataFrame: 主要股东列表
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            df = ak.stock_top_holder(symbol=symbol)
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch major holders for {symbol}: {str(e)}")
    
    def report_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: str = "akshare",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取财报发布日历
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            provider: 数据源
        
        Returns:
            pd.DataFrame: 财报发布日历
        """
        import akshare as ak
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        else:
            start_date = start_date.replace("-", "")
        
        if end_date is None:
            end_date = (datetime.now() + timedelta(days=90)).strftime("%Y%m%d")
        else:
            end_date = end_date.replace("-", "")
        
        try:
            df = ak.stock_report_financial_analysis_indicator(
                symbol="全部",
                start_year=start_date[:4],
                end_year=end_date[:4]
            )
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch report calendar: {str(e)}")
    
    def revenue_breakdown(
        self,
        symbol: str,
        provider: str = "akshare",
        **kwargs
    ) -> dict:
        """
        获取营收构成
        
        Args:
            symbol: 股票代码
            provider: 数据源
        
        Returns:
            dict: 营收构成明细
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            df = ak.stock_zyjs_ths(symbol=symbol)
            
            if df.empty:
                return {}
            
            return {
                "symbol": symbol,
                "revenue_breakdown": df.to_dict("records")
            }
        except Exception as e:
            raise RuntimeError(f"Failed to fetch revenue breakdown for {symbol}: {str(e)}")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码"""
        symbol = symbol.strip().upper()
        
        # 移除后缀
        for suffix in [".SH", ".SZ", ".BJ"]:
            if suffix in symbol:
                symbol = symbol.replace(suffix, "")
        
        return symbol


# 导入 datetime 和 timedelta
from datetime import datetime, timedelta
