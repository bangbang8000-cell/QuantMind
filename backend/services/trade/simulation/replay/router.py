"""时光回放 API 端点。

POST   /sessions              创建回放会话（后台生成信号，轮询进度）
GET    /sessions              列出当前用户的会话
GET    /sessions/{id}         查看会话详情 + 进度
POST   /sessions/{id}/step    单步推演（执行下一个交易日）
DELETE /sessions/{id}         丢弃会话
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.deps import AuthContext, get_auth_context, get_db
from backend.services.trade.simulation.models.replay import (
    ReplaySession,
    ReplayStatus,
)
from backend.services.trade.simulation.replay.account import ReplayAccountManager
from backend.services.trade.simulation.replay.day_runner import ReplayDayRunner
from backend.services.trade.simulation.replay.signal_generator import (
    ReplaySignalGenerator,
)
from backend.services.trade.simulation.services.local_market_data import (
    get_local_market_data,
)
from backend.shared.database_manager_v2 import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/replay", tags=["Replay"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str = Field(default="", max_length=128, description="会话名称")
    model_id: str | None = Field(default=None, description="模型 ID，空则用主模型")
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    start_date: date = Field(description="回放起始日（含）")
    end_date: date = Field(description="回放结束日（含）")
    auto_trade: bool = Field(default=True, description="S1 仅支持自动交易")
    stop_loss_pct: float | None = Field(default=None, ge=0, le=1)


class StepRequest(BaseModel):
    approved_orders: list[dict[str, Any]] | None = Field(
        default=None,
        description="手动模式下的确认委托列表（S1 暂不使用）",
    )


class SessionResponse(BaseModel):
    session_id: str
    name: str
    status: str
    model_id: str | None
    initial_cash: float
    start_date: str
    end_date: str
    cursor_date: str | None
    next_date: str | None
    sessions_total: int
    sessions_done: int
    auto_trade: bool
    stop_loss_pct: float | None
    signal_progress: dict[str, Any]
    error_message: str | None


class StepResponse(BaseModel):
    trade_date: str
    signal_count: int
    filled: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    stop_loss_fills: list[dict[str, Any]]
    account: dict[str, Any]
    snapshot: dict[str, Any]
    error: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_to_response(s: ReplaySession) -> SessionResponse:
    return SessionResponse(
        session_id=str(s.session_id),
        name=s.name,
        status=s.status.value,
        model_id=s.model_id,
        initial_cash=s.initial_cash,
        start_date=s.start_date.isoformat(),
        end_date=s.end_date.isoformat(),
        cursor_date=s.cursor_date.isoformat() if s.cursor_date else None,
        next_date=s.next_date.isoformat() if s.next_date else None,
        sessions_total=s.sessions_total,
        sessions_done=s.sessions_done,
        auto_trade=s.auto_trade,
        stop_loss_pct=s.stop_loss_pct,
        signal_progress=s.signal_progress or {},
        error_message=s.error_message,
    )


def _compute_next_date(
    cursor: date | None, start: date, end: date, sessions: list[int]
) -> date | None:
    """从 cursor 推算下一个交易日。cursor=None 时返回 start。"""
    if cursor is None:
        start_int = int(start.strftime("%Y%m%d"))
        on_or_after = [d for d in sessions if d >= start_int]
        if not on_or_after:
            return None
        nxt = on_or_after[0]
    else:
        cursor_int = int(cursor.strftime("%Y%m%d"))
        after = [d for d in sessions if d > cursor_int]
        if not after:
            return None
        nxt = after[0]

    end_int = int(end.strftime("%Y%m%d"))
    if nxt > end_int:
        return None
    return date(nxt // 10000, (nxt % 10000) // 100, nxt % 100)


def _count_sessions(start: date, end: date, sessions: list[int]) -> int:
    s = int(start.strftime("%Y%m%d"))
    e = int(end.strftime("%Y%m%d"))
    return sum(1 for d in sessions if s <= d <= e)


# ---------------------------------------------------------------------------
# Background signal generation
# ---------------------------------------------------------------------------


async def _run_signal_generation(
    session_id: uuid.UUID,
    model_id: str | None,
    start_date: date,
    end_date: date,
) -> None:
    """后台任务：预生成信号并更新会话状态。

    CPU 密集部分（parquet 读取 + 模型推理）在线程池中执行，
    DB 写入在主事件循环中异步执行。
    """
    gen = ReplaySignalGenerator(model_id=model_id)

    # Phase 1: CPU 密集 — 在线程池中执行
    loop = asyncio.get_event_loop()
    predict_result = await loop.run_in_executor(
        None,
        gen.predict_all,
        session_id,
        start_date,
        end_date,
    )

    # Phase 2: DB 写入 — 异步
    async with get_session(read_only=False) as db:
        persist_result = await gen.persist_all(db, session_id, predict_result)

    # Phase 3: 更新会话状态
    async with get_session(read_only=False) as db:
        row = (
            (
                await db.execute(
                    select(ReplaySession).where(ReplaySession.session_id == session_id)
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return

        if persist_result.get("errors"):
            row.status = ReplayStatus.FAILED
            row.error_message = "; ".join(persist_result["errors"][:5])
        else:
            row.status = ReplayStatus.READY
            row.signal_progress = {
                "done": persist_result["total_days"],
                "total": persist_result["total_days"],
                "total_signals": persist_result["total_signals"],
            }
        await db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def create_session(
    req: CreateSessionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """创建回放会话。信号在后台生成，前端轮询 GET /sessions/{id} 看进度。"""
    if req.start_date >= req.end_date:
        raise HTTPException(400, "start_date 必须 < end_date")

    market_data = get_local_market_data()
    sessions = market_data._sessions()
    if not sessions:
        raise HTTPException(503, "本地行情数据不可用")

    total_sessions = _count_sessions(req.start_date, req.end_date, sessions)
    if total_sessions == 0:
        raise HTTPException(400, "区间内无交易日")

    next_date = _compute_next_date(None, req.start_date, req.end_date, sessions)

    row = ReplaySession(
        tenant_id=auth.tenant_id,
        user_id=int(auth.user_id) if auth.user_id.isdigit() else 0,
        name=req.name,
        model_id=req.model_id,
        strategy_params=req.strategy_params,
        initial_cash=req.initial_cash,
        start_date=req.start_date,
        end_date=req.end_date,
        next_date=next_date,
        sessions_total=total_sessions,
        sessions_done=0,
        status=ReplayStatus.GENERATING,
        signal_progress={"done": 0, "total": total_sessions},
        auto_trade=req.auto_trade,
        stop_loss_pct=req.stop_loss_pct,
    )
    db.add(row)
    await db.flush()

    # 初始化回放账户
    accounts = ReplayAccountManager(session_id=row.session_id)
    await accounts.init(initial_cash=req.initial_cash)

    await db.commit()

    # 后台生成信号
    asyncio.create_task(
        _run_signal_generation(
            session_id=row.session_id,
            model_id=req.model_id,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    )

    return _session_to_response(row)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的回放会话。"""
    uid = int(auth.user_id) if auth.user_id.isdigit() else 0
    rows = (
        (
            await db.execute(
                select(ReplaySession)
                .where(
                    ReplaySession.tenant_id == auth.tenant_id,
                    ReplaySession.user_id == uid,
                )
                .order_by(ReplaySession.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_session_to_response(r) for r in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_detail(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """查看会话详情 + 信号生成进度。"""
    row = (
        (
            await db.execute(
                select(ReplaySession).where(ReplaySession.session_id == session_id)
            )
        )
        .scalars()
        .first()
    )
    if not row:
        raise HTTPException(404, "会话不存在")
    return _session_to_response(row)


@router.post("/sessions/{session_id}/step", response_model=StepResponse)
async def step_session(
    session_id: uuid.UUID,
    req: StepRequest | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """单步推演：执行下一个交易日。stepping 状态返回 409 防连点。"""
    row = (
        (
            await db.execute(
                select(ReplaySession).where(ReplaySession.session_id == session_id)
            )
        )
        .scalars()
        .first()
    )
    if not row:
        raise HTTPException(404, "会话不存在")

    if row.status == ReplayStatus.STEPPING:
        raise HTTPException(409, "正在执行中，请勿重复点击")
    if row.status == ReplayStatus.GENERATING:
        raise HTTPException(409, "信号生成中，请等待")
    if row.status in (
        ReplayStatus.FINISHED,
        ReplayStatus.FAILED,
        ReplayStatus.DISCARDED,
    ):
        raise HTTPException(400, f"会话已终止（{row.status.value}）")

    if row.next_date is None:
        row.status = ReplayStatus.FINISHED
        await db.commit()
        raise HTTPException(400, "已到达回放终点")

    # 标记 stepping
    row.status = ReplayStatus.STEPPING
    await db.commit()

    try:
        accounts = ReplayAccountManager(session_id=session_id)
        runner = ReplayDayRunner()
        result = await runner.run_day(
            db=db,
            session_id=session_id,
            trade_date=row.next_date,
            tenant_id=row.tenant_id,
            user_id=str(row.user_id),
            accounts=accounts,
            strategy_params=row.strategy_params,
            stop_loss_pct=row.stop_loss_pct,
            approved_orders=(req.approved_orders if req else None),
        )
    except Exception as exc:
        row.status = ReplayStatus.FAILED
        row.error_message = str(exc)[:500]
        await db.commit()
        raise HTTPException(500, f"推演失败: {exc}") from None

    # 更新游标
    market_data = get_local_market_data()
    sessions = market_data._sessions()
    row.cursor_date = row.next_date
    row.sessions_done += 1
    row.next_date = _compute_next_date(
        row.cursor_date, row.start_date, row.end_date, sessions
    )
    row.status = ReplayStatus.READY if row.next_date else ReplayStatus.FINISHED
    await db.commit()

    return StepResponse(
        trade_date=result.trade_date.isoformat(),
        signal_count=result.signal_count,
        filled=result.filled,
        rejected=result.rejected,
        stop_loss_fills=result.stop_loss_fills,
        account=result.account,
        snapshot=result.snapshot,
        error=result.error,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """丢弃会话：CASCADE 删除所有关联数据 + 清除 Redis 账户。"""
    row = (
        (
            await db.execute(
                select(ReplaySession).where(ReplaySession.session_id == session_id)
            )
        )
        .scalars()
        .first()
    )
    if not row:
        raise HTTPException(404, "会话不存在")

    # 清除 Redis 账户
    accounts = ReplayAccountManager(session_id=session_id)
    accounts.drop()

    # CASCADE 删除 DB 数据
    await db.delete(row)
    await db.commit()
