"""
Tushare Provider
集成 tushare 数据源的 Provider 实现

Tushare 是国内知名的免费/付费财经数据接口
项目地址: http://tushare.org/
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta

from openbb_core.providers.base import BaseProvider


class TushareProvider(BaseProvider):
    """
    Tushare 数据源 Provider
    
    需要 Token: https://tushare.pro/register
    
    支持的数据类型:
    - A股、港股通数据
    - 财务报表（利润表、资产负债表、现金流量表）
    - 估值数据
    - 宏观数据
    """
    
    name = "tushare"
    description = "Tushare - 专业财经数据接口"
    supported_requests = [
        "historical_data",
        "realtime_quote",
        "financial_data",
        "valuation",
        "dividend",
    ]
    
    def __init__(self, credentials: Optional[Any] = None):
        super().__init__(credentials)
        self._client = None
        self._token = None
        
        # 从 credentials 或环境变量获取 token
        if credentials and hasattr(credentials, 'api_key'):
            self._token = credentials.api_key
        else:
            import os
            self._token = os.environ.get("TUSHARE_TOKEN")
        
        if self._token:
            self._init_client()
        else:
            print("Warning: TUSHARE_TOKEN not set. Tushare provider will not work.")
    
    def _init_client(self):
        """初始化 tushare 客户端"""
        if self._token is None:
            return
            
        try:
            import tushare as ts
            ts.set_token(self._token)
            self._client = ts.pro_api()
        except ImportError:
            raise ImportError(
                "tushare is not installed. "
                "Please install it with: pip install tushare"
            )
    
    def _ensure_client(self):
        """确保 client 已初始化"""
        if self._client is None:
            if self._token is None:
                raise RuntimeError(
                    "Tushare token not set. "
                    "Please set TUSHARE_TOKEN environment variable or provide credentials."
                )
            self._init_client()
    
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
            symbol: 股票代码 (如 "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            period: K线周期 (daily/weekly/monthly)
            adjust: 复权类型 (qfq/hfq/none)
        
        Returns:
            pd.DataFrame: 包含 trade_date, open, high, low, close, volume 列
        """
        self._ensure_client()
        import tushare as ts
        
        # 标准化股票代码
        ts_code = self._normalize_symbol(symbol)
        
        # 设置日期
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        # 去除日期中的连字符
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")
        
        try:
            # 复权参数
            adj_map = {"qfq": "qfq", "hfq": "hfq", "none": None}
            adj = adj_map.get(adjust, "qfq")
            
            df = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                freq=self._period_to_tushare(period),
                adj=adj
            )
            
            if df is None or df.empty:
                raise RuntimeError(f"No data returned for {symbol}")
            
            # 按日期排序
            df = df.sort_values("trade_date")
            
            # 重命名列
            df = df.rename(columns={
                "trade_date": "date",
                "vol": "volume",
            })
            
            return df
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch historical data for {symbol}: {str(e)}")
    
    def get_realtime_quote(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
        
        Returns:
            Dict: 实时行情数据
        """
        import tushare as ts
        
        # 标准化
        symbol = symbol.strip().upper()
        ts_code = self._normalize_symbol(symbol)
        
        try:
            # 使用实时行情接口
            df = ts.realtime_quote(ts_code=ts_code)
            
            if df is None or df.empty:
                return {}
            
            return df.iloc[0].to_dict()
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch realtime quote for {symbol}: {str(e)}")
    
    def get_financial_data(
        self,
        symbol: str,
        statement_type: str = "income_statement",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取财务报表数据
        
        Args:
            symbol: 股票代码
            statement_type: 报表类型
                - income_statement: 利润表
                - balance_sheet: 资产负债表  
                - cash_flow: 现金流量表
        
        Returns:
            pd.DataFrame: 财务报表数据
        """
        self._ensure_client()
        
        ts_code = self._normalize_symbol(symbol)
        
        try:
            if statement_type == "income_statement":
                df = self._client.income(ts_code=ts_code)
            elif statement_type == "balance_sheet":
                df = self._client.balancesheet(ts_code=ts_code)
            elif statement_type == "cash_flow":
                df = self._client.cashflow(ts_code=ts_code)
            else:
                raise ValueError(f"Unknown statement type: {statement_type}")
            
            return df
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch financial data for {symbol}: {str(e)}")
    
    def get_valuation(
        self,
        symbol: str,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取估值数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            pd.DataFrame: 估值数据
        """
        self._ensure_client()
        
        ts_code = self._normalize_symbol(symbol)
        
        try:
            df = self._client.daily_basic(
                ts_code=ts_code,
                trade_date=datetime.now().strftime("%Y%m%d")
            )
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch valuation for {symbol}: {str(e)}")
    
    def get_dividend(
        self,
        symbol: str,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取分红送转数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            pd.DataFrame: 分红送转数据
        """
        self._ensure_client()
        
        ts_code = self._normalize_symbol(symbol)
        
        try:
            df = self._client.dividend(ts_code=ts_code)
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch dividend for {symbol}: {str(e)}")
    
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
            symbol: 指数代码 (如 "000001.SH" 上证指数)
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.DataFrame: 指数数据
        """
        self._ensure_client()
        
        # 标准化
        index_code = symbol.replace(".SH", "").replace(".SZ", "")
        index_code = f"{index_code}.SH" if index_code.startswith(("000", "399")) else index_code
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")
        
        try:
            df = self._client.index_daily(
                ts_code=index_code,
                start_date=start_date,
                end_date=end_date
            )
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to fetch index data for {symbol}: {str(e)}")
    
    def search_symbol(self, keyword: str, **kwargs) -> List[Dict[str, str]]:
        """
        搜索股票
        
        Args:
            keyword: 搜索关键词
        
        Returns:
            List[Dict]: 匹配的股票列表
        """
        self._ensure_client()
        
        try:
            # 获取所有股票列表
            df = self._client.stock_basic(
                ts_code="",
                list_status="L",
                fields="ts_code,name,area,industry,market"
            )
            
            # 模糊搜索
            mask = df["name"].str.contains(keyword, na=False) | \
                   df["ts_code"].str.contains(keyword, na=False)
            df = df[mask]
            
            limit = kwargs.get("limit", 20)
            df = df.head(limit)
            
            return df.to_dict("records")
            
        except Exception as e:
            raise RuntimeError(f"Failed to search symbol {keyword}: {str(e)}")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码为 tushare 格式"""
        symbol = symbol.strip().upper().replace("-", "")
        
        # 已经是 000001.SZ 格式
        if "." in symbol:
            return symbol
        
        # 根据前缀添加后缀
        if symbol.startswith("6") or symbol.startswith("688"):
            return f"{symbol}.SH"
        elif symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        elif symbol.startswith("4") or symbol.startswith("8"):
            return f"{symbol}.BJ"
        
        return symbol
    
    def _period_to_tushare(self, period: str) -> str:
        """转换周期为 tushare 格式"""
        mapping = {
            "daily": "D",
            "weekly": "W",
            "monthly": "M",
            "yearly": "Y",
        }
        return mapping.get(period, "D")


def get_provider(credentials: Optional[Any] = None) -> TushareProvider:
    """创建 Tushare Provider 实例"""
    return TushareProvider(credentials)
