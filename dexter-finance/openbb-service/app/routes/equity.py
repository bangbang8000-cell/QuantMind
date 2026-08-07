"""
美股股票数据路由
提供美国股票市场的历史价格、报价等数据
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from openbb import obb

from ..utils.openbb_client import openbb_client

router = APIRouter(prefix="/equity", tags=["equity"])


@router.get("/historical/{symbol}")
async def get_equity_historical(
    symbol: str,
    start_date: Optional[str] = Query(
        None,
        description="开始日期，格式：YYYY-MM-DD，默认为30天前"
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期，格式：YYYY-MM-DD，默认为今天"
    ),
    interval: str = Query(
        "1d",
        description="数据间隔：1d(日线), 1h(小时), 5m(5分钟)等"
    )
):
    """
    获取美股历史价格数据

    支持的股票：
    - 纽交所（NYSE）：如 IBM, BAC
    - 纳斯达克（NASDAQ）：如 AAPL, MSFT, TSLA
    - 其他美国交易所

    示例：
    - AAPL：苹果公司
    - TSLA：特斯拉
    - MSFT：微软
    - GOOGL：谷歌
    """
    try:
        # 设置默认日期
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # 调用 OpenBB API
        result = obb.equity.price.historical(
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )

        # 格式化响应
        return openbb_client.format_response(
            result.to_df(),
            meta={
                "symbol": symbol.upper(),
                "start_date": start_date,
                "end_date": end_date,
                "interval": interval,
            }
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
            }
        )


@router.get("/quote/{symbol}")
async def get_equity_quote(symbol: str):
    """
    获取美股实时报价

    返回：
    - 最新价格
    - 涨跌幅
    - 成交量
    - 市值等信息
    """
    try:
        result = obb.equity.price.quote(symbol=symbol.upper())

        return openbb_client.format_response(
            result.to_df(),
            meta={"symbol": symbol.upper()}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"symbol": symbol}
        )


@router.get("/profile/{symbol}")
async def get_equity_profile(symbol: str):
    """
    获取公司基本信息

    返回：
    - 公司名称
    - 行业
    - 市值
    - 员工数
    - 公司描述等
    """
    try:
        result = obb.equity.profile(symbol=symbol.upper())

        return openbb_client.format_response(
            result.to_df(),
            meta={"symbol": symbol.upper()}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"symbol": symbol}
        )


@router.get("/search")
async def search_equity(
    query: str = Query(..., description="搜索关键词，如公司名称或股票代码"),
    limit: int = Query(10, description="返回结果数量")
):
    """
    搜索美股股票

    根据公司名称或代码搜索股票
    """
    try:
        result = obb.equity.search(query=query, limit=limit)

        return openbb_client.format_response(
            result.to_df(),
            meta={"query": query, "limit": limit}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"query": query}
        )
