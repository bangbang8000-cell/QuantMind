import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.services.signal_readiness_service import (
    signal_readiness_service,
)



def _build_check(key: str, label: str, passed: bool, detail: str) -> dict[str, Any]:


    return {
        "key": key,
        "label": label,
        "passed": bool(passed),
        "detail": detail,
    }


def _check_local_market_data_freshness(expected_trade_date: date) -> tuple[bool, str]:
    """本地 quantdb 行情是否已覆盖到目标交易日。

    替代原「stream 实时行情新鲜度」检查：模拟盘撮合只读本地 parquet，
    实时行情服务不再是依赖项。
    """
    from backend.services.trade.simulation.services.local_market_data import (
        get_local_market_data,
    )

    latest = get_local_market_data().latest_trade_date()
    if latest is None:
        return False, "本地 quantdb 无任何行情分区，请先执行日线同步"
    if latest < expected_trade_date:
        return (
            False,
            f"本地行情最新交易日 {latest} 落后于目标 {expected_trade_date}，请先执行日线同步",
        )
    return True, f"本地行情已覆盖至 {latest}"


def _previous_trading_day(today: date, market: str = "A") -> date:
    market_upper = (market or "A").upper()
    if market_upper == "CRYPTO":
        return today - timedelta(days=1)
    try:
        import exchange_calendars as xcals

        _MARKET_XCAL = {"A": "XSHG", "HK": "XHKG", "US": "XNYS"}
        calendar = xcals.get_calendar(_MARKET_XCAL.get(market_upper, "XSHG"))
        session = calendar.date_to_session(today, direction="previous")
        prev_session = calendar.previous_session(session)
        return prev_session.date()
    except Exception:
        candidate = today - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate


def _check_inference_model_exists() -> tuple[bool, str]:
    """检查推理模型文件是否存在，不查询数据库。"""
    production_dir = Path(
        os.getenv("MODELS_PRODUCTION", "/app/models/production/model_qlib")
    )
    if not production_dir.exists() or not production_dir.is_dir():
        return False, f"推理模型目录不存在: {production_dir}"
    try:
        model_files = [f for f in production_dir.iterdir() if f.is_file()]
    except Exception as exc:
        return False, f"推理模型目录读取失败: {exc}"
    if not model_files:
        return False, f"推理模型目录为空: {production_dir}"
    return (
        True,
        f"推理模型已存在 (model_dir={production_dir}, files={len(model_files)})",
    )


async def run_trading_readiness_precheck(
    db: AsyncSession,
    *,
    mode: str,
    redis_client,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    normalized_mode = str(mode or "SIMULATION").strip().upper()
    if normalized_mode != "SIMULATION":
        raise ValueError(
            f"实盘交易已下线（政策原因），仅支持 SIMULATION。收到 mode={mode}"
        )

    checks: list[dict[str, Any]] = []

    expected_trade_date = _previous_trading_day(date.today())

    try:
        redis_ok = bool(redis_client.ping())
        checks.append(
            _build_check(
                "redis",
                "Redis",
                redis_ok,
                "Redis 已连接" if redis_ok else "Redis 不可达",
            )
        )
    except Exception as exc:
        checks.append(_build_check("redis", "Redis", False, f"Redis 自检失败: {exc}"))

    try:
        await db.execute(text("SELECT 1"))
        checks.append(_build_check("db", "PostgreSQL", True, "数据库连接正常"))
    except Exception as exc:
        checks.append(_build_check("db", "PostgreSQL", False, f"数据库自检失败: {exc}"))

    # 信号就绪状态检查（合并了信号链路启用检查）
    try:
        signal_readiness = await signal_readiness_service.evaluate(
            db,
            redis_client=redis_client,
            tenant_id=tenant_id,
            user_id=user_id,
            mode=normalized_mode,
        )
    except Exception as exc:
        signal_readiness = {
            "available": False,
            "status": "check_error",
            "message": f"读取默认模型信号就绪状态失败: {exc}",
            "trading_permission": "blocked"
            if normalized_mode == "REAL"
            else "observe_only",
            "blocking": normalized_mode == "REAL",
        }
        await db.rollback()
    signal_passed = not bool(signal_readiness.get("blocking"))
    checks.append(
        _build_check(
            "signal_readiness",
            "默认模型信号可交易",
            signal_passed,
            (
                str(signal_readiness.get("message") or "默认模型信号状态正常")
                if signal_readiness.get("available")
                else (
                    f"[阻断] {signal_readiness.get('message')}"
                    if signal_readiness.get("blocking")
                    else f"[观察态] {signal_readiness.get('message')}"
                )
            ),
        )
    )

    # 默认模型检测（检查用户是否配置了默认模型）
    try:
        from backend.shared.model_registry import model_registry_service

        default_model = await model_registry_service.get_default_model(
            tenant_id=tenant_id,
            user_id=user_id,
        )
        model_configured = bool(default_model)
        checks.append(
            _build_check(
                "default_model_configured",
                "默认模型已配置",
                model_configured,
                (
                    f"默认模型已配置 (model_id={default_model.get('model_id')})"
                    if model_configured
                    else "未配置默认模型，请先在模型管理中设置默认模型"
                ),
            )
        )
    except Exception as exc:
        checks.append(
            _build_check(
                "default_model_configured",
                "默认模型已配置",
                False,
                f"default_model_check_error={exc}",
            )
        )

    try:
        model_ok, model_detail = _check_inference_model_exists()
        # SIMULATION 模式推理模型仅警告，允许用户先配置系统
        checks.append(
            _build_check(
                "inference_database_ready",
                "推理模型已就绪",
                True,  # 仅警告，不阻断
                model_detail if model_ok else f"[WARNING] {model_detail}",
            )
        )
    except Exception as exc:
        checks.append(
            _build_check(
                "inference_database_ready",
                "推理模型已就绪",
                True,  # 仅警告，不阻断
                f"[WARNING] model_check_error={exc}",
            )
        )

    try:
        from backend.services.trade.sandbox.manager import sandbox_manager

        workers = list(getattr(sandbox_manager, "_workers", {}).values())
        worker_total = len(workers)
        alive_total = sum(1 for proc in workers if bool(proc and proc.is_alive()))
        pool_ok = alive_total > 0
        checks.append(
            _build_check(
                "simulation_sandbox_pool",
                "模拟盘进程池",
                pool_ok,
                (
                    f"进程池可用（alive={alive_total}/{worker_total}）"
                    if pool_ok
                    else "进程池不可用（无存活 worker）"
                ),
            )
        )
    except Exception as exc:
        checks.append(
            _build_check(
                "simulation_sandbox_pool",
                "模拟盘进程池",
                False,
                f"process_pool_error={exc}",
            )
        )

    try:
        ok, detail = _check_local_market_data_freshness(expected_trade_date)
        checks.append(
            _build_check(
                "local_market_data_freshness",
                "本地行情数据已就绪",
                ok,
                detail,
            )
        )
    except Exception as exc:
        checks.append(
            _build_check(
                "local_market_data_freshness",
                "本地行情数据已就绪",
                False,
                f"local_market_probe_error={exc}",
            )
        )
    return {
        "passed": all(bool(item.get("passed")) for item in checks),
        "checked_at": datetime.now().isoformat(),
        "items": checks,
        "signal_readiness": signal_readiness,
        "trading_permission": signal_readiness.get("trading_permission"),
    }
