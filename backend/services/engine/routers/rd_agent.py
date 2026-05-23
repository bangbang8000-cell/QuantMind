"""RD-Agent 因子管理 REST API"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services.engine.qlib_app.services.rd_agent_persistence import (
    RDAgentFactorPersistence,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rd-agent", tags=["RD-Agent"])
persistence = RDAgentFactorPersistence()


@router.get("/factors")
async def list_factors(
    user_id: Optional[str] = Query(None, description="按用户过滤"),
    status: Optional[str] = Query(None, description="按状态过滤: pending/backtesting/completed/failed"),
    limit: int = Query(50, ge=1, le=200),
):
    """列出所有已生成的因子"""
    factors = await persistence.list_factors(user_id=user_id, status=status, limit=limit)
    return {"code": 200, "data": {"factors": factors, "total": len(factors)}}


@router.get("/factors/{factor_id}")
async def get_factor(factor_id: str):
    """获取单个因子详情"""
    factor = await persistence.get_factor(factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail=f"Factor {factor_id} not found")
    return {"code": 200, "data": factor}


@router.post("/factors/{factor_id}/backtest")
async def backtest_factor(
    factor_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """对 RD-Agent 因子发起回测"""
    factor = await persistence.get_factor(factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail=f"Factor {factor_id} not found")

    if not factor.get("factor_code"):
        raise HTTPException(status_code=400, detail="因子代码为空，无法回测")

    # 更新状态为回测中
    await persistence.update_factor_metrics(factor_id, status="backtesting")

    # TODO: 实际调用 Qlib 回测接口
    # 这里返回回测请求信息，异步回测通过状态轮询获取结果
    return {
        "code": 200,
        "data": {
            "factor_id": factor_id,
            "status": "backtesting",
            "message": f"回测已触发: {factor.get('factor_name')}",
        },
    }


@router.get("/stats")
async def get_stats():
    """RD-Agent 因子统计信息"""
    from backend.shared.database_manager_v2 import get_session
    from sqlalchemy import text

    async with get_session(read_only=True) as session:
        rows = await session.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COUNT(*) FILTER (WHERE status = 'backtesting') AS backtesting,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                AVG(ic_value) FILTER (WHERE ic_value IS NOT NULL) AS avg_ic,
                AVG(sharpe_ratio) FILTER (WHERE sharpe_ratio IS NOT NULL) AS avg_sharpe,
                MAX(ic_value) AS best_ic,
                MAX(sharpe_ratio) AS best_sharpe
            FROM rd_agent_factors
        """))
        row = rows.mappings().first()

    if not row:
        return {"code": 200, "data": {}}

    data = dict(row)
    for key in ("avg_ic", "best_ic", "avg_sharpe", "best_sharpe"):
        if data.get(key) is not None:
            data[key] = round(float(data[key]), 4)
    return {"code": 200, "data": data}
