"""
OPENBB-CN 测试文件
"""

import pytest
from datetime import datetime, timedelta


class TestProviders:
    """Provider 测试"""
    
    def test_akshare_provider(self):
        """测试 AkShare Provider"""
        from openbb_core.providers import get_provider
        
        provider = get_provider("akshare")
        assert provider.name == "akshare"
        
        # 测试搜索
        results = provider.search_symbol("茅台")
        assert len(results) > 0
        print(f"Search results for '茅台': {len(results)} found")
    
    def test_easyquotation_provider(self):
        """测试 EasyQuotation Provider"""
        from openbb_core.providers import get_provider
        
        provider = get_provider("easyquotation")
        assert provider.name == "easyquotation"
        
        # 测试实时行情
        quote = provider.get_realtime_quote("600000")
        assert "price" in quote or "name" in quote
        print(f"Quote for 600000: {quote.get('name', 'N/A')}")
    
    def test_eastmoney_provider(self):
        """测试东方财富 Provider"""
        from openbb_core.providers import get_provider
        
        provider = get_provider("eastmoney")
        assert provider.name == "eastmoney"
        
        # 测试实时行情
        quote = provider.get_realtime_quote("000001.SZ")
        assert "price" in quote
        print(f"EastMoney quote: {quote.get('name', 'N/A')} @ {quote.get('price', 'N/A')}")


class TestStocksExtension:
    """股票扩展测试"""
    
    def setup_method(self):
        """设置测试"""
        from openbb_core.core import OpenBB
        self.obb = OpenBB()
    
    def test_historical_data(self):
        """测试历史数据获取"""
        # 获取上证指数历史数据
        df = self.obb.stocks.historical(
            "000001.SH",
            start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            provider="akshare"
        )
        assert len(df) > 0
        print(f"Historical data: {len(df)} rows")
        print(df.tail(3))
    
    def test_search(self):
        """测试股票搜索"""
        results = self.obb.stocks.search("腾讯")
        assert len(results) > 0
        print(f"Search '腾讯': {len(results)} results")
    
    def test_market_overview(self):
        """测试市场概览"""
        overview = self.obb.stocks.market_overview()
        assert "上证指数" in overview or "深证成指" in overview
        print("Market Overview:")
        for name, data in overview.items():
            print(f"  {name}: {data}")


class TestTechnicalAnalysis:
    """技术分析测试"""
    
    def setup_method(self):
        from openbb_core.core import OpenBB
        self.obb = OpenBB()
    
    def test_ma(self):
        """测试移动平均线"""
        df = self.obb.technical.ma("000001.SZ", period=20, provider="akshare")
        assert "ma20" in df.columns or "ma" in df.columns
        print(f"MA data: {len(df)} rows")
    
    def test_macd(self):
        """测试 MACD"""
        df = self.obb.technical.macd("000001.SZ", provider="akshare")
        assert len(df.columns) >= 3
        print(f"MACD columns: {df.columns.tolist()}")


class TestAIExtension:
    """AI 扩展测试"""
    
    def setup_method(self):
        from openbb_core.core import OpenBB
        self.obb = OpenBB()
    
    def test_ai_set_provider(self):
        """测试 AI Provider 设置"""
        import os
        
        # 检查是否有 API key
        has_key = any([
            os.environ.get("MINIMAX_API_KEY"),
            os.environ.get("ZHIPUAI_API_KEY"),
            os.environ.get("DASHSCOPE_API_KEY"),
            os.environ.get("DEEPSEEK_API_KEY"),
        ])
        
        if has_key:
            # 如果有 API key，测试设置
            if os.environ.get("MINIMAX_API_KEY"):
                self.obb.ai.set_provider("minimaxi")
                print("MiniMax provider set successfully")
        else:
            print("No AI API key found, skipping AI tests")


class TestAPI:
    """API 测试"""
    
    def test_api_import(self):
        """测试 API 导入"""
        from openbb_core.api import app
        assert app is not None
        print(f"API title: {app.title}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
