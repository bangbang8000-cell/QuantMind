"""Market analysis schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateSectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector_id: str = Field(min_length=1, max_length=64)
    sector_type: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=32)
    parent_sector_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sector_id: str
    sector_type: str
    name: str
    code: str
    parent_sector_id: str | None
    metadata_json: dict[str, Any]


class SectorMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: str
    sector_id: str
    avg_pct_change: float | None
    median_pct_change: float | None
    total_market_cap: float | None
    avg_turnover_rate: float | None
    advance_count: int | None
    decline_count: int | None
    flat_count: int | None
    net_inflow: float | None
    sentiment_score: float | None
    sentiment_label: str | None
    details: dict[str, Any]


class AnomalyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    anomaly_id: str
    trade_date: str
    anomaly_type: str
    sector_id: str | None
    instrument: str | None
    severity: str
    title: str
    description: str
    details: dict[str, Any]
    created_at: str


class HeatmapItem(BaseModel):
    sector_id: str
    name: str
    sector_type: str
    avg_pct_change: float | None
    sentiment_score: float | None
    sentiment_label: str | None
    advance_count: int | None
    decline_count: int | None
    net_inflow: float | None


class HeatmapResponse(BaseModel):
    trade_date: str
    items: list[HeatmapItem]


class MoneyFlowPeriodItem(BaseModel):
    id: str
    name: str
    symbol: str | None = None
    pct_change: float = 0.0
    net_inflow: float = 0.0
    main_ratio: float = 0.0
    super_large: float = 0.0
    large: float = 0.0
    medium: float = 0.0
    small: float = 0.0
    trend_20d: list[float] = Field(default_factory=list)


class MoneyFlowPeriodResponse(BaseModel):
    trade_date: str
    period: str  # '1d' | '3d' | '5d' | '10d' | '20d'
    dimension: str  # 'sector' | 'stock'
    items: list[MoneyFlowPeriodItem]


class MarketBreadthResponse(BaseModel):
    trade_date: str
    advance_count: int = 0
    decline_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    total_turnover_yi: float = 0.0
    exploded_ratio: float = 0.0  # 炸板率 %
    profit_effect_score: float = 50.0  # 赚钱效应指数 0-100
    profit_effect: float = 50.0  # 前端字段别名（上涨占比 %）
    limit_up_broken_ratio: float = 0.0  # 前端字段别名（炸板率 %）


class HeatmapSectorItem(BaseModel):
    name: str
    value: float = 0.0  # 成交额/市值权重 (亿元)
    pct_change: float = 0.0  # 涨跌幅 %
    leader: str = ""  # 领涨股
    leader_pct: float = 0.0  # 领涨股涨幅 %

