"""
期权数据路由
提供美股期权链数据
"""
from fastapi import APIRouter, Query
from typing import Optional
from openbb import obb

from ..utils.openbb_client import openbb_client

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/chains/{symbol}")
async def get_options_chains(
    symbol: str,
    expiration: Optional[str] = Query(None, description="到期日，格式：YYYY-MM-DD")
):
    """
    获取期权链数据

    返回指定股票的看涨和看跌期权数据

    包括：
    - 执行价格
    - 权利金
    - 隐含波动率
    - 持仓量
    - 成交量等
    """
    try:
        result = obb.derivatives.options.chains(
            symbol=symbol.upper(),
            expiration=expiration
        )

        return openbb_client.format_response(
            result.to_df(),
            meta={
                "symbol": symbol.upper(),
                "expiration": expiration
            }
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"symbol": symbol, "expiration": expiration}
        )


@router.get("/expirations/{symbol}")
async def get_options_expirations(symbol: str):
    """
    获取可用的期权到期日列表

    返回指定股票所有可交易的期权到期日
    """
    try:
        result = obb.derivatives.options.expirations(symbol=symbol.upper())

        return openbb_client.format_response(
            result.to_df(),
            meta={"symbol": symbol.upper()}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"symbol": symbol}
        )
