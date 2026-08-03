from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SymbolsFeaturesRequest(BaseModel):
    symbols: list[str]


class BatchFeaturesRequest(BaseModel):
    """QuantDB 全量特征批量查询请求。

    fields 为可选投影：传入 camelCase 字段名（如 momRet5d）时只返回这些字段，
    用于表格/筛选场景大幅压缩响应体（371 字段 → 按需字段）。
    """

    symbols: list[str]
    fields: list[str] | None = None


class WatchlistAddRequest(BaseModel):
    run_id: str | None = None
    stock_name: str | None = None
    features_snapshot: dict[str, Any] | None = None


class PoolAddRequest(BaseModel):
    run_id: str | None = None
    stock_name: str | None = None
    model_id: str | None = None
    fusion_score: float | None = None
    thesis_summary: str | None = None
    features_snapshot: dict[str, Any] | None = None
