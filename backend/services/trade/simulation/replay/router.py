"""时光回放 API 端点。

POST   /sessions                   创建回放会话（后台生成信号，轮询进度）
GET    /sessions                   列出当前用户的会话
GET    /sessions/{id}              查看会话详情 + 进度
POST   /sessions/{id}/step         单步推演（执行下一个交易日）
DELETE /sessions/{id}              丢弃会话
GET    /strategy-templates         可选策略模板（含参数定义，供前端渲染表单）
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
from backend.services.trade.simulation.services.ashare_matcher import MatchConfig
from backend.services.trade.simulation.services.local_market_data import (
    get_local_market_data,
)
from backend.shared.database_manager_v2 import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/replay", tags=["Replay"])


def _match_config_from_params(strategy_params: dict[str, Any]) -> MatchConfig:
    """从 strategy_params 构造撮合配置（bug 8 fix）。

    回放默认按开盘价撮合：信号是昨收后算出来的，次日开盘才可交易。
    费率/滑点未指定时沿用 MatchConfig 的 A 股默认值。
    """
    defaults = MatchConfig(price_mode="open")
    return MatchConfig(
        price_mode=str(strategy_params.get("price_mode", defaults.price_mode)),
        slippage_bps=float(
            strategy_params.get("slippage_bps", defaults.slippage_bps)
        ),
        commission_rate=float(
            strategy_params.get("commission_rate", defaults.commission_rate)
        ),
        commission_min=float(
            strategy_params.get("commission_min", defaults.commission_min)
        ),
        stamp_duty_rate=float(
            strategy_params.get("stamp_duty_rate", defaults.stamp_duty_rate)
        ),
        transfer_fee_rate=float(
            strategy_params.get("transfer_fee_rate", defaults.transfer_fee_rate)
        ),
        lot_size=int(strategy_params.get("lot_size", defaults.lot_size)),
    )


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
    strategy_params: dict[str, Any] = {}


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
        strategy_params=s.strategy_params or {},
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

    try:
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
    except Exception as exc:
        # 兜底：任何阶段抛异常都必须把会话置为 FAILED，否则永久卡在 generating
        # （无超时、无重试端点，用户只能删会话重建）。
        logger.exception("回放信号生成失败 session=%s model=%s", session_id, model_id)
        try:
            async with get_session(read_only=False) as db:
                row = (
                    (
                        await db.execute(
                            select(ReplaySession).where(
                                ReplaySession.session_id == session_id
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if row is not None:
                    row.status = ReplayStatus.FAILED
                    row.error_message = f"信号生成失败: {exc}"[:500]
                    await db.commit()
        except Exception:
            logger.exception("写入 FAILED 状态也失败 session=%s", session_id)
        return

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

    # model_id 前置校验。注意不能用 _resolve_model_dir —— 它对无效 id 会静默
    # 回落到 model_qlib，用户以为在跑自选模型，实际跑的是默认模型。
    if req.model_id:
        import json as _json
        import os as _os
        from pathlib import Path as _Path

        _base = _Path(_os.getenv("MODELS_PRODUCTION", "/app/models/production"))
        _dir = _base / req.model_id
        if not _dir.is_dir():
            raise HTTPException(400, f"模型不存在: {req.model_id}")
        _meta_path = _dir / "metadata.json"
        if not _meta_path.is_file():
            raise HTTPException(400, f"模型缺少 metadata.json: {req.model_id}")
        # 校验模型文件真实可读 —— 断链 symlink 会让后台任务在预测阶段才炸
        try:
            _meta = _json.loads(_meta_path.read_text(encoding="utf-8"))
            _mf = _dir / str(_meta.get("model_file") or "model.lgb")
            if not _mf.exists():
                raise HTTPException(
                    400, f"模型文件不可读（可能是断链符号链接）: {_mf.name}"
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"模型元数据无法解析: {exc}") from None

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


async def _load_owned_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    auth: AuthContext,
) -> ReplaySession:
    """按 session_id 取会话，并校验 tenant/user 归属。

    bug 9 fix: 原先 GET/{id}、step、DELETE 都只按 session_id 查，
    任意用户可读写他人会话。
    """
    uid = int(auth.user_id) if str(auth.user_id).isdigit() else 0
    row = (
        (
            await db.execute(
                select(ReplaySession).where(
                    ReplaySession.session_id == session_id,
                    ReplaySession.tenant_id == auth.tenant_id,
                    ReplaySession.user_id == uid,
                )
            )
        )
        .scalars()
        .first()
    )
    if not row:
        raise HTTPException(404, "会话不存在")
    return row


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_detail(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """查看会话详情 + 信号生成进度。"""
    row = await _load_owned_session(db, session_id, auth)
    return _session_to_response(row)


@router.post("/sessions/{session_id}/step", response_model=StepResponse)
async def step_session(
    session_id: uuid.UUID,
    req: StepRequest | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """单步推演：执行下一个交易日。stepping 状态返回 409 防连点。"""
    row = await _load_owned_session(db, session_id, auth)

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
            initial_cash=float(row.initial_cash),
            match_config=_match_config_from_params(row.strategy_params or {}),
        )
    except Exception as exc:
        row.status = ReplayStatus.FAILED
        row.error_message = str(exc)[:500]
        await db.commit()
        raise HTTPException(500, f"推演失败: {exc}") from None

    # bug 3 fix: run_day 内部报错时不推进游标，否则会静默跳过一天、曲线断档
    if result.error:
        row.status = ReplayStatus.FAILED
        row.error_message = result.error[:500]
        await db.commit()
        raise HTTPException(500, f"推演失败: {result.error}")

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
    row = await _load_owned_session(db, session_id, auth)

    # 清除 Redis 账户
    accounts = ReplayAccountManager(session_id=session_id)
    accounts.drop()

    # CASCADE 删除 DB 数据
    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# 策略模板（供前端渲染「选策略」表单）
# ---------------------------------------------------------------------------


class StrategyTemplateParam(BaseModel):
    name: str
    description: str
    default: Any
    min: float | None = None
    max: float | None = None


class StrategyTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    difficulty: str
    params: list[StrategyTemplateParam]
    # 映射到 replay 可识别的 strategy_params（Qlib 口径 → replay 6 key）
    replay_params: dict[str, Any]


# Qlib 模板参数名 → replay strategy_params key
_PARAM_ALIAS = {
    "topk": "topk",
    "max_weight": "max_position_pct",
    "stop_loss": "stop_loss_pct",
}


def _to_replay_params(tpl: Any) -> dict[str, Any]:
    """把模板默认参数翻译成 replay 的 strategy_params。

    replay 的 RebalanceCalculator 只认 topk / weight_mode / custom_weights /
    min_score / max_position_pct / lot_size，Qlib 模板里的 n_drop、
    rebalance_days、signal 等在回放里没有对应语义，直接丢弃。
    """
    out: dict[str, Any] = {}
    for p in tpl.params or []:
        key = _PARAM_ALIAS.get(p.name)
        if key and p.default is not None:
            val = p.default
            # Qlib 的 stop_loss 是负数（-0.08 = 跌 8% 止损），
            # replay 的 stop_loss_pct 约束 ge=0 le=1，取绝对值
            if key == "stop_loss_pct":
                try:
                    val = abs(float(val))
                except (TypeError, ValueError):
                    continue
            out[key] = val
    # 按模板 id 推断权重模式
    tid = (tpl.id or "").lower()
    if "score_weighted" in tid:
        out["weight_mode"] = "score_weighted"
    elif "volatility" in tid:
        out["weight_mode"] = "score_weighted"
    else:
        out["weight_mode"] = "equal"
    return out


@router.get("/strategy-templates", response_model=list[StrategyTemplateResponse])
async def list_strategy_templates(
    auth: AuthContext = Depends(get_auth_context),
):
    """列出可用策略模板。复用 qlib_app 的模板加载器（单一数据源）。"""
    try:
        from backend.services.engine.qlib_app.services.strategy_templates import (
            get_all_templates,
        )
    except ImportError as exc:
        logger.warning("策略模板加载器不可用: %s", exc)
        raise HTTPException(503, "策略模板服务不可用") from None

    try:
        templates = get_all_templates()
    except Exception as exc:
        logger.error("读取策略模板失败: %s", exc)
        raise HTTPException(500, f"读取策略模板失败: {exc}") from None

    out: list[StrategyTemplateResponse] = []
    for tpl in templates:
        # 回放只支持 A 股（markets 空=全市场适用）
        if tpl.markets and "a_share" not in tpl.markets:
            continue
        out.append(
            StrategyTemplateResponse(
                id=tpl.id,
                name=tpl.name,
                description=tpl.description,
                category=tpl.category,
                difficulty=tpl.difficulty,
                params=[
                    StrategyTemplateParam(
                        name=p.name,
                        description=p.description,
                        default=p.default,
                        min=p.min,
                        max=p.max,
                    )
                    for p in (tpl.params or [])
                ],
                replay_params=_to_replay_params(tpl),
            )
        )
    return out
