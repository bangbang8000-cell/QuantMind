"""
OPENBB-CN REST API
基于 FastAPI 的 Web API 接口
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel
import pandas as pd

from openbb_core.core import OpenBB

# 创建 FastAPI 应用
app = FastAPI(
    title="OPENBB-CN API",
    description="面向中国市场的开源金融数据平台 API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 OpenBB 实例
obb = OpenBB()


# ============ Request/Response Models ============

class HistoricalDataRequest(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    period: str = "daily"
    adjust: str = "qfq"
    provider: str = "akshare"


class QuoteRequest(BaseModel):
    symbol: str
    provider: str = "easyquotation"


class AIDataRequest(BaseModel):
    message: str
    provider: Optional[str] = None
    temperature: float = 0.7


# ============ 股票数据接口 ============

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": "OPENBB-CN API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/api/v1/stocks/historical")
async def get_historical_data(
    symbol: str = Query(..., description="股票代码"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", description="K线周期"),
    adjust: str = Query("qfq", description="复权类型"),
    provider: str = Query("akshare", description="数据源"),
):
    """获取历史行情数据"""
    try:
        df = obb.stocks.historical(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjust=adjust,
            provider=provider,
        )
        return {
            "success": True,
            "data": df.to_dict("records"),
            "columns": df.columns.tolist(),
            "count": len(df),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stocks/quote")
async def get_quote(
    symbol: str = Query(..., description="股票代码"),
    provider: str = Query("easyquotation", description="数据源"),
):
    """获取实时行情"""
    try:
        data = obb.stocks.quote(symbol, provider=provider)
        return {
            "success": True,
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stocks/search")
async def search_stocks(
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, description="返回数量"),
    provider: str = Query("akshare", description="数据源"),
):
    """搜索股票"""
    try:
        results = obb.stocks.search(keyword, limit=limit, provider=provider)
        return {
            "success": True,
            "data": results,
            "count": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stocks/market-overview")
async def get_market_overview(
    provider: str = Query("akshare", description="数据源"),
):
    """获取市场概览"""
    try:
        overview = obb.stocks.market_overview(provider=provider)
        return {
            "success": True,
            "data": overview,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 技术分析接口 ============

@app.get("/api/v1/technical/ma")
async def get_ma(
    symbol: str = Query(..., description="股票代码"),
    period: int = Query(20, description="周期"),
    provider: str = Query("akshare", description="数据源"),
):
    """计算移动平均线"""
    try:
        df = obb.technical.ma(symbol, period=period, provider=provider)
        return {
            "success": True,
            "data": df.to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/technical/macd")
async def get_macd(
    symbol: str = Query(..., description="股票代码"),
    provider: str = Query("akshare", description="数据源"),
):
    """计算 MACD 指标"""
    try:
        df = obb.technical.macd(symbol, provider=provider)
        return {
            "success": True,
            "data": df.to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/technical/kdj")
async def get_kdj(
    symbol: str = Query(..., description="股票代码"),
    provider: str = Query("akshare", description="数据源"),
):
    """计算 KDJ 指标"""
    try:
        df = obb.technical.kdj(symbol, provider=provider)
        return {
            "success": True,
            "data": df.to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/technical/rsi")
async def get_rsi(
    symbol: str = Query(..., description="股票代码"),
    period: int = Query(14, description="周期"),
    provider: str = Query("akshare", description="数据源"),
):
    """计算 RSI 指标"""
    try:
        df = obb.technical.rsi(symbol, period=period, provider=provider)
        return {
            "success": True,
            "data": df.to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 基本面分析接口 ============

@app.get("/api/v1/fundamental/valuation")
async def get_valuation(
    symbol: str = Query(..., description="股票代码"),
    provider: str = Query("akshare", description="数据源"),
):
    """获取估值指标"""
    try:
        data = obb.fundamental.valuation(symbol, provider=provider)
        return {
            "success": True,
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/fundamental/dividend")
async def get_dividend(
    symbol: str = Query(..., description="股票代码"),
    provider: str = Query("akshare", description="数据源"),
):
    """获取分红信息"""
    try:
        df = obb.fundamental.dividend(symbol, provider=provider)
        return {
            "success": True,
            "data": df.to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ AI 助手接口 ============

@app.post("/api/v1/ai/chat")
async def ai_chat(request: AIDataRequest):
    """AI 对话"""
    try:
        if request.provider:
            obb.ai.set_provider(request.provider)
        
        response = obb.ai.chat(
            request.message,
            temperature=request.temperature,
        )
        return {
            "success": True,
            "response": response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ai/analyze")
async def ai_analyze(
    symbol: str = Query(..., description="股票代码"),
    analysis_type: str = Query("comprehensive", description="分析类型"),
    provider: Optional[str] = Query(None, description="AI Provider"),
):
    """AI 股票分析"""
    try:
        if provider:
            obb.ai.set_provider(provider)
        
        result = obb.ai.analyze_stock(symbol, analysis_type=analysis_type)
        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 健康检查 ============

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
