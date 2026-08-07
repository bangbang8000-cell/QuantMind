"""
加密货币数据路由
提供比特币、以太坊等加密货币的价格和市场数据
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from openbb import obb

from ..utils.openbb_client import openbb_client

router = APIRouter(prefix="/crypto", tags=["crypto"])


@router.get("/historical/{symbol}")
async def get_crypto_historical(
    symbol: str,
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    interval: str = Query("1d", description="数据间隔")
):
    """
    获取加密货币历史价格

    常用代码：
    - BTC：比特币
    - ETH：以太坊
    - BNB：币安币
    - SOL：Solana
    - XRP：瑞波币
    """
    try:
        # 设置默认日期
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        result = obb.crypto.price.historical(
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )

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
            context={"symbol": symbol}
        )


@router.get("/quote/{symbol}")
async def get_crypto_quote(symbol: str):
    """
    获取加密货币实时报价

    返回当前价格、24小时涨跌幅、成交量等
    """
    try:
        result = obb.crypto.price.quote(symbol=symbol.upper())

        return openbb_client.format_response(
            result.to_df(),
            meta={"symbol": symbol.upper()}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"symbol": symbol}
        )
