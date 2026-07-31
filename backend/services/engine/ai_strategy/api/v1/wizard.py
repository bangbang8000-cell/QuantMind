"""AI 策略向导 - 路由分发层 (Phase 5 精简版)

5步策略生成流程：
1. 股票池选择 (parse_conditions)
2. 股票池确认 (query_pool)
3. 策略参数设置 (validate_position)
4. 风格配置 (apply_style_config)
5. 策略生成 (generate_strategy)

其余路由（pool 文件管理、远程策略、Qlib 生成/验证/修复、save-to-cloud 等）
保留原始实现。内联 Pydantic 模型已迁移至 api/schemas/。
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

# ---------------------------------------------------------------------------
# 数据库连接
# ---------------------------------------------------------------------------
try:
    from backend.shared.database_pool import get_database_pool, get_db
except ImportError:
    try:
        from shared.database_pool import get_database_pool, get_db
    except ImportError:
        try:
            from backend.shared.strategy_storage import get_db

            def get_database_pool():
                raise ImportError("database_pool not available")

        except ImportError:
            try:
                from shared.strategy_storage import get_db

                def get_database_pool():
                    raise ImportError("database_pool not available")

            except ImportError:

                def get_database_pool():
                    raise ImportError("Cannot find database_pool module")

                def get_db():
                    raise ImportError("Cannot find database_pool module")


from backend.shared.redis_sentinel_client import get_redis_sentinel_client

from ...models.stock_pool_file import StockPoolFile
from ...services.cos_uploader import (
    get_cos_uploader,
)
from ...services.llm_resilience import LLMRateLimitError, get_resilient_llm_router
from ...services.qlib_validator import get_qlib_validator
from ...services.selection.generator import get_sql_generator

# ---------------------------------------------------------------------------
# 服务层依赖
# ---------------------------------------------------------------------------
from ...services.selection.parser import get_intent_parser
from ...services.selection.rule_parser import get_trade_rule_parser

# ---------------------------------------------------------------------------
# Steps 层（Phase 1-4 抽取的业务逻辑）
# ---------------------------------------------------------------------------
from ...steps.step1_stock_selection import (
    LATEST_TABLE,
    get_latest_table,
    _condition_to_dsl,
)
from ...steps.step1_stock_selection import parse_conditions as _step1_parse_conditions
from ...steps.step2_pool_confirmation import (
    _build_full_market_sql,
    _build_pool_summary,
    _get_universe_total,
    _is_full_market_query,
    _is_full_market_sql,
    _require_user_id,
)
from ...steps.step2_pool_confirmation import query_pool as _step2_query_pool
from .validation import router as validation_router
from .storage import router as storage_router
from .generation import router as generation_router
from .pool_management import router as pool_management_router

# ---------------------------------------------------------------------------
# Schemas（Phase 1 抽取的 Pydantic 模型）
# ---------------------------------------------------------------------------
from ..schemas import (  # Stock Pool; Backtest; Text Parse; Remote
    BacktestRequest,
    BacktestResponse,
    DeletePoolFileRequest,
    DeletePoolFileResponse,
    GenerateQlibRequest,
    GenerateQlibResponse,
    GenerateQlibTaskStatusResponse,
    GenerateQlibTaskSubmitResponse,
    GetActivePoolFileRequest,
    GetActivePoolFileResponse,
    ImportRemoteRequest,
    ListPoolFilesRequest,
    ListPoolFilesResponse,
    ParseRequest,
    ParseResponse,
    ParseTextRequest,
    ParseTradeRulesRequest,
    PoolFileSummary,
    PoolItem,
    PreviewPoolFileRequest,
    PreviewPoolFileResponse,
    QueryPoolRequest,
    QueryPoolResponse,
    RepairQlibRequest,
    RepairQlibResponse,
    SavePoolFileRequest,
    SavePoolFileResponse,
    SaveToCloudRequest,
    SaveToCloudResponse,
    ScanRemoteRequest,
    ValidateQlibRequest,
    ValidateQlibResponse,
    ValidationCheckResponse,
)

logger = logging.getLogger(__name__)
TOTAL_MV_PER_YI = float(os.getenv("AI_STRATEGY_TOTAL_MV_PER_YI", "100000000.0"))
TOTAL_MV_TO_YUAN = 1.0  # 已经是元口径，无需二次换算

router = APIRouter(prefix="/strategy", tags=["strategy-wizard"])
router.include_router(validation_router)
router.include_router(storage_router)
router.include_router(generation_router)
router.include_router(pool_management_router)

_QLIB_TASK_TTL_SECONDS = int(os.getenv("QLIB_GENERATE_TASK_TTL_SECONDS", "3600"))
_QLIB_TASK_REDIS_PREFIX = os.getenv("QLIB_GENERATE_TASK_REDIS_PREFIX", "quantmind:strategy:generate_qlib:task:").strip()
_qlib_task_lock = asyncio.Lock()
_qlib_tasks: dict[str, dict[str, Any]] = {}


def _strip_markdown_fences(code: str) -> str:
    """将 LLM 返回的 markdown 代码围栏剥离为纯 Python。"""
    if not code:
        return code
    s = code.strip()
    if "```" not in s:
        return s + "\n"
    try:
        m = re.search(r"```(?:python)?\s*(.*?)\s*```", s, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return (m.group(1) or "").strip() + "\n"
    except Exception:
        pass
    lines = [ln for ln in s.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip() + "\n"


def _trace_id(request: Request | None) -> str | None:
    if not request:
        return None
    return (
        getattr(request.state, "trace_id", None)
        or request.headers.get("X-Trace-Id")
        or request.headers.get("X-Request-Id")
    )


async def _cleanup_expired_qlib_tasks() -> None:
    now = datetime.now().timestamp()
    expired_ids = [
        task_id
        for task_id, task in _qlib_tasks.items()
        if (now - float(task.get("updated_at_ts", now))) > _QLIB_TASK_TTL_SECONDS
    ]
    for task_id in expired_ids:
        _qlib_tasks.pop(task_id, None)


def _qlib_task_cache_key(task_id: str) -> str:
    return f"{_QLIB_TASK_REDIS_PREFIX}{task_id}"


async def _save_qlib_task_to_redis(task_id: str, task: dict[str, Any]) -> None:
    def _write() -> None:
        client = get_redis_sentinel_client()
        client.setex(
            _qlib_task_cache_key(task_id),
            _QLIB_TASK_TTL_SECONDS,
            json.dumps(task, ensure_ascii=False).encode("utf-8"),
        )

    try:
        await asyncio.to_thread(_write)
    except Exception as exc:
        logger.warning("save qlib task to redis failed: task_id=%s err=%s", task_id, exc)


async def _load_qlib_task_from_redis(task_id: str) -> dict[str, Any] | None:
    def _read() -> bytes | None:
        client = get_redis_sentinel_client()
        return client.get(_qlib_task_cache_key(task_id), use_slave=False)

    try:
        raw = await asyncio.to_thread(_read)
    except Exception as exc:
        logger.warning("load qlib task from redis failed: task_id=%s err=%s", task_id, exc)
        return None

    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            return json.loads(raw.decode("utf-8"))
        if isinstance(raw, str):
            return json.loads(raw)
        return None
    except Exception as exc:
        logger.warning("decode qlib task from redis failed: task_id=%s err=%s", task_id, exc)
        return None


async def _save_qlib_task(task_id: str, updates: dict[str, Any]) -> None:
    async with _qlib_task_lock:
        await _cleanup_expired_qlib_tasks()
        task = _qlib_tasks.get(task_id) or await _load_qlib_task_from_redis(task_id) or {}
        task.update(updates)
        task["updated_at_ts"] = datetime.now().timestamp()
        _qlib_tasks[task_id] = task
        await _save_qlib_task_to_redis(task_id, task)


async def _get_qlib_task(task_id: str) -> dict[str, Any] | None:
    async with _qlib_task_lock:
        await _cleanup_expired_qlib_tasks()
        task = _qlib_tasks.get(task_id)
        if not task:
            task = await _load_qlib_task_from_redis(task_id)
            if task:
                _qlib_tasks[task_id] = task
        if not task:
            return None
        return dict(task)


# ============================================================================
#  Step 1: 股票池选择 — 条件解析
# ============================================================================


@router.post("/parse-conditions", response_model=ParseResponse)
async def parse_conditions(body: ParseRequest, request: Request):
    """解析筛选条件为 DSL"""
    try:
        logger.info("parse_conditions started", extra={"trace_id": _trace_id(request)})
        return _step1_parse_conditions(body.conditions)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("parse_conditions failed: %s", e)
        raise HTTPException(status_code=400, detail=f"解析失败: {e}")


# ============================================================================
#  Step 2: 股票池确认 — 执行查询
# ============================================================================


def _safe_float(v) -> float:
    """Sanitize float: replace inf/nan with 0 for JSON serialization."""
    try:
        f = float(v) if v is not None else 0.0
        if f != f:  # nan check
            return 0.0
        if abs(f) == float("inf"):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _build_items_from_quantdb(result: QueryPoolResponse, qdb_symbols: set[str], market: str | None = None):
    """Build PoolItems from QuantDB symbols with rich metrics from multiple views."""
    from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

    sym_list = list(qdb_symbols)[:10000]
    hub = QuantDBDataHub.get_instance()
    if not hub.available:
        for sym in sym_list:
            result.items.append(PoolItem(symbol=sym, name=sym, metrics={}))
        return

    conn = hub._get_duck_conn()
    sym_placeholders = ", ".join(f"'{s}'" for s in sym_list)
    sym_set = set(sym_list)

    # Step 1: Valuation (close, pe, pb, market_cap, dividend_rate, ps_ttm, float_mv)
    valuation: dict[str, dict] = {}
    if hub._view_exists("qdb_valuation"):
        try:
            sql = f"""
                SELECT symbol, close, pe_ttm, pb, total_mv, float_mv, ps_ttm, dividend_rate
                FROM qdb_valuation
                WHERE dt = (SELECT MAX(dt) FROM qdb_valuation)
                  AND symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                total_mv = _safe_float(row.get("total_mv"))
                valuation[sym] = {
                    "close": _safe_float(row.get("close")),
                    "pe": _safe_float(row.get("pe_ttm")),
                    "pb": _safe_float(row.get("pb")),
                    "market_cap": total_mv / 1e8 if total_mv else 0,
                    "float_mv": _safe_float(row.get("float_mv")) / 1e8 if _safe_float(row.get("float_mv")) else 0,
                    "ps_ttm": _safe_float(row.get("ps_ttm")),
                    "dividend_rate": _safe_float(row.get("dividend_rate")),
                }
        except Exception as exc:
            logger.warning("QuantDB valuation fetch failed: %s", exc)

    # Step 2: Technical indicators (ma, rsi, kdj, macd, returns, pct_change, ma_gap, vol_to_ma)
    technical: dict[str, dict] = {}
    if hub._view_exists("qdb_technical_indicators"):
        try:
            sql = f"""
                SELECT symbol, ma5, ma10, ma20, ma60, rsi_6, rsi_14,
                       kdj_k, kdj_d, kdj_j, macd_dif, macd_dea, macd_hist,
                       vol_atr_14, vol_to_ma5, vol_to_ma20,
                       vol_std_5, vol_std_20, vol_std_60,
                       return_1d, return_3d, return_5d, return_10d, return_20d, return_60d,
                       pct_change, ma_gap_5, ma_gap_10, ma_gap_20,
                       beta_20, volume_trend_3d, volume_ma_3, amount_ma_5
                FROM qdb_technical_indicators
                WHERE dt = (SELECT MAX(dt) FROM qdb_technical_indicators)
                  AND symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                technical[sym] = {
                    "ma5": _safe_float(row.get("ma5")),
                    "ma10": _safe_float(row.get("ma10")),
                    "ma20": _safe_float(row.get("ma20")),
                    "ma60": _safe_float(row.get("ma60")),
                    "rsi_6": _safe_float(row.get("rsi_6")),
                    "rsi_14": _safe_float(row.get("rsi_14")),
                    "kdj_k": _safe_float(row.get("kdj_k")),
                    "kdj_d": _safe_float(row.get("kdj_d")),
                    "kdj_j": _safe_float(row.get("kdj_j")),
                    "macd_dif": _safe_float(row.get("macd_dif")),
                    "macd_dea": _safe_float(row.get("macd_dea")),
                    "macd_hist": _safe_float(row.get("macd_hist")),
                    "atr_14": _safe_float(row.get("vol_atr_14")),
                    "vol_to_ma5": _safe_float(row.get("vol_to_ma5")),
                    "vol_to_ma20": _safe_float(row.get("vol_to_ma20")),
                    "vol_std_5": _safe_float(row.get("vol_std_5")),
                    "vol_std_20": _safe_float(row.get("vol_std_20")),
                    "vol_std_60": _safe_float(row.get("vol_std_60")),
                    "return_1d": _safe_float(row.get("return_1d")),
                    "return_3d": _safe_float(row.get("return_3d")),
                    "return_5d": _safe_float(row.get("return_5d")),
                    "return_10d": _safe_float(row.get("return_10d")),
                    "return_20d": _safe_float(row.get("return_20d")),
                    "return_60d": _safe_float(row.get("return_60d")),
                    "pct_change": _safe_float(row.get("pct_change")),
                    "ma_gap_5": _safe_float(row.get("ma_gap_5")),
                    "ma_gap_10": _safe_float(row.get("ma_gap_10")),
                    "ma_gap_20": _safe_float(row.get("ma_gap_20")),
                    "beta_20": _safe_float(row.get("beta_20")),
                    "volume_trend_3d": _safe_float(row.get("volume_trend_3d")),
                }
        except Exception as exc:
            logger.warning("QuantDB technical fetch failed: %s", exc)

    # Step 3: Market sentiment (liquidity_score, buy_pressure, momentum)
    sentiment: dict[str, dict] = {}
    if hub._view_exists("qdb_market_sentiment"):
        try:
            sql = f"""
                SELECT symbol, liquidity_score, buy_pressure, sell_pressure,
                       momentum_1d, momentum_3d, amount_per_trade
                FROM qdb_market_sentiment
                WHERE dt = (SELECT MAX(dt) FROM qdb_market_sentiment)
                  AND symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                sentiment[sym] = {
                    "liquidity_score": _safe_float(row.get("liquidity_score")),
                    "buy_pressure": _safe_float(row.get("buy_pressure")),
                    "sell_pressure": _safe_float(row.get("sell_pressure")),
                    "momentum_1d": _safe_float(row.get("momentum_1d")),
                    "momentum_3d": _safe_float(row.get("momentum_3d")),
                }
        except Exception as exc:
            logger.warning("QuantDB sentiment fetch failed: %s", exc)

    # Step 4: L1 factors (roe, turnover, chip, ind, style, concept, tech, liq)
    factors: dict[str, dict] = {}
    if hub._view_exists("qdb_l1_factors"):
        try:
            sql = f"""
                SELECT symbol, fun_roe, fun_turnover_1, fun_turnover_5, fun_turnover_20,
                       fun_bp, fun_ep, fun_peg, fun_value_zscore,
                       chip_profit_ratio_20, chip_profit_ratio_60, chip_profit_ratio_120,
                       chip_concentration_20, chip_floating_ratio, chip_cost_90_width,
                       chip_peak_distance, chip_profit_delta_5,
                       ind_strength_20, ind_strength_60, ind_rotation_speed_20,
                       ind_breadth_up_20, ind_crowding_20, ind_dispersion_20,
                       ind_relative_momentum_20, ind_relative_pe, ind_netflow_rank_20,
                       ind_concentration, ind_momentum_decay,
                       style_beta_20, style_beta_60, style_value_20, style_size_20,
                       style_idio_vol_20, style_idio_vol_60, style_residual_ret_20,
                       vol_std_5, vol_std_10, vol_std_20,
                       liq_volume_ratio_5, liq_volume_ratio_20,
                       liq_volume_ma_5, liq_volume_ma_20,
                       liq_mfi_14, liq_obv_20,
                       tech_adx_14, tech_bb_pos, tech_bb_width, tech_cci_20,
                       tech_vol_price_corr_20,
                       concept_hot_score, concept_momentum_top3, concept_leader_score,
                       concept_rotation_score, concept_crowding_max, concept_diversity,
                       concept_flow_rank, concept_exposure_top1, concept_cross_sector,
                       concept_volume_ratio,
                       mom_ret_1d, mom_ret_3d, mom_ret_5d, mom_ret_10d, mom_ret_20d, mom_ret_60d
                FROM qdb_l1_factors
                WHERE dt = (SELECT MAX(dt) FROM qdb_l1_factors)
                  AND symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                factors[sym] = {
                    "roe": _safe_float(row.get("fun_roe")),
                    "turnover_rate": _safe_float(row.get("fun_turnover_1")),
                    "turnover_5": _safe_float(row.get("fun_turnover_5")),
                    "turnover_20": _safe_float(row.get("fun_turnover_20")),
                    "bp": _safe_float(row.get("fun_bp")),
                    "ep": _safe_float(row.get("fun_ep")),
                    "peg": _safe_float(row.get("fun_peg")),
                    "value_zscore": _safe_float(row.get("fun_value_zscore")),
                    "chip_profit_ratio_20": _safe_float(row.get("chip_profit_ratio_20")),
                    "chip_profit_ratio_60": _safe_float(row.get("chip_profit_ratio_60")),
                    "chip_profit_ratio_120": _safe_float(row.get("chip_profit_ratio_120")),
                    "chip_concentration_20": _safe_float(row.get("chip_concentration_20")),
                    "chip_floating_ratio": _safe_float(row.get("chip_floating_ratio")),
                    "chip_cost_90_width": _safe_float(row.get("chip_cost_90_width")),
                    "chip_peak_distance": _safe_float(row.get("chip_peak_distance")),
                    "chip_profit_delta_5": _safe_float(row.get("chip_profit_delta_5")),
                    "ind_strength_20": _safe_float(row.get("ind_strength_20")),
                    "ind_strength_60": _safe_float(row.get("ind_strength_60")),
                    "ind_rotation_speed_20": _safe_float(row.get("ind_rotation_speed_20")),
                    "ind_breadth_up_20": _safe_float(row.get("ind_breadth_up_20")),
                    "ind_crowding_20": _safe_float(row.get("ind_crowding_20")),
                    "ind_dispersion_20": _safe_float(row.get("ind_dispersion_20")),
                    "ind_relative_momentum_20": _safe_float(row.get("ind_relative_momentum_20")),
                    "ind_relative_pe": _safe_float(row.get("ind_relative_pe")),
                    "ind_netflow_rank_20": _safe_float(row.get("ind_netflow_rank_20")),
                    "ind_concentration": _safe_float(row.get("ind_concentration")),
                    "ind_momentum_decay": _safe_float(row.get("ind_momentum_decay")),
                    "style_beta_20": _safe_float(row.get("style_beta_20")),
                    "style_beta_60": _safe_float(row.get("style_beta_60")),
                    "style_value_20": _safe_float(row.get("style_value_20")),
                    "style_size_20": _safe_float(row.get("style_size_20")),
                    "style_idio_vol_20": _safe_float(row.get("style_idio_vol_20")),
                    "style_idio_vol_60": _safe_float(row.get("style_idio_vol_60")),
                    "style_residual_ret_20": _safe_float(row.get("style_residual_ret_20")),
                    "vol_std_20": _safe_float(row.get("vol_std_20")),
                    "volume_ratio_5": _safe_float(row.get("liq_volume_ratio_5")),
                    "volume_ratio_20": _safe_float(row.get("liq_volume_ratio_20")),
                    "liq_mfi_14": _safe_float(row.get("liq_mfi_14")),
                    "liq_obv_20": _safe_float(row.get("liq_obv_20")),
                    "tech_adx_14": _safe_float(row.get("tech_adx_14")),
                    "tech_bb_pos": _safe_float(row.get("tech_bb_pos")),
                    "tech_bb_width": _safe_float(row.get("tech_bb_width")),
                    "tech_cci_20": _safe_float(row.get("tech_cci_20")),
                    "tech_vol_price_corr_20": _safe_float(row.get("tech_vol_price_corr_20")),
                    "concept_hot_score": _safe_float(row.get("concept_hot_score")),
                    "concept_leader_score": _safe_float(row.get("concept_leader_score")),
                    "concept_rotation_score": _safe_float(row.get("concept_rotation_score")),
                    "concept_crowding_max": _safe_float(row.get("concept_crowding_max")),
                    "concept_diversity": _safe_float(row.get("concept_diversity")),
                    "concept_flow_rank": _safe_float(row.get("concept_flow_rank")),
                    # Returns from mom_ret_* (technical_indicators return_* are all NULL)
                    "return_1d": _safe_float(row.get("mom_ret_1d")),
                    "return_3d": _safe_float(row.get("mom_ret_3d")),
                    "return_5d": _safe_float(row.get("mom_ret_5d")),
                    "return_10d": _safe_float(row.get("mom_ret_10d")),
                    "return_20d": _safe_float(row.get("mom_ret_20d")),
                    "return_60d": _safe_float(row.get("mom_ret_60d")),
                }
        except Exception as exc:
            logger.warning("QuantDB factors fetch failed: %s", exc)

    # Step 5: Margin trading (finance_net, finance_balance) — values in 万元, convert to 亿
    margin: dict[str, dict] = {}
    if hub._view_exists("qdb_margin_trading"):
        try:
            sql = f"""
                SELECT symbol, finance_balance, finance_net, finance_buy, slo_volume
                FROM qdb_margin_trading
                WHERE dt = (SELECT MAX(dt) FROM qdb_margin_trading)
                  AND symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                margin[sym] = {
                    "finance_balance": _safe_float(row.get("finance_balance")) / 1e4 if _safe_float(row.get("finance_balance")) else 0,
                    "finance_net": _safe_float(row.get("finance_net")) / 1e4 if _safe_float(row.get("finance_net")) else 0,
                    "finance_buy": _safe_float(row.get("finance_buy")) / 1e4 if _safe_float(row.get("finance_buy")) else 0,
                }
        except Exception as exc:
            logger.warning("QuantDB margin fetch failed: %s", exc)

    # Step 6: Computed turnover_rate from volume/circulating_capital
    turnover_map: dict[str, float] = {}
    if hub._view_exists("qdb_daily_unadjusted") and hub._view_exists("qdb_valuation"):
        try:
            sql = f"""
                SELECT d.symbol,
                       d.volume * 100.0 / NULLIF(v.circulating_capital, 0) * 100 as turnover_rate
                FROM qdb_daily_unadjusted d
                JOIN qdb_valuation v ON d.symbol = v.symbol
                WHERE d.dt = (SELECT MAX(dt) FROM qdb_daily_unadjusted)
                  AND v.dt = (SELECT MAX(dt) FROM qdb_valuation)
                  AND v.circulating_capital > 0
                  AND d.symbol IN ({sym_placeholders})
            """
            df = conn.execute(sql).fetchdf()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", ""))
                turnover_map[sym] = _safe_float(row.get("turnover_rate"))
        except Exception as exc:
            logger.warning("QuantDB turnover computation failed: %s", exc)

    # Step 7: Stock names + industry from instrument_detail
    name_map: dict[str, str] = {}
    industry_map: dict[str, str] = {}
    is_st_map: dict[str, bool] = {}
    try:
        df_names = hub.fetch_stock_list()
        if df_names is not None and not df_names.empty:
            sym_col = "Symbol" if "Symbol" in df_names.columns else "symbol"
            name_col = "Name" if "Name" in df_names.columns else "name"
            matched = df_names[df_names[sym_col].isin(sym_set)]
            for _, row in matched.iterrows():
                sym = str(row[sym_col])
                name = str(row.get(name_col, "")).strip()
                if name:
                    name_map[sym] = name
                # Industry
                for ind_col in ("rs_hyname", "tdx_dyname"):
                    ind_val = str(row.get(ind_col, "")).strip()
                    if ind_val and ind_val != "0":
                        industry_map[sym] = ind_val
                        break
                # ST flag
                st_col = "IsSTGP" if "IsSTGP" in df_names.columns else None
                if st_col and row.get(st_col):
                    is_st_map[sym] = bool(int(row.get(st_col, 0)))
    except Exception as exc:
        logger.debug("QuantDB name/industry lookup failed: %s", exc)

    # Step 8: Build items with merged metrics
    for sym in sym_list:
        name = name_map.get(sym, sym)
        m: dict[str, float] = {}
        m.update(valuation.get(sym, {}))
        m.update(technical.get(sym, {}))
        m.update(sentiment.get(sym, {}))
        m.update(factors.get(sym, {}))
        m.update(margin.get(sym, {}))
        # Add computed turnover_rate
        if sym in turnover_map:
            m["turnover_rate"] = turnover_map[sym]
        # Add industry and ST as metrics fields
        industry = industry_map.get(sym, "")
        if industry:
            m["industry"] = industry  # type: ignore[assignment]
        if is_st_map.get(sym):
            m["is_st"] = 1  # type: ignore[assignment]
        result.items.append(PoolItem(symbol=sym, name=name, metrics=m))


