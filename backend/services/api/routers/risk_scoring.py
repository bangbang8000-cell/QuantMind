"""个股风险评分卡 API 路由。

GET  /api/v1/risk/score/{symbol}?trade_date=YYYY-MM-DD   单票评分
POST /api/v1/risk/scores                                  批量评分
     body: {"symbols": [...], "trade_date": "YYYY-MM-DD"}

trade_date 不传则取最新交易日；传了则取 ≤ 该日的最近交易日。

设计文档：docs/risk_scorecard_design_v2.md
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.services.api.risk_scoring import (
    compute_risk_score,
    compute_risk_scores_batch,
)
from backend.services.api.user_app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1/risk", tags=["RiskScoring"])


class RiskScoresRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, max_length=200)
    trade_date: date | None = Field(
        default=None,
        description="评分基于的交易日（YYYY-MM-DD），缺省取最新交易日",
    )


@router.get("/score/{symbol}")
async def get_risk_score(
    symbol: str,
    trade_date: date | None = Query(None, description="评分基于的交易日，缺省取最新"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    _ = current_user
    data = await compute_risk_score(symbol, trade_date)
    return {"code": 200, "data": data}


@router.post("/scores")
async def get_risk_scores(
    req: RiskScoresRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    _ = current_user
    data = await compute_risk_scores_batch(req.symbols, req.trade_date)
    return {"code": 200, "data": {"items": data, "count": len(data)}}
