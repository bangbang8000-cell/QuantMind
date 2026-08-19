# mypy: disable-error-code=untyped-decorator

"""Market analysis API Router."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.services.api.user_app.middleware.auth import get_current_user
from backend.shared.database_manager_v2 import get_session

from .domain import SectorConflictError, SectorNotFoundError
from .repository import MarketAnalysisRepository
from .schemas import (
    AnomalyResponse,
    CreateSectorRequest,
    HeatmapItem,
    HeatmapResponse,
    MoneyFlowPeriodItem,
    MoneyFlowPeriodResponse,
    SectorMetricsResponse,
    SectorResponse,
)
from .service import MarketAnalysisService
from . import quantdb_service as qdb

router = APIRouter(prefix="/api/v1/market-analysis", tags=["Market Analysis"])


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


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    trade_date: date = Query(...),
    current_user: dict = Depends(get_current_user),
) -> HeatmapResponse:
    async with get_session(read_only=True) as session:
        service = MarketAnalysisService(MarketAnalysisRepository(session))
        items = await service.get_heatmap(trade_date)
        return HeatmapResponse(
            trade_date=str(trade_date),
            items=[HeatmapItem(**item) for item in items],
        )


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


# ---- Indices & Money Flow Extensions ----


@router.get("/indices/overview")
async def get_indices_overview(
    trade_date: str | None = Query(default=None, description="YYYYMMDD，默认最新交易日"),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """大盘核心指数快照（QuantDB index_daily 最新交易日真实数据）。"""
    return qdb.indices_overview(trade_date=trade_date)


@router.get("/money-flow/stocks")
async def get_stock_money_flow(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """个股资金流向排行榜（l2 真实资金流；单位：元，数据截至 2026-02-27）。"""
    return qdb.stock_money_flow(limit=limit)


@router.get("/money-flow/sankey")
async def get_money_flow_sankey(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """主力/散户资金流向桑基图（l2 真实行业资金流，单位：元，截至 2026-02-27）。"""
    return qdb.money_flow_sankey()


# ---- Tag Dual Lookup Endpoints (标签双向查询) ----

@router.get("/tags/by-tag")
async def get_stocks_by_tag(
    tag: str = Query(..., description="标签或板块名称，如：低空经济 / 华为概念 / 电子"),
    limit: int = Query(default=30, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """根据标签查个股：QuantDB sector_members 真实成分股 + 最新涨跌幅。"""
    return qdb.stocks_by_tag(tag=tag, limit=limit)


@router.get("/tags/by-stock")
async def get_tags_by_stock(
    symbol: str = Query(..., description="股票代码或名称，如：600036.SH 或 招商银行"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """根据个股查标签：QuantDB 真实行业/概念归属。"""
    return qdb.tags_by_stock(symbol=symbol)


@router.get("/money-flow/period", response_model=MoneyFlowPeriodResponse)
async def get_money_flow_by_period(
    period: str = Query("1d", description="周期: 1d, 3d, 5d, 10d, 20d"),
    dimension: str = Query("sector", description="维度: sector 或 stock"),
    category: str = Query("shenwan", description="分类: shenwan 或 concept"),
    limit: int = Query(31, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> MoneyFlowPeriodResponse:
    """资金净流向排行榜（QuantDB l2 真实数据；单位：元）。

    ⚠️ l2_factors 停更 2026-02-27 且仅存单日分区：多周期选项不伪造，
    一律返回最新分区真实值，trade_date 即数据截止日。
    """
    raw = qdb.money_flow_period(period=period, dimension=dimension)
    items: list[MoneyFlowPeriodItem] = []
    for r in raw[:limit]:
        items.append(
            MoneyFlowPeriodItem(
                id=str(r.get("id", r.get("symbol", ""))),
                name=r.get("name", ""),
                symbol=r.get("symbol"),
                pct_change=float(r.get("pct_change") or 0.0),
                net_inflow=float(r.get("net_inflow") or 0.0),
                super_large=float(r.get("super_large") or 0.0),
                large=float(r.get("large") or 0.0),
                medium=float(r.get("medium") or 0.0),
                small=float(r.get("small") or 0.0),
                trend_20d=[],
            )
        )
    trade_date = raw[0]["trade_date"] if raw else str(datetime.now().strftime("%Y-%m-%d"))
    return MoneyFlowPeriodResponse(
        trade_date=trade_date,
        period=period,
        dimension=dimension,
        items=items,
    )



