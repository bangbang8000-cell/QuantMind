"""
OpenBB API Service - 全球金融市场数据服务

提供美股、加密货币、期权、宏观经济等数据的 RESTful API 接口
基于 OpenBB Platform 构建，支持与 AkShare 服务互补使用
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .routes import equity, macro, crypto, options

# 创建 FastAPI 应用
app = FastAPI(
    title="OpenBB API Service",
    description="全球金融市场数据 API - 美股、期权、加密货币、宏观经济数据",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(equity.router)
app.include_router(macro.router)
app.include_router(crypto.router)
app.include_router(options.router)


@app.get("/")
async def root():
    """API 根路径 - 服务信息"""
    return {
        "service": "OpenBB API Service",
        "version": "1.0.0",
        "status": "running",
        "description": "全球金融市场数据服务",
        "features": [
            "美股历史数据和实时报价",
            "全球宏观经济指标",
            "加密货币价格数据",
            "美股期权链数据"
        ],
        "endpoints": {
            "equity": "/equity/*",
            "macro": "/macro/*",
            "crypto": "/crypto/*",
            "options": "/options/*"
        },
        "docs": {
            "swagger": "/docs",
            "redoc": "/redoc"
        }
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "openbb-api"
    }


@app.get("/info")
async def info():
    """服务信息和示例"""
    return {
        "service": "OpenBB API Service",
        "port": 8001,
        "examples": {
            "美股历史数据": "/equity/historical/AAPL?start_date=2026-01-01&end_date=2026-02-24",
            "美股实时报价": "/equity/quote/TSLA",
            "公司信息": "/equity/profile/MSFT",
            "股票搜索": "/equity/search?query=apple&limit=5",
            "美国 GDP": "/macro/gdp?country=united_states",
            "美国 CPI": "/macro/cpi?country=united_states",
            "比特币历史": "/crypto/historical/BTC?start_date=2026-01-01",
            "以太坊报价": "/crypto/quote/ETH",
            "期权链": "/options/chains/AAPL?expiration=2026-03-21",
            "期权到期日": "/options/expirations/AAPL"
        },
        "data_coverage": {
            "equity": "美国所有上市股票（NYSE, NASDAQ等）",
            "macro": "全球主要国家宏观经济数据",
            "crypto": "主流加密货币价格数据",
            "options": "美股期权链和希腊值"
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
