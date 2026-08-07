"""
AKShare Provider
集成 akshare 数据源的 Provider 实现

AKShare 是免费的 Python 财经数据接口包，提供股票、期货、基金等数据
项目地址: https://github.com/akshare-org/akshare
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta

from openbb_core.providers.base import BaseProvider, ProviderResponse


class AkShareProvider(BaseProvider):
    """
    AkShare 数据源 Provider
    
    支持的数据类型:
    - A股、港股、期货、基金、宏观数据
    - 实时行情、历史K线
    - 财务报表、估值数据
    """
    
    name = "akshare"
    description = "AKShare - 免费财经数据接口"
    supported_requests = [
        "historical_data",
        "realtime_quote",
        "financial_data",
        "search_symbol",
        "index_data",
        "futures_data",
        "fund_data",
    ]
    
    def __init__(self, credentials: Optional[Any] = None):
        super().__init__(credentials)
        self._client = None
        self._init_client()
    
    def _init_client(self):
        """初始化 akshare 客户端"""
        try:
            import akshare as ak
            self._client = ak
        except ImportError:
            raise ImportError(
                "akshare is not installed. "
                "Please install it with: pip install akshare"
            )
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        adjust: str = "qfq",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取历史行情数据
        
        Args:
            symbol: 股票代码 (如 "000001.SZ" 或 "000001")
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: K线周期 (daily/weekly/monthly)
            adjust: 复权类型 (qfq/hfq/none)
        
        Returns:
            pd.DataFrame: 包含 date, open, high, low, close, volume 列
        """
        import akshare as ak
        
        # 标准化股票代码
        symbol = self._normalize_symbol(symbol)
        
        # 设置默认日期范围
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        # 去除日期中的连字符
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")
        
        try:
            # 根据代码类型调用不同接口
            if symbol.startswith("60") or symbol.startswith("688"):
                # 上证
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    adjust=adjust
                )
            elif symbol.startswith("000") or symbol.startswith("001"):
                # 深证
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    adjust=adjust
                )
            else:
                # 通用接口
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    adjust=adjust
                )
            
            # 标准化列名
            df = self._normalize_dataframe(df)
            return df
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch historical data for {symbol}: {str(e)}")
    
    def get_realtime_quote(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码 (支持多代码，用逗号分隔)
        
        Returns:
            Dict: 实时行情数据
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            # 实时行情接口
            if "," in symbol:
                # 批量获取
                df = ak.stock_zh_a_spot_em()
                symbols = symbol.split(",")
                df = df[df["代码"].isin(symbols)]
            else:
                # 单只股票
                df = ak.stock_zh_a_spot_em()
                df = df[df["代码"] == symbol]
            
            if df.empty:
                return {}
            
            # 转换为字典
            result = df.iloc[0].to_dict()
            return result
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch realtime quote for {symbol}: {str(e)}")
    
    def search_symbol(self, keyword: str, **kwargs) -> List[Dict[str, str]]:
        """
        搜索股票代码
        
        Args:
            keyword: 搜索关键词（代码或名称）
        
        Returns:
            List[Dict]: 匹配的股票列表
        """
        import akshare as ak
        
        try:
            # 股票列表
            df = ak.stock_info_a_code_name()
            
            # 模糊搜索
            mask = df["code"].str.contains(keyword, na=False) | \
                   df["name"].str.contains(keyword, na=False, case=False)
            df = df[mask]
            
            # 限制返回数量
            df = df.head(kwargs.get("limit", 20))
            
            return df.to_dict("records")
            
        except Exception as e:
            raise RuntimeError(f"Failed to search symbol {keyword}: {str(e)}")
    
    def get_index_data(
        self,
        symbol: str = "000001",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取指数数据
        
        Args:
            symbol: 指数代码 (默认 "000001" 上证指数)
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.DataFrame: 指数数据
        """
        import akshare as ak
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")
        
        try:
            df = ak.stock_zh_index_daily_em(symbol=symbol)
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch index data for {symbol}: {str(e)}")
    
    def get_financial_data(
        self,
        symbol: str,
        statement_type: str = "balance_sheet",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取财务报表数据
        
        Args:
            symbol: 股票代码
            statement_type: 报表类型
                - balance_sheet: 资产负债表
                - income_statement: 利润表
                - cash_flow: 现金流量表
        
        Returns:
            pd.DataFrame: 财务报表数据
        """
        import akshare as ak
        
        symbol = self._normalize_symbol(symbol)
        
        try:
            if statement_type == "balance_sheet":
                df = ak.stock_financial_analysis_indicator(
                    symbol=symbol,
                    start_year="近3年"
                )
            elif statement_type == "income_statement":
                df = ak.stock_profit_sheet_by_report_em(symbol=symbol)
            elif statement_type == "cash_flow":
                df = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
            else:
                raise ValueError(f"Unknown statement type: {statement_type}")
            
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch financial data for {symbol}: {str(e)}")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码"""
        # 去除空格
        symbol = symbol.strip()
        
        # 如果没有后缀，根据代码前缀添加
        if "." not in symbol:
            if symbol.startswith("6"):
                symbol = f"{symbol}.SH"
            elif symbol.startswith(("0", "3")):
                symbol = f"{symbol}.SZ"
            elif symbol.startswith("8") or symbol.startswith("4"):
                symbol = f"{symbol}.BJ"
        
        # 去除上海/深圳的中文
        symbol = symbol.replace("上证", "").replace("深证", "")
        
        return symbol
    
    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame 列名"""
        # 常见的列名映射
        column_mapping = {
            "日期": "date",
            "时间": "date",
            "股票代码": "symbol",
            "代码": "symbol",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "换手率": "turnover_rate",
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        return df


# 快捷创建函数
def get_provider(credentials: Optional[Any] = None) -> AkShareProvider:
    """创建 AkShare Provider 实例"""
    return AkShareProvider(credentials)
