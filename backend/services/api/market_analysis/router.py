# mypy: disable-error-code=untyped-decorator

"""Market analysis API Router."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.services.api.user_app.middleware.auth import get_current_user
from backend.shared.database_manager_v2 import get_session

from . import quantdb_feed
from .domain import SectorConflictError, SectorNotFoundError
from .repository import MarketAnalysisRepository
from .schemas import (
    AnomalyResponse,
    CreateSectorRequest,
    HeatmapItem,
    HeatmapResponse,
    HeatmapSectorItem,
    MarketBreadthResponse,
    MoneyFlowPeriodItem,
    MoneyFlowPeriodResponse,
    SectorMetricsResponse,
    SectorResponse,
)
from .service import MarketAnalysisService
from .quantdb_realtime import QuantDBRealtimeUnavailable, get_snapshots

router = APIRouter(prefix="/api/v1/market-analysis", tags=["Market Analysis"])


@router.get("/realtime/snapshots")
async def get_realtime_snapshots(
    symbols: list[str] = Query(..., min_length=1, max_length=100),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Serve QuantDB snapshots without exposing its internal credential to clients."""
    _ = current_user
    try:
        return await get_snapshots(symbols)
    except QuantDBRealtimeUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QuantDB 实时行情源不可用",
        ) from exc


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SectorNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SectorConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---- Sectors ----

@router.post("/sectors", response_model=SectorResponse, status_code=201)
async def create_sector(
    request: CreateSectorRequest,
    current_user: dict = Depends(get_current_user),
) -> SectorResponse:
    try:
        async with get_session(read_only=False) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            sector = await service.create_sector(request)
            await session.commit()
            return SectorResponse.model_validate(sector)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sectors", response_model=list[SectorResponse])
