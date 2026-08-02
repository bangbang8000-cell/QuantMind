import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from .real_trading_utils import *
from .real_trading_utils import (
    _check_inference_model_exists,
    _fetch_latest_real_account_snapshot,
    _normalize_identity,
    _parse_user_id,
    _upsert_preflight_snapshot,
)
from backend.services.trade.services.signal_readiness_service import (
    signal_readiness_service,
)
from backend.services.trade.services.trading_precheck_service import (
    _check_local_market_data_freshness,
    _previous_trading_day,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_FEATURE_PARQUET_DIR = Path(
    os.getenv("FEATURE_SNAPSHOT_DIR", "/app/db/feature_snapshots")
)


def _check_feature_parquet_coverage(
    expected_trade_date: date,
) -> tuple[bool, str, dict]:
    """推理特征 parquet 是否覆盖到目标交易日。

    只读 parquet 的 trade_date 列最大值，不加载全表（单年文件可达数 GB）。
    """
    path = _FEATURE_PARQUET_DIR / f"model_features_{expected_trade_date.year}.parquet"
    details = {"path": str(path), "expected_trade_date": expected_trade_date.isoformat()}
    if not path.exists():
        return False, f"特征 parquet 不存在: {path}", details

    import pandas as pd

    latest_raw = pd.read_parquet(path, columns=["trade_date"])["trade_date"].max()
    latest = pd.Timestamp(latest_raw).date()
    details["latest_trade_date"] = latest.isoformat()
    if latest < expected_trade_date:
        return (
            False,
            f"特征 parquet 最新交易日 {latest} 落后于目标 {expected_trade_date}，请先执行特征回补",
            details,
        )
    return True, f"特征 parquet 已覆盖至 {latest}", details


def _parse_snapshot_timestamp(raw: Any) -> float | None:
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc).timestamp()
        return raw.timestamp()
    if isinstance(raw, str):
        text_raw = raw.strip()
        if not text_raw:
            return None
        try:
            parsed = datetime.fromisoformat(text_raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _is_cn_trading_hours() -> bool:
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        now = datetime.now()
    return (
        now.weekday() < 5
        and ((now.hour == 9 and now.minute >= 15) or (10 <= now.hour < 15))
    )


@router.get("/preflight")
async def preflight_check(
    trading_mode: str = "SIMULATION",
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    模拟盘启动前自检：
    - Redis / PostgreSQL 连通性
    - 默认模型已配置且模型文件可加载
    - 本地 quantdb 行情与特征 parquet 覆盖到最新交易日
    - 沙箱进程池与模拟盘关键表
    """
    resolved_user_id, resolved_tenant_id = _normalize_identity(auth, user_id=user_id, tenant_id=tenant_id)
    mode = str(trading_mode or "SIMULATION").strip().upper()
    if mode != "SIMULATION":
        raise HTTPException(
            status_code=400,
            detail=f"实盘交易已下线（政策原因），仅支持模拟盘。收到 trading_mode={mode}",
        )

    checks = []

    def add_check(
        key: str,
        label: str,
        ok: bool,
        required: bool,
        message: str,
        details: Optional[dict] = None,
    ):
        checks.append(
            {
                "key": key,
                "label": label,
                "ok": ok,
                "required": required,
                "message": message,
                "details": details or {},
            }
        )

    # 1) Redis
    try:
        redis_ok = bool(redis.client.ping())
        add_check(
            "redis",
            "Redis",
            redis_ok,
            True,
            "Redis 已连接" if redis_ok else "Redis 不可达",
        )
    except Exception as e:
        add_check("redis", "Redis", False, True, f"Redis 自检失败: {e}")

    # 2) DB
    try:
        await db.execute(text("SELECT 1"))
        add_check("db", "PostgreSQL", True, True, "数据库连接正常")
    except Exception as e:
        add_check("db", "PostgreSQL", False, True, f"数据库自检失败: {e}")
        await db.rollback()

    # 3) Internal Secret
    internal_secret = str(os.getenv("INTERNAL_CALL_SECRET", "")).strip()
    if internal_secret:
        add_check("internal_secret", "内部密钥", True, True, "INTERNAL_CALL_SECRET 已配置")
    else:
        add_check("internal_secret", "内部密钥", False, True, "缺少 INTERNAL_CALL_SECRET 配置")

    # 4) User ID 格式（执行链路要求可转 int）
    try:
        _parse_user_id(resolved_user_id)
        add_check("user_id", "用户标识", True, True, "用户标识格式合法")
    except HTTPException:
        add_check(
            "user_id",
            "用户标识",
            False,
            True,
            "当前用户ID不是数字，实盘执行链路可能失败",
        )

    try:
        signal_readiness = await signal_readiness_service.evaluate(
            db,
            redis_client=redis.client,
            tenant_id=resolved_tenant_id,
            user_id=resolved_user_id,
            mode=mode,
        )
    except Exception as exc:
        signal_readiness = {
            "available": False,
            "blocking": False,
            "trading_permission": "observe_only",
            "message": f"读取默认模型托管状态失败: {exc}",
        }
        await db.rollback()
    add_check(
        "signal_readiness",
        "默认模型信号可交易",
        not bool(signal_readiness.get("blocking")),
        bool(signal_readiness.get("blocking")),
        (
            str(signal_readiness.get("message") or "默认模型信号状态正常")
            if signal_readiness.get("available")
            else (
                f"[阻断] {signal_readiness.get('message')}"
                if signal_readiness.get("blocking")
                else f"[观察态] {signal_readiness.get('message')}"
            )
        ),
        signal_readiness,
    )
    add_check(
        "latest_signal_run",
        "最新推理批次",
        bool(signal_readiness.get("latest_run_id")),
        False,
        (
            f"latest_run_id={signal_readiness.get('latest_run_id')}"
            if signal_readiness.get("latest_run_id")
            else str(
                signal_readiness.get("message")
                or "[WARNING] 未检测到当前用户默认模型的最新完成推理"
            )
        ),
    )

    # 5) 账户快照（用于双向交易信用字段探测）
    account_report: dict | None = None
    try:
        account_snapshot = await _fetch_latest_real_account_snapshot(
            db,
            tenant_id=resolved_tenant_id,
            user_id=resolved_user_id,
        )
        if account_snapshot:
            account_report = account_snapshot.get("payload_json") or {}
            if not isinstance(account_report, dict):
                account_report = {}
    except Exception as e:
        logger.warning("读取实盘账户快照失败: %s", e)
        # 回滚事务以清除 aborted 状态，避免后续查询失败
        await db.rollback()

    # 7.1~7.4) 双向交易专属预检
    margin_enabled = bool(getattr(settings, "ENABLE_MARGIN_TRADING", False))
    add_check(
        "margin_trading_feature",
        "双向交易功能开关",
        True,  # 警告：不阻断启动
        False, # 不阻断
        "ENABLE_MARGIN_TRADING 已开启" if margin_enabled else "[WARNING] ENABLE_MARGIN_TRADING 未开启(部分双向策略可能无法下单)",
    )

    if margin_enabled:
        try:
            pool = get_margin_stock_pool_service(settings.MARGIN_STOCK_POOL_PATH)
            snapshot = pool.snapshot()
            add_check(
                "margin_stock_pool_loaded",
                "融资融券股票池",
                snapshot.record_count > 0,
                True,
                (
                    f"融资融券股票池已加载，共 {snapshot.record_count} 只股票"
                    if snapshot.record_count > 0
                    else "融资融券股票池为空"
                ),
                {"source_path": snapshot.source_path, "record_count": snapshot.record_count},
            )
        except Exception as e:
            add_check(
                "margin_stock_pool_loaded",
                "融资融券股票池",
                False,
                True,
                f"融资融券股票池加载失败: {e}",
            )

    # 6) 模拟盘：模型、本地数据、沙箱与关键表
    # 6.1 默认模型检测（检查用户是否配置了默认模型）
    try:
        from backend.shared.model_registry import model_registry_service

        default_model = await model_registry_service.get_default_model(
            tenant_id=resolved_tenant_id,
            user_id=resolved_user_id,
        )
        model_configured = bool(default_model)
        add_check(
            "default_model_configured",
            "默认模型已配置",
            model_configured,
            True,
            (
                f"默认模型已配置 (model_id={default_model.get('model_id')})"
                if model_configured
                else "未配置默认模型，请先在模型管理中设置默认模型"
            ),
            {
                "model_id": default_model.get("model_id") if model_configured else None,
                "model_name": default_model.get("model_name") if model_configured else None,
            },
        )
    except Exception as e:
        add_check(
            "default_model_configured",
            "默认模型已配置",
            False,
            True,
            f"默认模型检测失败: {e}",
        )

    # 6.2 推理模型就绪度（检查生产模型目录是否有模型文件）
    try:
        model_ok, model_detail = _check_inference_model_exists()
        add_check(
            "inference_database_ready",
            "推理模型已就绪",
            model_ok,
            True,
            model_detail,
        )
    except Exception as e:
        add_check(
            "inference_database_ready",
            "推理模型已就绪",
            False,
            True,
            f"推理模型检测失败: {e}",
        )

    # 6.3 本地 quantdb 行情 + 特征 parquet 覆盖度
    #     模拟撮合只读本地 parquet，这两项取代了原「stream 行情新鲜度」检查。
    expected_trade_date = _previous_trading_day(date.today())
    try:
        ok, detail = _check_local_market_data_freshness(expected_trade_date)
        add_check(
            "local_market_data_freshness",
            "本地行情数据",
            ok,
            True,
            detail,
            {"expected_trade_date": expected_trade_date.isoformat()},
        )
    except Exception as e:
        add_check(
            "local_market_data_freshness",
            "本地行情数据",
            False,
            True,
            f"本地行情检测失败: {e}",
        )

    try:
        ok, detail, feature_details = _check_feature_parquet_coverage(expected_trade_date)
        add_check(
            "feature_parquet_coverage",
            "推理特征 parquet",
            ok,
            True,
            detail,
            feature_details,
        )
    except Exception as e:
        add_check(
            "feature_parquet_coverage",
            "推理特征 parquet",
            False,
            True,
            f"特征 parquet 检测失败: {e}",
        )

    # 6.4 沙箱进程池
    try:
        from backend.services.trade.sandbox.manager import sandbox_manager

        workers = list(getattr(sandbox_manager, "_workers", {}).values())
        worker_total = len(workers)
        alive_total = sum(1 for proc in workers if bool(proc and proc.is_alive()))
        pool_ok = alive_total > 0
        add_check(
            "simulation_sandbox_pool",
            "模拟盘沙箱池",
            pool_ok,
            True,
            (
                f"沙箱进程池可用（alive={alive_total}/{worker_total}）"
                if pool_ok
                else "沙箱进程池不可用（无存活 worker）"
            ),
            {"worker_total": worker_total, "alive_total": alive_total},
        )
    except Exception as e:
        add_check(
            "simulation_sandbox_pool",
            "模拟盘沙箱池",
            False,
            True,
            f"沙箱进程池检测失败: {e}",
        )

    # 6.5 模拟盘关键表（防止库被清空后启动才报错）
    try:
        table_probe_sql = text("""
            SELECT
                to_regclass('public.sim_orders') IS NOT NULL AS sim_orders,
                to_regclass('public.sim_trades') IS NOT NULL AS sim_trades,
                to_regclass('public.simulation_fund_snapshots') IS NOT NULL AS simulation_fund_snapshots
            """)
        table_probe_row = (await db.execute(table_probe_sql)).mappings().one()
        missing_tables = [
            name
            for name in (
                "sim_orders",
                "sim_trades",
                "simulation_fund_snapshots",
            )
            if not bool(table_probe_row.get(name))
        ]
        tables_ok = len(missing_tables) == 0
        add_check(
            "simulation_tables",
            "模拟盘数据表",
            tables_ok,
            True,
            "模拟盘关键表已就绪" if tables_ok else f"缺少模拟盘关键表: {', '.join(missing_tables)}",
            {
                "required_tables": [
                    "sim_orders",
                    "sim_trades",
                    "simulation_fund_snapshots",
                ],
                "missing_tables": missing_tables,
            },
        )
    except Exception as e:
        add_check(
            "simulation_tables",
            "模拟盘数据表",
            False,
            True,
            f"模拟盘关键表检测失败: {e}",
        )
        # 回滚事务以清除 aborted 状态
        await db.rollback()

    # 6.6 资金快照任务配置（非阻断，便于排障）
    snapshot_enabled = str(os.getenv("SIM_FUND_SNAPSHOT_ENABLED", "true")).strip().lower() != "false"
    interval_raw = str(os.getenv("SIM_FUND_SNAPSHOT_INTERVAL_SECONDS", "300")).strip()
    try:
        interval_seconds = int(interval_raw)
    except Exception:
        interval_seconds = 300
    snapshot_config_ok = (not snapshot_enabled) or interval_seconds > 0
    add_check(
        "simulation_snapshot_worker_config",
        "模拟盘资金快照任务",
        snapshot_config_ok,
        False,
        (
            f"已启用（interval={interval_seconds}s）"
            if snapshot_enabled and snapshot_config_ok
            else (
                "已关闭（SIM_FUND_SNAPSHOT_ENABLED=false）"
                if not snapshot_enabled
                else "配置异常（SIM_FUND_SNAPSHOT_INTERVAL_SECONDS 应大于 0）"
            )
        ),
        {
            "enabled": snapshot_enabled,
            "interval_seconds": interval_seconds,
        },
    )

    check_order: list[str] = []
    checks_by_key: dict[str, dict] = {}
    for item in checks:
        key = str(item.get("key") or "")
        if key and key not in checks_by_key:
            check_order.append(key)
        checks_by_key[key] = item
    checks = [checks_by_key[key] for key in check_order]

    ready = all(item["ok"] for item in checks if item["required"])

    try:
        await _upsert_preflight_snapshot(
            db,
            tenant_id=resolved_tenant_id,
            user_id=resolved_user_id,
            trading_mode=mode,
            ready=ready,
            checks=checks,
        )
    except Exception as e:
        logger.warning("Failed to persist preflight snapshot: %s", e)
        await db.rollback()

    return {
        "ready": ready,
        "mode": mode,
        "user_id": resolved_user_id,
        "tenant_id": resolved_tenant_id,
        "trading_permission": signal_readiness.get("trading_permission"),
        "signal_readiness": signal_readiness,
        "checks": checks,
    }


@router.get("/trading-precheck", response_model=TradingPrecheckResponse)
async def trading_precheck(
    trading_mode: str = "SIMULATION",
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    mode = str(trading_mode or "SIMULATION").strip().upper()
    if mode != "SIMULATION":
        raise HTTPException(
            status_code=400,
            detail=f"实盘交易已下线（政策原因），仅支持模拟盘。收到 trading_mode={mode}",
        )
    resolved_user_id, resolved_tenant_id = _normalize_identity(auth)
    return await run_trading_readiness_precheck(
        db,
        mode=mode,
        redis_client=redis.client,
        user_id=resolved_user_id,
        tenant_id=resolved_tenant_id,
    )


@router.get("/preflight/snapshots/daily")
async def list_preflight_snapshots_daily(
    days: int = Query(30, ge=1, le=3650),
    trading_mode: Optional[str] = Query(None, description="REAL/SHADOW/SIMULATION"),
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    resolved_user_id, resolved_tenant_id = _normalize_identity(auth, user_id=user_id, tenant_id=tenant_id)
    query = (
        select(PreflightSnapshot)
        .where(
            PreflightSnapshot.tenant_id == resolved_tenant_id,
            PreflightSnapshot.user_id == resolved_user_id,
        )
        .order_by(desc(PreflightSnapshot.snapshot_date))
        .limit(days)
    )
    mode = str(trading_mode or "").strip().upper()
    if mode:
        query = query.where(PreflightSnapshot.trading_mode == mode)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
            "tenant_id": r.tenant_id,
            "user_id": r.user_id,
            "trading_mode": r.trading_mode,
            "ready": bool(r.ready),
            "run_count": int(r.run_count or 0),
            "total_checks": int(r.total_checks or 0),
            "passed_checks": int(r.passed_checks or 0),
            "required_failed_count": int(r.required_failed_count or 0),
            "failed_required_keys": r.failed_required_keys or [],
            "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "checks": r.checks or [],
        }
        for r in rows
    ]


@router.get("/account")
async def get_account(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    获取账户资金与持仓。

    只读取 PostgreSQL 中最近一次持久化快照，不再用 Redis 参与展示口径。
    """
    try:
        resolved_user_id, resolved_tenant_id = _normalize_identity(auth, user_id=user_id, tenant_id=tenant_id)
        latest_snapshot = await _fetch_latest_real_account_snapshot(
            db,
            tenant_id=resolved_tenant_id,
            user_id=resolved_user_id,
        )
        if latest_snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账户信息尚未持久化，请先等待柜台侧代理上报 PostgreSQL 快照",
            )

        account_info = dict(latest_snapshot)
        snapshot_ts = _parse_snapshot_timestamp(account_info.get("snapshot_at"))
        stale_threshold_sec = max(30, int(os.getenv("QMT_AGENT_ACCOUNT_STALE_THRESHOLD_SEC", "120") or 120))
        account_age_sec = None if snapshot_ts is None else max(0.0, time.time() - snapshot_ts)
        account_info["is_online"] = bool(account_age_sec is not None and account_age_sec <= stale_threshold_sec)
        if account_age_sec is not None:
            account_info["account_age_seconds"] = int(account_age_sec)
        if account_info["is_online"] is False:
            account_info["stale_reason"] = f"account_snapshot_stale({int(account_age_sec or 0)}s)"

        # ── 字段归一化 ──────────────────────────────────────────────────
        # 对外暴露语义统一来自 PostgreSQL 最新快照视图：
        #   available_cash  = 可用资金（真正可下单的自由资金）
        #   cash            = 现金总额（= available_cash + 当日委托冻结部分）
        #   frozen_cash     = 冻结资金（委托冻结 + 其他冻结）
        # ───────────────────────────────────────────────────────────────

        try:
            raw_cash = float(account_info.get("cash") or 0.0)
            raw_available = float(account_info.get("available_cash") or 0.0)
            total_asset = float(account_info.get("total_asset") or 0.0)
            market_value = float(account_info.get("market_value") or 0.0)
            reported_frozen = float(account_info.get("frozen_cash") or 0.0)

            if raw_available <= 0.0 and raw_cash > 0.0:
                effective_available = raw_cash
            else:
                effective_available = raw_available

            base_frozen = max(0.0, raw_cash - effective_available)
            gap_frozen = max(0.0, total_asset - market_value - raw_cash)
            calc_frozen = max(base_frozen, gap_frozen)
            final_frozen = max(reported_frozen, calc_frozen)

            account_info["available_cash"] = effective_available
            account_info["cash"] = effective_available
            account_info["frozen_cash"] = final_frozen
            account_info["frozen"] = final_frozen
            account_info["market_value"] = market_value
            account_info["total_asset"] = total_asset
            account_info["baseline"] = {
                "initial_equity": float(account_info.get("initial_equity") or 0.0),
                "day_open_equity": float(account_info.get("day_open_equity") or 0.0),
                "month_open_equity": float(account_info.get("month_open_equity") or 0.0),
            }

            return account_info
        except Exception as e:
            logger.warning(
                "Failed to normalize PostgreSQL account snapshot for tenant=%s user=%s: %s",
                resolved_tenant_id,
                resolved_user_id,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="账户快照字段格式异常，请检查 PostgreSQL 视图口径",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取账户信息失败",
        )
