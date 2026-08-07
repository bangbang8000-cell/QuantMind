"""
EastMoney (东方财富) Provider
集成东方财富数据源的 Provider 实现

东方财富是国内领先的财经门户网站，提供免费实时行情和资讯数据
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import requests
from datetime import datetime, timedelta

from openbb_core.providers.base import BaseProvider


class EastMoneyProvider(BaseProvider):
    """
    东方财富数据源 Provider
    
    支持的数据类型:
    - 实时行情
    - 历史K线
    - 资金流向
    - 融资融券
    - 龙虎榜
    - 新闻资讯
    """
    
    name = "eastmoney"
    description = "东方财富 - 实时行情和资讯"
    supported_requests = [
        "historical_data",
        "realtime_quote",
        "fund_flow",
        "news",
        "margin",
    ]
    
    # EastMoney API 基础地址
    BASE_URL = "https://push2.eastmoney.com"
    
    def __init__(self, credentials: Optional[Any] = None):
        super().__init__(credentials)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.eastmoney.com"
        })
    
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
            start_date: 开始日期
            end_date: 结束日期
            period: K线周期
            adjust: 复权类型
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        # 标准化代码
        secid = self._symbol_to_secid(symbol)
        
        # 周期映射
        period_map = {
            "daily": "101",
            "weekly": "102",
            "monthly": "103",
            "yearly": "104",
            "1min": "1",
            "5min": "5",
            "15min": "15",
            "30min": "30",
            "60min": "60",
        }
        
        # 复权映射
        adj_map = {
            "qfq": "2",
            "hfq": "1",
            "none": "0",
        }
        
        period_code = period_map.get(period, "101")
        adj_type = adj_map.get(adjust, "2")
        
        # 日期参数
        if start_date:
            start_date = start_date.replace("-", "")
        if end_date:
            end_date = end_date.replace("-", "")
        
        # API URL
        url = f"{self.BASE_URL}/api/qt/stock/kline/get"
        
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": period_code,
            "fqt": adj_type,
            "beg": start_date or "",
            "end": end_date or "20500101",
            "lmt": kwargs.get("limit", 1000000),
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["data"] is None or not data["data"].get("klines"):
                raise RuntimeError(f"No data returned for {symbol}")
            
            klines = data["data"]["klines"]
            
            # 解析数据
            records = []
            for kl in klines:
                parts = kl.split(",")
                records.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]) if len(parts) > 6 else 0,
                })
            
            df = pd.DataFrame(records)
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
        secid = self._symbol_to_secid(symbol)
        
        # 分离市场前缀和代码
        market, code = secid.split(".")
        
        url = f"{self.BASE_URL}/api/qt/stock/get"
        
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f170",
            "ut": "fa5fd1943c7b386f172d6893dbbd5d51",
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["data"] is None:
                raise RuntimeError(f"Symbol {symbol} not found")
            
            d = data["data"]
            
            return {
                "symbol": symbol,
                "name": d.get("f58", ""),
                "price": d.get("f43", 0) / 100,  # 最新价
                "open": d.get("f46", 0) / 100,    # 开盘价
                "high": d.get("f44", 0) / 100,    # 最高价
                "low": d.get("f45", 0) / 100,     # 最低价
                "volume": d.get("f47", 0),         # 成交量
                "amount": d.get("f48", 0),         # 成交额
                "bid": d.get("f50", 0) / 100,     # 买价
                "ask": d.get("f51", 0) / 100,     # 卖价
                "pct_change": d.get("f170", 0) / 100,  # 涨跌幅
                "change": d.get("f169", 0) / 100,     # 涨跌额
                "timestamp": datetime.now().isoformat(),
            }
            
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
        if not symbols:
            return pd.DataFrame()
        
        # 转换代码格式
        secids = [self._symbol_to_secid(s) for s in symbols]
        
        url = f"{self.BASE_URL}/api/qt/ulist/get"
        
        params = {
            "secids": ",".join(secids),
            "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f12,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
            "ut": "fa5fd1943c7b386f172d6893dbbd5d51",
            "fltt": "2",
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["data"] is None:
                return pd.DataFrame()
            
            records = []
            for item in data["data"]["diff"]:
                records.append({
                    "symbol": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "price": item.get("f2", 0) / 100 if item.get("f2") else 0,
                    "pct_change": item.get("f3", 0) / 100,
                    "change": item.get("f4", 0) / 100,
                    "volume": item.get("f5", 0),
                    "amount": item.get("f6", 0),
                    "open": item.get("f15", 0) / 100 if item.get("f15") else 0,
                    "high": item.get("f16", 0) / 100 if item.get("f16") else 0,
                    "low": item.get("f17", 0) / 100 if item.get("f17") else 0,
                    "turnover": item.get("f8", 0),
                    "pe": item.get("f9", 0) / 100 if item.get("f9") else 0,
                    "pb": item.get("f23", 0) / 100 if item.get("f23") else 0,
                })
            
            return pd.DataFrame(records)
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch realtime quotes: {str(e)}")
    
    def get_fund_flow(
        self,
        symbol: str,
        flow_type: str = "all",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取资金流向
        
        Args:
            symbol: 股票代码
            flow_type: 流向类型 (all/main/retail)
                - all: 全部
                - main: 主力
                - retail: 散户
        
        Returns:
            pd.DataFrame: 资金流向数据
        """
        secid = self._symbol_to_secid(symbol)
        
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/get"
        
        klt = "101"  # 日K
        fields = "f1,f2,f3,f7,f8,f10,f12"
        
        params = {
            "secid": secid,
            "fields1": fields,
            "klt": klt,
            "lmt": kwargs.get("limit", 60),
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["data"] is None:
                return pd.DataFrame()
            
            klines = data["data"].get("klines", [])
            
            records = []
            for kl in klines:
                parts = kl.split(",")
                records.append({
                    "date": parts[1],
                    "pct_change": float(parts[2]) if parts[2] else 0,
                    "net_inflow": float(parts[3]) if parts[3] else 0,
                    "main_net_inflow": float(parts[4]) if parts[4] else 0,
                    "retail_net_inflow": float(parts[5]) if parts[5] else 0,
                })
            
            return pd.DataFrame(records)
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch fund flow for {symbol}: {str(e)}")
    
    def get_news(
        self,
        symbol: Optional[str] = None,
        category: str = "all",
        **kwargs
    ) -> pd.DataFrame:
        """
        获取新闻资讯
        
        Args:
            symbol: 股票代码 (可选)
            category: 类别 (all/announcement/research)
        
        Returns:
            pd.DataFrame: 新闻数据
        """
        url = "https://np-anotice-eastmoney.com/api/security/ann"
        
        params = {
            "sr": "-1",
            "page_size": "20",
            "page_index": "1",
            "ann_type": "SHA,CYB,SZA,SHE,NSE",
            "client_source": "web",
        }
        
        if symbol:
            params["stock"] = self._symbol_to_secid(symbol)
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["data"] is None:
                return pd.DataFrame()
            
            records = []
            for item in data["data"]["list"]:
                records.append({
                    "title": item.get("title", ""),
                    "publish_time": item.get("publish_time", ""),
                    "category": item.get("notice_category", ""),
                    "symbol": item.get("security_code", ""),
                    "url": item.get("art_url", ""),
                })
            
            return pd.DataFrame(records)
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch news: {str(e)}")
    
    def search_symbol(self, keyword: str, **kwargs) -> List[Dict[str, str]]:
        """
        搜索股票
        
        Args:
            keyword: 搜索关键词
        
        Returns:
            List[Dict]: 匹配的股票列表
        """
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        
        params = {
            "input": keyword,
            "type": "14",
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": kwargs.get("limit", 20),
        }
        
        try:
            response = self._session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data["QuotationCodeTable"] is None:
                return []
            
            records = []
            for item in data["QuotationCodeTable"]["Data"]:
                records.append({
                    "symbol": item.get("Code", ""),
                    "name": item.get("Name", ""),
                    "market": item.get("MktNum", ""),
                    "type": item.get("SecurityType", ""),
                })
            
            return records
            
        except Exception as e:
            raise RuntimeError(f"Failed to search symbol {keyword}: {str(e)}")
    
    def _symbol_to_secid(self, symbol: str) -> str:
        """
        将股票代码转换为 EastMoney 的 secid 格式
        
        Args:
            symbol: 原始代码 (如 "000001.SZ" 或 "600000")
        
        Returns:
            str: secid 格式 (如 "0.000001" 或 "1.600000")
        """
        symbol = symbol.strip().upper().replace("-", "")
        
        # 已经是 secid 格式
        if "." in symbol:
            parts = symbol.split(".")
            code = parts[0]
            suffix = parts[1]
            
            if suffix == "SH":
                return f"1.{code}"
            elif suffix == "SZ":
                return f"0.{code}"
            return symbol
        
        # 根据前缀判断
        if symbol.startswith("6") or symbol.startswith("688"):
            return f"1.{symbol}"
        elif symbol.startswith(("0", "3")):
            return f"0.{symbol}"
        elif symbol.startswith("4") or symbol.startswith("8"):
            return f"0.{symbol}"  # 北交所
        
        return symbol


def get_provider(credentials: Optional[Any] = None) -> EastMoneyProvider:
    """创建 EastMoney Provider 实例"""
    return EastMoneyProvider(credentials)