@router.post("/query-pool", response_model=QueryPoolResponse)
async def query_pool(body: QueryPoolRequest, request: Request):
    """执行查询确认股票池 — 以 QuantDB 为主要数据源

    流程:
    1. 解析 DSL 条件，分离 PG 可用条件 vs QuantDB 条件
    2. 用 QuantDB 执行条件过滤（主力数据源）
    3. 用 QuantDB 结果回查 PG 获取 name/close 等基础字段
    4. 用 QuantDB enrichment 补充估值/因子维度数据
    """
    try:
        trace_id = _trace_id(request)
        user_id = _require_user_id(request)
        quantdb_conditions = body.quantdb_filters or []

        # === Step 1: Determine ALL conditions (from DSL + explicit quantdb_filters) ===
        # Parse DSL to extract factor conditions
        all_qdb_conditions = list(quantdb_conditions)  # copy explicit filters

        # Only parse DSL for additional QuantDB conditions if no explicit filters provided
        # (avoids duplicate/conflicting conditions when presets already set them)
        if not quantdb_conditions and body.dsl and body.dsl.startswith("SELECT symbol WHERE"):
            from ...steps.step1_stock_selection import _parse_dsl, is_quantdb_factor, FACTOR_COLUMN_MAP
            try:
                conditions, combiners = _parse_dsl(body.dsl)
                for cond in conditions:
                    factor = cond.get("factor", "")
                    if is_quantdb_factor(factor):
                        mapped = FACTOR_COLUMN_MAP[factor.strip()]
                        all_qdb_conditions.append({
                            "table": mapped[0],
                            "field": mapped[1],
                            "operator": cond.get("op", ">"),
                            "value": cond.get("value", 0),
                        })
            except Exception:
                pass

        # === Step 2: Query QuantDB as primary data source ===
        qdb_symbols = set()
        result = QueryPoolResponse(items=[], summary={}, charts={})

        if all_qdb_conditions:
            from backend.services.engine.ai_strategy.services.selection.generator import QuantDBQueryExecutor
            from datetime import date as _date

            executor = QuantDBQueryExecutor()
            qdb_symbols = await asyncio.to_thread(executor.execute, all_qdb_conditions, _date.today())
            logger.info("QuantDB primary query returned %d symbols", len(qdb_symbols))

        # === Step 3: Build results ===
        if qdb_symbols:
            # Use QuantDB as sole data source (PG A-share data is incomplete)
            await asyncio.to_thread(_build_items_from_quantdb, result, qdb_symbols, body.market)
            logger.info("QuantDB-only: QDB=%d, built=%d items", len(qdb_symbols), len(result.items))
        elif all_qdb_conditions:
            # Had QuantDB conditions but no results — return empty (do NOT fall back to PG)
            logger.info("QuantDB conditions yielded 0 results, returning empty (PG disabled for A-shares)")
        else:
            # No QuantDB conditions at all — return empty
            logger.info("No QuantDB conditions provided, returning empty pool")

        logger.info(
            f"query_pool executed for user {user_id}",
            extra={"dsl": body.dsl, "count": len(result.items), "trace_id": trace_id},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        err_text = str(e)
        logger.error(f"query_pool failed: {err_text}")
        if "UndefinedColumn" in err_text or ("column" in err_text.lower() and "does not exist" in err_text.lower()):
            raise HTTPException(
                status_code=422,
                detail="股票池筛选字段与当前数据库结构不匹配，请联系管理员同步字段映射。",
            )
        raise HTTPException(status_code=500, detail=f"查询失败 (AI Strategy): {err_text}")


# ============================================================================
#  文本解析（自然语言 → DSL/SQL）
#  _simple_parse_text / _parse_trade_text 尚未迁移到 steps/，暂保留于路由层
# ============================================================================


def _simple_parse_text(text_input: str):
    """基于正则的本地文本解析（无需 LLM）"""
    s = text_input.replace("：", ":").replace(" ", "")
    s = s.replace("总市值", "市值")
    s = s.replace("<=", "≤").replace(">=", "≥").replace("—", "-")

    # --- 策略关键词预设 → 自动展开为 QuantDB 条件 ---
    # 当用户输入模糊策略描述时，regex 无法匹配具体数值，这里用预设映射
    _STRATEGY_PRESETS: dict[str, list[dict]] = {
        "高股息": [
            {"field": "dividend_rate", "operator": ">", "value": 0.03, "table": "quantdb_valuation"},
            {"field": "pe_ttm", "operator": "<=", "value": 20.0, "table": "quantdb_valuation"},
        ],
        "价值股": [
            {"field": "pe_ttm", "operator": "<=", "value": 20.0, "table": "quantdb_valuation"},
            {"field": "pb", "operator": "<=", "value": 2.0, "table": "quantdb_valuation"},
        ],
        "蓝筹": [
            {"field": "total_mv", "operator": ">=", "value": 200e8, "table": "quantdb_valuation"},
            {"field": "pe_ttm", "operator": "<=", "value": 25.0, "table": "quantdb_valuation"},
        ],
        "白马": [
            {"field": "total_mv", "operator": ">=", "value": 100e8, "table": "quantdb_valuation"},
            {"field": "pe_ttm", "operator": "<=", "value": 25.0, "table": "quantdb_valuation"},
            {"field": "dividend_rate", "operator": ">", "value": 0.01, "table": "quantdb_valuation"},
        ],
        "成长股": [
            {"field": "total_mv", "operator": ">=", "value": 50e8, "table": "quantdb_valuation"},
            {"field": "pe_ttm", "operator": "<=", "value": 40.0, "table": "quantdb_valuation"},
        ],
        "大盘股": [
            {"field": "total_mv", "operator": ">=", "value": 500e8, "table": "quantdb_valuation"},
        ],
        "中盘股": [
            {"field": "total_mv", "operator": ">=", "value": 100e8, "table": "quantdb_valuation"},
            {"field": "total_mv", "operator": "<=", "value": 500e8, "table": "quantdb_valuation"},
        ],
        "小盘股": [
            {"field": "total_mv", "operator": "<=", "value": 100e8, "table": "quantdb_valuation"},
        ],
        "低估值": [
            {"field": "pe_ttm", "operator": "<=", "value": 15.0, "table": "quantdb_valuation"},
            {"field": "pb", "operator": "<=", "value": 1.5, "table": "quantdb_valuation"},
        ],
    }
    _preset_qdb_filters: list[dict] = []
    _preset_dsl_parts: list[str] = []
    for keyword, preset_filters in _STRATEGY_PRESETS.items():
        if keyword in text_input:
            _preset_qdb_filters.extend(preset_filters)
            _preset_dsl_parts.append(keyword)
    # deduplicate
    if _preset_qdb_filters:
        _dedup: dict[tuple, dict] = {}
        for f in _preset_qdb_filters:
            _dedup[(f["field"], f["operator"], f["table"])] = f
        _preset_qdb_filters = list(_dedup.values())

    factors = []
    suggestions = []
    pe_range = None
    pb_range = None
    roe_range = None
    cap_range = None
    industry_list: list[str] = []
    local_hit = False
    loose_mode_hits: list[str] = []

    def _sql_quote(val: str) -> str:
        return (val or "").replace("'", "''")

    # total_mv 单位可配置，默认“元”：1亿=100,000,000.0。
    # 若仍使用旧库“万元”口径，可设置 AI_STRATEGY_TOTAL_MV_PER_YI=10000。
    cap_unit_multiplier = 1.0
    if "亿" in s:
        cap_unit_multiplier = TOTAL_MV_PER_YI

    def _cap_to_yuan(num_text: str, unit_text: str | None) -> float:
        n = float(num_text)
        u = (unit_text or "").strip()
        if u == "亿":
            return n * TOTAL_MV_PER_YI
        if u == "万":
            return n * (TOTAL_MV_PER_YI / 10000.0)
        return n * cap_unit_multiplier

    # 支持总市值和流通市值
    m_cap_range = re.search(
        r"(?:总?市值|流通市值|流通盘)(?:区间|范围)?(?:在)?(\d+(?:\.\d+)?)(亿|万)?(?:到|至|~|-|—|和)(\d+(?:\.\d+)?)(亿|万)?(?:之间|区间|范围内|以内)?",
        s,
    )
    is_float_cap = "流通" in s
    cap_factor = "float_mv" if is_float_cap else "market_cap"
    
    if m_cap_range:
        low_val = _cap_to_yuan(m_cap_range.group(1), m_cap_range.group(2))
        high_val = _cap_to_yuan(m_cap_range.group(3), m_cap_range.group(4))
        if low_val > high_val:
            low_val, high_val = high_val, low_val
            loose_mode_hits.append("市值区间已自动纠正为从小到大")
        cap_range = (low_val, high_val)
        factors.append(cap_factor)
        local_hit = True
    else:
        m_cap = re.search(
            r"(?:总?市值|流通市值|流通盘)(?:[≥>=]|大于等于|不少于|不低于|不小于|大于|高于|超过|以上|至少)(\d+(?:\.\d+)?)(亿|万)?",
            s,
        )
        if m_cap:
            cap_range = (_cap_to_yuan(m_cap.group(1), m_cap.group(2)), None)
            factors.append(cap_factor)
            local_hit = True
        else:
            m_cap_rev = re.search(
                r"(?:总?市值|流通市值|流通盘)(?:[≤<=]|小于等于|不高于|不超过|不大于|小于|低于|以下|以内|至多)(\d+(?:\.\d+)?)(亿|万)?",
                s,
            )
            if m_cap_rev:
                cap_range = (None, _cap_to_yuan(m_cap_rev.group(1), m_cap_rev.group(2)))
                factors.append(cap_factor)
                local_hit = True
            else:
                m_cap_approx = re.search(
                    r"(?:总?市值|流通市值|流通盘)(?:约|大约|大概|大致)?(\d+(?:\.\d+)?)(亿|万)?(?:左右|附近)?",
                    s,
                )
                if m_cap_approx:
                    center = _cap_to_yuan(m_cap_approx.group(1), m_cap_approx.group(2))
                    # 宽松查询：近似值按 ±20% 区间处理
                    cap_range = (center * 0.8, center * 1.2)
                    factors.append(cap_factor)
                    local_hit = True
                    loose_mode_hits.append("市值“约/左右”已按±20%宽松区间处理")

    if cap_range is None and (("小市值" in s) or ("小盘" in s) or ("微盘" in s)):
        # 默认小市值阈值：10亿-100亿（按 total_mv 口径）
        cap_range = (10.0 * TOTAL_MV_PER_YI, 100.0 * TOTAL_MV_PER_YI)
        factors.append("market_cap")
        local_hit = True
        suggestions.append("已按“小市值10亿-100亿”默认阈值处理，可手动指定市值范围提升精度")

    m_pe_range = re.search(
        r"(?:PE|市盈率)(?:区间|范围)?(?:在|是)?(\d+(?:\.\d+)?)(?:到|至|~|-|—|和)(\d+(?:\.\d+)?)(?:之间|区间|范围内|以内)?",
        s,
        re.IGNORECASE,
    )
    if m_pe_range:
        pe_low = float(m_pe_range.group(1))
        pe_high = float(m_pe_range.group(2))
        if pe_low > pe_high:
            pe_low, pe_high = pe_high, pe_low
            loose_mode_hits.append("PE区间已自动纠正为从小到大")
        pe_range = (pe_low, pe_high)
        factors.append("pe")
        local_hit = True
    else:
        m_pe = (
            re.search(r"PE[≤<=](\d+(?:\.\d+)?)", s, re.IGNORECASE)
            or re.search(r"市盈率[≤<=](\d+(?:\.\d+)?)", s)
            or re.search(
                r"(?:PE|市盈率)(?:小于等于|不高于|不超过|不大于|小于|低于|以下|以内|至多)(\d+(?:\.\d+)?)",
                s,
                re.IGNORECASE,
            )
        )
        if m_pe:
            pe_range = (None, float(m_pe.group(1)))
            factors.append("pe")
            local_hit = True
        else:
            m_pe_ge = re.search(
                r"(?:PE|市盈率)(?:大于等于|不少于|不低于|不小于|大于|高于|超过|以上|至少)(\d+(?:\.\d+)?)",
                s,
                re.IGNORECASE,
            )
            if m_pe_ge:
                pe_range = (float(m_pe_ge.group(1)), None)
                factors.append("pe")
                local_hit = True
            else:
                m_pe_approx = re.search(
                    r"(?:PE|市盈率)(?:约|大约|大概|大致)?(\d+(?:\.\d+)?)(?:左右|附近)?",
                    s,
                    re.IGNORECASE,
                )
                if m_pe_approx:
                    center = float(m_pe_approx.group(1))
                    pe_range = (center * 0.8, center * 1.2)
                    factors.append("pe")
                    local_hit = True
                    loose_mode_hits.append("PE“约/左右”已按±20%宽松区间处理")

    # 4. ROE 过滤 (单位：百分比，如 15 代表 15%)
    m_roe_range = re.search(
        r"(?:ROE|净资产收益率)(?:区间|范围)?(?:在|是)?(\d+(?:\.\d+)?)(?:到|至|~|-|—|和)(\d+(?:\.\d+)?)(?:之间|区间|范围内|以内)?",
        s,
        re.IGNORECASE,
    )
    if m_roe_range:
        roe_low = float(m_roe_range.group(1))
        roe_high = float(m_roe_range.group(2))
        if roe_low > roe_high:
            roe_low, roe_high = roe_high, roe_low
        roe_range = (roe_low, roe_high)
        factors.append("roe")
        local_hit = True
    else:
        m_roe = (
            re.search(r"ROE[≥>=](\d+(?:\.\d+)?)", s, re.IGNORECASE)
            or re.search(r"净资产收益率[≥>=](\d+(?:\.\d+)?)", s)
            or re.search(
                r"(?:ROE|净资产收益率)(?:大于等于|不少于|不低于|不小于|大于|高于|超过|以上|至少)(\d+(?:\.\d+)?)",
                s,
                re.IGNORECASE,
            )
        )
        if m_roe:
            roe_range = (float(m_roe.group(1)), None)
            factors.append("roe")
            local_hit = True
        else:
            m_roe_le = (
                re.search(r"ROE[≤<=](\d+(?:\.\d+)?)", s, re.IGNORECASE)
                or re.search(r"净资产收益率[≤<=](\d+(?:\.\d+)?)", s)
                or re.search(
                    r"(?:ROE|净资产收益率)(?:小于等于|不高于|不超过|不大于|小于|低于|以下|以内|至多)(\d+(?:\.\d+)?)",
                    s,
                    re.IGNORECASE,
                )
            )
            if m_roe_le:
                roe_range = (None, float(m_roe_le.group(1)))
                factors.append("roe")
                local_hit = True

    m_pb_range = re.search(
        r"(?:PB|市净率)(?:区间|范围)?(?:在)?(\d+(?:\.\d+)?)(?:到|至|~|-|—|和)(\d+(?:\.\d+)?)(?:之间|区间|范围内|以内)?",
        s,
        re.IGNORECASE,
    )
    if m_pb_range:
        pb_low = float(m_pb_range.group(1))
        pb_high = float(m_pb_range.group(2))
        if pb_low > pb_high:
            pb_low, pb_high = pb_high, pb_low
            loose_mode_hits.append("PB区间已自动纠正为从小到大")
        pb_range = (pb_low, pb_high)
        factors.append("pb")
        local_hit = True
    else:
        m_pb = (
            re.search(r"PB[≤<=](\d+(?:\.\d+)?)", s, re.IGNORECASE)
            or re.search(r"市净率[≤<=](\d+(?:\.\d+)?)", s)
            or re.search(
                r"(?:PB|市净率)(?:小于等于|不高于|不超过|不大于|小于|低于|以下|以内|至多)(\d+(?:\.\d+)?)",
                s,
                re.IGNORECASE,
            )
        )
        if m_pb:
            pb_range = (None, float(m_pb.group(1)))
            factors.append("pb")
            local_hit = True
        else:
            m_pb_ge = re.search(
                r"(?:PB|市净率)(?:大于等于|不少于|不低于|不小于|大于|高于|超过|以上|至少)(\d+(?:\.\d+)?)",
                s,
                re.IGNORECASE,
            )
            if m_pb_ge:
                pb_range = (float(m_pb_ge.group(1)), None)
                factors.append("pb")
                local_hit = True
            else:
                m_pb_approx = re.search(
                    r"(?:PB|市净率)(?:约|大约|大概|大致)?(\d+(?:\.\d+)?)(?:左右|附近)?",
                    s,
                    re.IGNORECASE,
                )
                if m_pb_approx:
                    center = float(m_pb_approx.group(1))
                    pb_range = (center * 0.8, center * 1.2)
                    factors.append("pb")
                    local_hit = True
                    loose_mode_hits.append("PB“约/左右”已按±20%宽松区间处理")

    if any(k in s for k in ("金融股", "金融板块", "金融行业", "券商股", "证券股", "银行股", "保险股")):
        # 兼容当前库内行业值（仅有 industry 一列，常见为细分行业名）
        industry_list = ["金融", "银行", "保险", "证券"]
        factors.append("industry")
        local_hit = True
        suggestions.append("已按金融股解析为金融相关行业（含金融信息服务）")
    else:
        inds = re.findall(r"行业[:：]\s*([\u4e00-\u9fa5,，\s]+)", s)
        if inds:
            industry_list = [x.strip() for x in re.split(r"[,，\s]+", inds[0]) if x.strip()]
            if industry_list:
                factors.append("industry")
                local_hit = True
        if not industry_list:
            # 宽松行业识别：支持“XX股/XX板块/XX行业/XX概念”
            coarse_terms = re.findall(r"([\u4e00-\u9fa5]{2,8})(?:股|板块|行业|概念)", s)
            industry_stopwords = {
                "小市值",
                "大市值",
                "中小市值",
                "沪深300",
                "中证1000",
                "全市场",
                "A股",
                "股票",
                "非ST",
                "ST",
                "总市值",
                "市值",
                "市盈率",
                "市净率",
                "成分",
                "成分股",
            }
            for term in coarse_terms:
                t = term.strip()
                if not t or t in industry_stopwords or t.endswith("的"):
                    continue
                if t not in industry_list:
                    industry_list.append(t)
            if industry_list:
                factors.append("industry")
                local_hit = True
                loose_mode_hits.append("已启用“XX股/XX板块”宽松行业匹配")

    is_st_flag = None
    if re.search(r"非ST|去除ST|排除ST|不含ST", s, re.IGNORECASE):
        is_st_flag = 0
    elif re.search(r"\bST\b|^ST|\\*ST", s, re.IGNORECASE):
        is_st_flag = 1
    if is_st_flag is not None:
        factors.append("is_st")
        local_hit = True

    hs300_flag = None
    csi1000_flag = None
    if "沪深300" in s or "HS300" in s.upper():
        hs300_flag = 1
        factors.append("idx_hs300")
        local_hit = True
    if "中证1000" in s or "CSI1000" in s.upper():
        csi1000_flag = 1
        factors.append("idx_zz1000")
        local_hit = True

    # --- QuantDB 新增维度解析 ---
    # NOTE: A股估值数据(PE/PB/ROE/市值)在 PG 中为空，必须路由到 QuantDB
    quantdb_filters: list[dict] = []

    # Merge preset filters first
    if _preset_qdb_filters:
        quantdb_filters.extend(_preset_qdb_filters)
        local_hit = True
        if _preset_dsl_parts:
            factors.extend(_preset_dsl_parts)

    # is_st → stock_list filter (IsSTGP field)
    if is_st_flag is not None:
        quantdb_filters.append({"field": "IsSTGP", "operator": "==", "value": is_st_flag, "table": "quantdb_stock_list"})

    # Index membership → stock_list filter
    if hs300_flag is not None:
        quantdb_filters.append({"field": "idx_hs300", "operator": "==", "value": 1, "table": "quantdb_stock_list"})
    if csi1000_flag is not None:
        quantdb_filters.append({"field": "idx_zz1000", "operator": "==", "value": 1, "table": "quantdb_stock_list"})

    # PE → QuantDB valuation
    if pe_range:
        low, high = pe_range
        if low is not None:
            quantdb_filters.append({"field": "pe_ttm", "operator": ">=", "value": low, "table": "quantdb_valuation"})
        if high is not None:
            quantdb_filters.append({"field": "pe_ttm", "operator": "<=", "value": high, "table": "quantdb_valuation"})

    # PB → QuantDB valuation
    if pb_range:
        low, high = pb_range
        if low is not None:
            quantdb_filters.append({"field": "pb", "operator": ">=", "value": low, "table": "quantdb_valuation"})
        if high is not None:
            quantdb_filters.append({"field": "pb", "operator": "<=", "value": high, "table": "quantdb_valuation"})

    # ROE → QuantDB l1_factors (fun_roe is in percentage, e.g. 15 = 15%)
    if roe_range:
        low, high = roe_range
        if low is not None:
            quantdb_filters.append({"field": "fun_roe", "operator": ">=", "value": low, "table": "quantdb_factors"})
        if high is not None:
            quantdb_filters.append({"field": "fun_roe", "operator": "<=", "value": high, "table": "quantdb_factors"})

    # Market cap → QuantDB valuation (total_mv in 元)
    if cap_range:
        low, high = cap_range
        # cap_range is already in yuan (converted by _cap_to_yuan above)
        if low is not None:
            quantdb_filters.append({"field": "total_mv", "operator": ">=", "value": low, "table": "quantdb_valuation"})
        if high is not None:
            quantdb_filters.append({"field": "total_mv", "operator": "<=", "value": high, "table": "quantdb_valuation"})

    if re.search(r"股息率|分红率", text_input):
        val = 0.02  # default 2%
        m_div = re.search(r"(?:股息率|分红率)[≥>=≥大于等于不少于不低于不小于大于高于超过以上至少]*(\d+(?:\.\d+)?)", s)
        if m_div:
            raw_val = float(m_div.group(1))
            # QuantDB stores dividend_rate as decimal (0.03 = 3%), user inputs percentage
            val = raw_val / 100.0 if raw_val > 1.0 else raw_val
        quantdb_filters.append({"field": "dividend_rate", "operator": ">", "value": val, "table": "quantdb_valuation"})
        factors.append("dividend_rate")
        local_hit = True
    if re.search(r"市销率|PS[^a-zA-Z]", text_input, re.IGNORECASE):
        val = 5.0
        m_ps = re.search(r"(?:市销率|PS)[≤<=≤小于等于不高于不超过不大于小于低于以下以内至多]*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
        if m_ps:
            val = float(m_ps.group(1))
        quantdb_filters.append({"field": "ps_ttm", "operator": "<", "value": val, "table": "quantdb_valuation"})
        factors.append("ps_ttm")
        local_hit = True
    if re.search(r"静态市盈率|静态PE", text_input, re.IGNORECASE):
        quantdb_filters.append({"field": "pe_static", "operator": "<", "value": 30.0, "table": "quantdb_valuation"})
        factors.append("pe_static")
        local_hit = True
    if re.search(r"获利盘|筹码获利", text_input):
        val = 50.0
        m_chip = re.search(r"(?:获利盘|筹码获利)[比例]?(?:≥|>=|大于等于|不少于|不低于|不小于|大于|高于|超过|以上|至少)?(\d+(?:\.\d+)?)", s)
        if m_chip:
            val = float(m_chip.group(1))
        quantdb_filters.append({"field": "chip_profit_ratio_20", "operator": ">", "value": val, "table": "quantdb_factors"})
        factors.append("chip_profit_ratio_20")
        local_hit = True
    if re.search(r"筹码集中", text_input):
        quantdb_filters.append({"field": "chip_concentration_20", "operator": ">", "value": 0.5, "table": "quantdb_factors"})
        factors.append("chip_concentration_20")
        local_hit = True
    if re.search(r"行业强度|行业动量", text_input):
        quantdb_filters.append({"field": "ind_strength_20", "operator": ">", "value": 0.0, "table": "quantdb_factors"})
        factors.append("ind_strength_20")
        local_hit = True
    if re.search(r"行业拥挤|拥挤度", text_input):
        quantdb_filters.append({"field": "ind_crowding_20", "operator": "<", "value": 0.5, "table": "quantdb_factors"})
        factors.append("ind_crowding_20")
        local_hit = True
    if re.search(r"风格|Beta|beta", text_input):
        if re.search(r"Beta|beta", text_input):
            quantdb_filters.append({"field": "style_beta_20", "operator": ">", "value": 0.8, "table": "quantdb_factors"})
            factors.append("style_beta_20")
        else:
            quantdb_filters.append({"field": "style_value_20", "operator": ">", "value": 0.0, "table": "quantdb_factors"})
            factors.append("style_value_20")
        local_hit = True
    if re.search(r"概念热度|热门概念", text_input):
        quantdb_filters.append({"field": "concept_hot_score", "operator": ">", "value": 0.5, "table": "quantdb_factors"})
        factors.append("concept_hot_score")
        local_hit = True
    if re.search(r"概念轮动|板块轮动", text_input):
        quantdb_filters.append({"field": "concept_rotation_score", "operator": ">", "value": 0.0, "table": "quantdb_factors"})
        factors.append("concept_rotation_score")
        local_hit = True
    if re.search(r"流动性|流动性评分", text_input):
        val = 0.3
        m_liq = re.search(r"(?:流动性|流动性评分)[≥>=≥大于等于不少于不低于不小于大于高于超过以上至少]*(\d+(?:\.\d+)?)", s)
        if m_liq:
            val = float(m_liq.group(1))
        quantdb_filters.append({"field": "liquidity_score", "operator": ">", "value": val, "table": "quantdb_sentiment"})
        factors.append("liquidity_score")
        local_hit = True
    if re.search(r"买入压力|买压", text_input):
        quantdb_filters.append({"field": "buy_pressure", "operator": ">", "value": 0.0, "table": "quantdb_sentiment"})
        factors.append("buy_pressure")
        local_hit = True
    if re.search(r"融资余额|两融余额|融资净买入", text_input):
        if "净买入" in s:
            quantdb_filters.append({"field": "finance_net", "operator": ">", "value": 0, "table": "quantdb_margin"})
            factors.append("finance_net")
        else:
            quantdb_filters.append({"field": "finance_balance", "operator": ">", "value": 0, "table": "quantdb_margin"})
            factors.append("finance_balance")
        local_hit = True
    if re.search(r"融券|卖空", text_input):
        quantdb_filters.append({"field": "slo_volume", "operator": "<", "value": 1000000, "table": "quantdb_margin"})
        factors.append("slo_volume")
        local_hit = True
    if re.search(r"商誉", text_input):
        # Financial data not in QuantDB parquet views; skip filter
        factors.append("goodwill")
        local_hit = True
        suggestions.append("商誉筛选暂不支持（财务数据未接入QuantDB视图）")
    if re.search(r"研发费用|研发投入", text_input):
        factors.append("research_expenses")
        local_hit = True
        suggestions.append("研发费用筛选暂不支持（财务数据未接入QuantDB视图）")
    if re.search(r"毛利率", text_input):
        factors.append("sales_gross_profit")
        local_hit = True
        suggestions.append("毛利率筛选暂不支持（财务数据未接入QuantDB视图）")
    if re.search(r"每股收益|EPS", text_input, re.IGNORECASE):
        factors.append("s_fa_eps_basic")
        local_hit = True
        suggestions.append("EPS筛选暂不支持（财务数据未接入QuantDB视图）")
    if re.search(r"量比|OBV|MFI|资金流量", text_input, re.IGNORECASE):
        if re.search(r"MFI|资金流量", text_input, re.IGNORECASE):
            quantdb_filters.append({"field": "liq_mfi_14", "operator": ">", "value": 50, "table": "quantdb_factors"})
            factors.append("liq_mfi_14")
        elif re.search(r"OBV|能量潮", text_input, re.IGNORECASE):
            quantdb_filters.append({"field": "liq_obv_20", "operator": ">", "value": 0, "table": "quantdb_factors"})
            factors.append("liq_obv_20")
        else:
            quantdb_filters.append({"field": "vol_to_ma5", "operator": ">", "value": 1.0, "table": "quantdb_technical"})
            factors.append("vol_to_ma5")
        local_hit = True

    parts = []
    if cap_range:
        low, high = cap_range
        if low is not None and high is not None:
            parts.append(f"market_cap >= {low} AND market_cap <= {high}")
        elif low is not None:
            parts.append(f"market_cap >= {low}")
        elif high is not None:
            parts.append(f"market_cap <= {high}")

    if pe_range:
        low, high = pe_range
        if low is not None and high is not None:
            parts.append(f"pe >= {low} AND pe <= {high}")
        elif low is not None:
            parts.append(f"pe >= {low}")
        elif high is not None:
            parts.append(f"pe <= {high}")

    if pb_range:
        low, high = pb_range
        if low is not None and high is not None:
            parts.append(f"pb >= {low} AND pb <= {high}")
        elif low is not None:
            parts.append(f"pb >= {low}")
        elif high is not None:
            parts.append(f"pb <= {high}")

    if roe_range:
        low, high = roe_range
        # fun_roe in QuantDB is already in percentage (e.g. 15 = 15%)
        if low is not None and high is not None:
            parts.append(f"roe >= {low} AND roe <= {high}")
        elif low is not None:
            parts.append(f"roe >= {low}")
        elif high is not None:
            parts.append(f"roe <= {high}")

    if is_st_flag is not None:
        parts.append(f"is_st == {is_st_flag}")
    if hs300_flag is not None:
        parts.append("idx_hs300 == 1")
    if csi1000_flag is not None:
        parts.append("idx_zz1000 == 1")
    if industry_list:
        sql_parts: list[str] = []
        if cap_range:
            low, high = cap_range
            if low is not None:
                sql_parts.append(f"total_mv >= {low}")
            if high is not None:
                sql_parts.append(f"total_mv <= {high}")
        if pe_range:
            low, high = pe_range
            if low is not None:
                sql_parts.append(f"pe_ttm >= {low}")
            if high is not None:
                sql_parts.append(f"pe_ttm <= {high}")
        if pb_range:
            low, high = pb_range
            if low is not None:
                sql_parts.append(f"pb >= {low}")
            if high is not None:
                sql_parts.append(f"pb <= {high}")
        if roe_range:
            low, high = roe_range
            if low is not None:
                sql_parts.append(f"fun_roe >= {low}")
            if high is not None:
                sql_parts.append(f"fun_roe <= {high}")
        if is_st_flag is not None:
            sql_parts.append(f"is_st = {is_st_flag}")
        if hs300_flag is not None:
            sql_parts.append("idx_hs300 = 1")
        if csi1000_flag is not None:
            sql_parts.append("idx_zz1000 = 1")
        # 将业务行业词映射到库内 industry 字段常见取值，仍然基于 industry 字段匹配。
        industry_alias_map: dict[str, list[str]] = {
            # 金融
            # 先保留业务词本身（如“金融”），再扩展到可能的细分别名，避免只匹配别名导致 0 结果。
            "金融": ["金融", "金融信息服务", "货币金融服务", "资本市场服务", "保险业", "其他金融业"],
            "银行": ["银行", "银行业", "货币金融服务"],
            "保险": ["保险", "保险业"],
            "证券": ["证券", "证券、期货业", "资本市场服务", "其他金融业"],
            "券商": ["资本市场服务"],
            # 科技
            "科技": [
                "计算机、通信和其他电子设备制造业",
                "软件和信息技术服务业",
                "互联网和相关服务",
                "电信、广播电视和卫星传输服务",
                "研究和试验发展",
                "科技推广和应用服务业",
            ],
            "半导体": ["计算机、通信和其他电子设备制造业"],
            "电子": ["计算机、通信和其他电子设备制造业"],
            "通信": ["计算机、通信和其他电子设备制造业"],
            "计算机": ["软件和信息技术服务业", "计算机、通信和其他电子设备制造业"],
            "软件": ["软件和信息技术服务业"],
            # 医药消费
            "医药": ["医药制造业", "卫生"],
            "医疗": ["医药制造业", "卫生"],
            "生物医药": ["医药制造业"],
            "白酒": ["酒、饮料和精制茶制造业"],
            "消费": [
                "食品制造业",
                "酒、饮料和精制茶制造业",
                "农副食品加工业",
                "纺织服装、服饰业",
                "零售业",
            ],
            # 制造与周期
            "军工": ["铁路、船舶、航空航天和其它运输设备制造业"],
            "新能源": ["电气机械及器材制造业", "电力、热力生产和供应业", "汽车制造业"],
            "光伏": ["电气机械及器材制造业"],
            "锂电": ["电气机械及器材制造业"],
            "汽车": ["汽车制造业"],
            "化工": ["化学原料及化学制品制造业", "化学纤维制造业"],
            "有色": ["有色金属冶炼及压延加工业", "有色金属矿采选业"],
            "钢铁": ["黑色金属冶炼及压延加工业", "黑色金属矿采选业"],
            "煤炭": ["煤炭开采和洗选业"],
            "石油": ["石油和天然气开采业", "石油加工、炼焦及核燃料加工业"],
            # 地产基建
            "地产": ["房地产业", "房屋建筑业"],
            "房地产": ["房地产业", "房屋建筑业"],
            "基建": ["土木工程建筑业", "建筑装饰和其他建筑业", "建筑安装业", "房屋建筑业"],
            "建筑": ["土木工程建筑业", "建筑装饰和其他建筑业", "建筑安装业", "房屋建筑业"],
            # 交通运输与公用事业
            "交通运输": ["道路运输业", "铁路运输业", "航空运输业", "水上运输业", "仓储业", "邮政业"],
            "公用事业": ["电力、热力生产和供应业", "燃气生产和供应业", "水的生产和供应业", "公共设施管理业"],
            "环保": ["生态保护和环境治理业"],
            # 传媒文娱
            "传媒": ["新闻和出版业", "广播、电视、电影和影视录音制作业", "文化艺术业"],
            "文娱": ["广播、电视、电影和影视录音制作业", "文化艺术业", "体育"],
        }
        expanded_industry_terms: list[str] = []
        for ind in industry_list:
            aliases = industry_alias_map.get(ind, [ind])
            for alias in aliases:
                if alias and alias not in expanded_industry_terms:
                    expanded_industry_terms.append(alias)

        # 行业匹配覆盖 industry 列（ind_code_l1/ind_code_l2 不存在于 PG，已移除）
        ind_clause = " OR ".join(
            [
                f"industry ILIKE '%{_sql_quote(ind)}%'"
                for ind in expanded_industry_terms
            ]
        )
        if ind_clause:
            sql_parts.append(f"({ind_clause})")
        where_clause = " AND ".join(sql_parts) if sql_parts else "true"
        dsl = (
            "SQL: SELECT symbol, name, close, "
            "total_mv as market_cap, pe_ttm as pe_ratio, pb as pb_ratio "
            f"FROM {LATEST_TABLE} WHERE {where_clause}"
        )
    else:
        dsl = "SELECT symbol WHERE " + (" AND ".join(parts) if parts else "true")
    # If preset filters generated conditions but DSL has no concrete parts, build from presets
    if _preset_qdb_filters and not parts:
        preset_parts = []
        for f in _preset_qdb_filters:
            field = f["field"]
            op = f["operator"]
            val = f["value"]
            op_str = {">=": ">=", "<=": "<=", ">": ">", "<": "<"}.get(op, op)
            if field == "total_mv" and isinstance(val, (int, float)) and val >= 1e8:
                preset_parts.append(f"market_cap {op_str} {val/1e8:.0f}亿")
            elif field == "dividend_rate":
                preset_parts.append(f"dividend_rate {op_str} {val*100:.1f}%")
            else:
                preset_parts.append(f"{field} {op_str} {val}")
        dsl = "SELECT symbol WHERE " + " AND ".join(preset_parts)
    mapping = {"factors": factors, "industry": industry_list, "local_hit": local_hit}
    if quantdb_filters:
        mapping["quantdb_filters"] = quantdb_filters
    if not parts and not industry_list and not quantdb_filters:
        suggestions.append("未识别具体条件, 可尝试使用: 市值100-300, PE 15-20, 行业: 计算机")
    suggestions.extend(loose_mode_hits)
    return dsl, mapping, suggestions


@router.post("/parse-text", response_model=ParseResponse)
async def parse_text(body: ParseTextRequest, request: Request):
    # TODO: 后续迁移到 steps/
    try:
        logger.info("parse_text started", extra={"trace_id": _trace_id(request)})
        if _is_full_market_query(body.text):
            sql = _build_full_market_sql(body.market)
            return ParseResponse(
                dsl=f"SQL: {sql}",
                mapping={
                    "semantic_category": "full_market",
                    "query": body.text,
                    "target_table": "stock_daily",
                    "sql": sql,
                },
                warnings=[],
                confidence=0.95,
                suggestions=["已识别为全市场查询，使用 stock_daily 最新交易日全量数据"],
                version="2.0.0",
            )

        # 优先使用本地正则解析（快速、确定性），LLM 仅在正则无法识别时作为兜底
        local_dsl, local_mapping, local_suggestions = _simple_parse_text(body.text)
        local_hit = local_mapping.get("local_hit", False)
        local_qdb_filters = local_mapping.pop("quantdb_filters", None)

        if local_hit:
            return ParseResponse(
                dsl=local_dsl,
                mapping=local_mapping,
                warnings=[],
                confidence=0.85,
                suggestions=local_suggestions,
                version="local-primary-1.0.0",
                quantdb_filters=local_qdb_filters,
            )

        # 正则无法识别时，降级到 LLM 大模型解析
        parser = get_intent_parser()
        try:
            intent = await parser.parse(body.text)
            generator = get_sql_generator()
            sql = await generator.generate_sql(intent)
        except Exception as llm_err:
            logger.warning("LLM parsing also failed: %s", llm_err)
            sql = None
            intent = {}

        # 检查是否成功生成 SQL
        if sql:
            market_table = get_latest_table(body.market)

            # 修复 LLM 可能生成的错误表名（重复拼接）
            sql = re.sub(r"stock_daily_latest_latest", "stock_daily_latest", sql, flags=re.IGNORECASE)
            sql = re.sub(r"stock_selection_selection", "stock_selection", sql, flags=re.IGNORECASE)

            # 适配表名规范（仅替换未正确使用 market_table 的情况）
            if "from stock_selection" in sql.lower():
                sql = re.sub(r"from\s+stock_selection", f"from {market_table}", sql, flags=re.IGNORECASE)
            if "from stock_daily" in sql.lower() and "from stock_daily_latest" not in sql.lower():
                sql = re.sub(r"from\s+stock_daily(?!\s_latest)", f"from {market_table}", sql, flags=re.IGNORECASE)

            # 若生成的是全市场 SQL，自动对齐口径
            if _is_full_market_sql(sql):
                sql = _build_full_market_sql(body.market)
                intent["semantic_category"] = "full_market"

            dsl = f"SQL: {sql}"
            mapping = {**intent, "sql": sql}
            suggestions = [
                f"已识别为 {intent.get('semantic_category', '通用')} 策略原型",
                f"选用数据表: {intent.get('target_table', 'stock_daily_latest')}",
            ]
            return ParseResponse(
                dsl=dsl,
                mapping=mapping,
                warnings=["正则解析未命中，由 LLM 生成，复杂语义可能受限"],
                confidence=0.7,
                suggestions=suggestions,
                version="llm-fallback-2.0.0",
            )

        # 正则和 LLM 都无法处理
        return ParseResponse(
            dsl=local_dsl,
            mapping=local_mapping,
            warnings=["当前解析结果由基础规则生成，复杂语义可能受限"],
            confidence=0.5,
            suggestions=local_suggestions or ["未识别具体条件，可尝试: 市值100-300亿, PE<20, 行业: 计算机"],
            version="local-fallback-1.0.0",
        )
    except Exception as e:
        logger.error("parse_text failed: %s", e)
        # 最后的最后，尝试最简单的解析
        try:
            dsl, mapping, suggestions = _simple_parse_text(body.text)
            return ParseResponse(dsl=dsl, mapping=mapping, suggestions=suggestions)
        except:
            raise HTTPException(status_code=400, detail=f"解析完全失败: {e}")
    except Exception as e:
        logger.error("parse_text failed: %s", e)
        try:
            dsl, mapping, suggestions = _simple_parse_text(body.text)
            return ParseResponse(dsl=dsl, mapping=mapping, suggestions=suggestions)
        except:
            raise HTTPException(status_code=400, detail=f"解析失败: {e}")


# ============================================================================