async def list_sectors(
    sector_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> list[SectorResponse]:
    async with get_session(read_only=True) as session:
        service = MarketAnalysisService(MarketAnalysisRepository(session))
        items, _ = await service.list_sectors(sector_type=sector_type, limit=limit, offset=offset)
        return [SectorResponse.model_validate(s) for s in items]


@router.get("/sectors/{sector_id}", response_model=SectorResponse)
async def get_sector(
    sector_id: str,
    current_user: dict = Depends(get_current_user),
) -> SectorResponse:
    try:
        async with get_session(read_only=True) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            sector = await service.get_sector(sector_id)
            return SectorResponse.model_validate(sector)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sectors/{sector_id}/constituents")
async def list_constituents(
    sector_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    try:
        async with get_session(read_only=True) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            items = await service.list_constituents(sector_id)
            return [
                {"instrument": str(c.instrument), "weight": float(c.weight) if c.weight else None}
                for c in items
            ]
    except Exception as exc:
        raise _translate_error(exc) from exc


# ---- Metrics ----

@router.get("/sectors/{sector_id}/metrics/latest", response_model=SectorMetricsResponse)
async def get_latest_metrics(
    sector_id: str,
    current_user: dict = Depends(get_current_user),
) -> SectorMetricsResponse:
    try:
        async with get_session(read_only=True) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            m = await service.get_latest_metrics(sector_id)
            return SectorMetricsResponse(
                trade_date=str(m.trade_date),
                sector_id=str(m.sector_id),
                avg_pct_change=m.avg_pct_change,
                median_pct_change=m.median_pct_change,
                total_market_cap=m.total_market_cap,
                avg_turnover_rate=m.avg_turnover_rate,
                advance_count=m.advance_count,
                decline_count=m.decline_count,
                flat_count=m.flat_count,
                net_inflow=m.net_inflow,
                sentiment_score=m.sentiment_score,
                sentiment_label=m.sentiment_label,
                details=m.details if isinstance(m.details, dict) else {},
            )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sectors/{sector_id}/metrics/history", response_model=list[SectorMetricsResponse])
async def get_metrics_history(
    sector_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: dict = Depends(get_current_user),
) -> list[SectorMetricsResponse]:
    try:
        async with get_session(read_only=True) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            items = await service.get_metrics_history(
                sector_id, start_date=start_date, end_date=end_date
            )
            return [
                SectorMetricsResponse(
                    trade_date=str(m.trade_date),
                    sector_id=str(m.sector_id),
                    avg_pct_change=m.avg_pct_change,
                    median_pct_change=m.median_pct_change,
                    total_market_cap=m.total_market_cap,
                    avg_turnover_rate=m.avg_turnover_rate,
                    advance_count=m.advance_count,
                    decline_count=m.decline_count,
                    flat_count=m.flat_count,
                    net_inflow=m.net_inflow,
                    sentiment_score=m.sentiment_score,
                    sentiment_label=m.sentiment_label,
                    details=m.details if isinstance(m.details, dict) else {},
                )
                for m in items
            ]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/breadth", response_model=MarketBreadthResponse)
async def get_market_breadth(
    current_user: dict = Depends(get_current_user),
) -> MarketBreadthResponse:
    """获取大盘情绪温度计与赚钱效应指标（真实 QuantDB 聚合）"""
    data = quantdb_feed.get_market_breadth()
    return MarketBreadthResponse(**data)


@router.get("/heatmap")
async def get_heatmap(
    trade_date: date | None = Query(default=None),
    category: str = Query(default="shenwan", description="分类: shenwan 或 concept"),
    current_user: dict = Depends(get_current_user),
):
    """获取申万一级行业或热门概念热力矩形图（支持 QuantDB 真实聚合）"""
    real_items = quantdb_feed.get_sector_heatmap(category=category)
    if real_items:
        return {
            "trade_date": str(trade_date or date.today()),
            "category": category,
            "items": real_items,
        }

    if trade_date:
        async with get_session(read_only=True) as session:
            service = MarketAnalysisService(MarketAnalysisRepository(session))
            items = await service.get_heatmap(trade_date)
            return HeatmapResponse(
                trade_date=str(trade_date),
                items=[HeatmapItem(**item) for item in items],
            )
    return {"trade_date": str(date.today()), "category": category, "items": []}


# ---- Anomalies ----

@router.get("/anomalies", response_model=list[AnomalyResponse])
async def list_anomalies(
    trade_date: date | None = Query(default=None),
    anomaly_type: str | None = Query(default=None),
    sector_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> list[AnomalyResponse]:
    async with get_session(read_only=True) as session:
        service = MarketAnalysisService(MarketAnalysisRepository(session))
        items, _ = await service.list_anomalies(
            trade_date=trade_date,
            anomaly_type=anomaly_type,
            sector_id=sector_id,
            limit=limit,
            offset=offset,
        )
        return [AnomalyResponse.model_validate(a) for a in items]


# ---- Indices & Money Flow Extensions (QuantDB 真实驱动) ----

@router.get("/indices/overview")
async def get_indices_overview(
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """获取大盘核心指数 (上证, 深证, 创业板, 沪深300, 科创50) 快照（真实 QuantDB 数据）"""
    data = quantdb_feed.get_indices_overview()
    if data:
        return data
    return []


@router.get("/money-flow/stocks")
async def get_stock_money_flow(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """个股资金流向排行榜（真实 QuantDB L2 资金流）"""
    data = quantdb_feed.get_stock_money_flow(limit=limit)
    if data:
        return data
    return []


@router.get("/money-flow/sankey")
async def get_money_flow_sankey(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """获取主力资金流向桑基图数据 (Nodes & Links)"""
    data = quantdb_feed.get_money_flow_sankey()
    if data:
        return data
    return {"nodes": [], "links": []}


# ---- Tag Dual Lookup Endpoints (标签双向查询) ----

@router.get("/tags/by-tag")
async def get_stocks_by_tag(
    tag: str = Query(..., description="标签或板块名称，如：低空经济 / 华为概念 / 电子"),
    limit: int = Query(default=30, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """根据标签查个股：返回该标签/板块包含的成分股列表（真实 QuantDB 数据）"""
    items = quantdb_feed.get_stocks_by_tag(tag=tag, limit=limit)
    if items is not None:
        return {"tag": tag, "total": len(items), "items": items}
    return {"tag": tag, "total": 0, "items": []}


@router.get("/tags/by-stock")
async def get_tags_by_stock(
    symbol: str = Query(..., description="股票代码或名称，如：SH600036 或 招商银行"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """根据个股查标签：返回该股票归属的所有行业、概念、风格与因子标签（真实 QuantDB 数据）"""
    tags = quantdb_feed.get_tags_by_stock(symbol=symbol)
    if tags:
        return {"symbol": symbol, "tags": tags}
    return {"symbol": symbol, "tags": {}}


@router.get("/money-flow/period", response_model=MoneyFlowPeriodResponse)
async def get_money_flow_by_period(
    period: str = Query("1d", description="周期: 1d, 3d, 5d, 10d, 20d"),
    dimension: str = Query("sector", description="维度: sector 或 stock"),
    category: str = Query("shenwan", description="分类: shenwan 或 concept"),
    limit: int = Query(31, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> MoneyFlowPeriodResponse:
    """获取指定交易日周期 (1D/3D/5D/10D/20D) 的资金净流向排行榜（真实 QuantDB 数据）"""
    raw_items = quantdb_feed.get_money_flow_period(
        period=period,
        dimension=dimension,
        category=category,
        limit=limit,
    )
    today_str = datetime.now().strftime("%Y-%m-%d")
    if raw_items:
        items = [MoneyFlowPeriodItem(**it) for it in raw_items]
        return MoneyFlowPeriodResponse(
            trade_date=today_str,
            period=period,
            dimension=dimension,
            items=items,
        )
    return MoneyFlowPeriodResponse(
        trade_date=today_str,
        period=period,
        dimension=dimension,
        items=[],
    )
