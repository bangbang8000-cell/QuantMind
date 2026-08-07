"""
全球宏观经济数据路由
提供美国及全球的宏观经济指标
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from openbb import obb

from ..utils.openbb_client import openbb_client

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/gdp")
async def get_gdp(
    country: str = Query("united_states", description="国家代码，默认美国"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    获取 GDP 数据

    支持国家：
    - united_states：美国
    - china：中国
    - japan：日本
    - germany：德国
    - 等
    """
    try:
        result = obb.economy.gdp(
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return openbb_client.format_response(
            result.to_df(),
            meta={"country": country, "indicator": "GDP"}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"country": country}
        )


@router.get("/cpi")
async def get_cpi(
    country: str = Query("united_states", description="国家代码"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    获取 CPI（消费者价格指数）数据

    用于衡量通货膨胀
    """
    try:
        result = obb.economy.cpi(
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return openbb_client.format_response(
            result.to_df(),
            meta={"country": country, "indicator": "CPI"}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"country": country}
        )


@router.get("/unemployment")
async def get_unemployment(
    country: str = Query("united_states", description="国家代码"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    获取失业率数据
    """
    try:
        result = obb.economy.unemployment(
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return openbb_client.format_response(
            result.to_df(),
            meta={"country": country, "indicator": "Unemployment"}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"country": country}
        )


@router.get("/interest-rate")
async def get_interest_rate(
    country: str = Query("united_states", description="国家代码"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    获取利率数据

    包括美联储利率等
    """
    try:
        result = obb.economy.interest_rate(
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return openbb_client.format_response(
            result.to_df(),
            meta={"country": country, "indicator": "Interest Rate"}
        )

    except Exception as e:
        return openbb_client.format_error(
            e,
            context={"country": country}
        )
