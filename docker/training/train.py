#!/usr/bin/env python3
"""
QuantMind 云端训练脚本 (CVM 容器内运行)
=========================================
参数传递方式：YAML 配置文件（固化在镜像中，参数通过挂载的 config.yaml 传入）

用法：
  docker run -v /host/workspace:/workspace quantmind:latest --config /workspace/config.yaml

config.yaml 结构：
  run_id / job_name
  data.train_start / data.train_end / data.features
  model.type / model.num_boost_round / model.val_ratio / model.params
  output.result_path
  callback.url / callback.secret
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests
import torch
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("quantmind.train")


# ── 硬件环境检测 ──────────────────────────────────────────────────────────────
def detect_hardware() -> dict[str, Any]:
    """检测运行环境的硬件配置（CPU、内存、GPU）。"""
    import os
    info: dict[str, Any] = {"cpu_count": os.cpu_count() or 1, "gpu_available": False, "gpu_count": 0, "gpu_name": "", "mem_total_gb": 0.0}
    try:
        import psutil
        info["mem_total_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            info["gpu_available"] = True
            info["gpu_count"] = torch.cuda.device_count()
            info["gpu_name"] = torch.cuda.get_device_name(0) if info["gpu_count"] > 0 else ""
    except ImportError:
        pass
    logger.info("Hardware: cpu=%d, mem=%.1fGB, gpu=%s(%d), gpu_name=%s",
                info["cpu_count"], info["mem_total_gb"],
                info["gpu_available"], info["gpu_count"], info["gpu_name"])
    return info


# ── 模型默认参数 ──────────────────────────────────────────────────────────────
DEFAULT_LGB_PARAMS: dict[str, Any] = {
    "objective":         "regression",
    "metric":            "l2",
    "boosting":          "gbdt",
    "num_leaves":        31,
    "learning_rate":     0.05,
    "feature_fraction":  0.6,
    "bagging_fraction":  0.7,
    "bagging_freq":      5,
    "min_child_samples": 50,
    "lambda_l1":         0.1,
    "lambda_l2":         1.0,
    "max_depth":         6,
    "path_smooth":       0.5,
    "n_jobs":            -1,
    "verbosity":         -1,
}

DEFAULT_XGB_PARAMS: dict[str, Any] = {
    "objective":        "reg:squarederror",
    "eval_metric":      "rmse",
    "max_depth":        6,
    "learning_rate":    0.05,
    "subsample":        0.7,
    "colsample_bytree": 0.6,
    "reg_alpha":        0.1,
    "reg_lambda":       1.0,
    "min_child_weight": 50,
    "tree_method":      "hist",
    "nthread":          -1,
    "verbosity":        0,
}

DEFAULT_CATBOOST_PARAMS: dict[str, Any] = {
    "loss_function":    "RMSE",
    "depth":            6,
    "learning_rate":    0.05,
    "iterations":       1000,
    "l2_leaf_reg":      3.0,
    "random_strength":  1.0,
    "bagging_temperature": 0.8,
    "od_type":          "Iter",
    "od_wait":          50,
    "thread_count":     -1,
    "verbose":          100,
}

# 支持的模型类型集合
_TREE_MODEL_TYPES = {"lightgbm", "xgboost", "catboost", "linear"}
_DL_MODEL_TYPES = {"gru", "lstm", "alstm", "transformer", "tabnet", "tcn"}
_ALL_MODEL_TYPES = _TREE_MODEL_TYPES | _DL_MODEL_TYPES
_ENSEMBLE_MODEL_TYPES = _TREE_MODEL_TYPES - {"linear"}  # 可参与集成的树模型

TRAINING_BASE_FEATURES: list[str] = [
    "mom_ret_1d",
    "mom_ret_5d",
    "mom_ret_20d",
    "liq_volume",
    "liq_amount",
    "liq_turnover_os",
]
_ALLOWED_SHAP_SPLIT = {"valid", "test", "train"}
_DEFAULT_EXPLAIN_CFG: dict[str, Any] = {
    "enable_shap": True,
    "shap_split": "valid",
    "shap_sample_rows": 30000,
}
_DEFAULT_SHAP_SAMPLE_ROWS = 30000
_MIN_SHAP_SAMPLE_ROWS = 1000
_MAX_SHAP_SAMPLE_ROWS = 100000
_SHAP_SAMPLE_RANDOM_STATE = 42


def _sanitize_nan_inf(obj):
    """递归替换 NaN/Inf 为 None，确保 JSON 可序列化。"""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize_nan_inf(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan_inf(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _load_local_parquet(
    local_dir: Path,
    year: int,
    required_columns: list[str],
    clip_start: pd.Timestamp | None = None,
    clip_end: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    file_path = local_dir / f"model_features_{year}.parquet"
    if not file_path.exists():
        return None
    try:
        logger.info(f"Local data hit: {file_path}")

        schema_cols = set(pq.ParquetFile(file_path).schema_arrow.names)
        selected_cols = [c for c in required_columns if c in schema_cols]
        if "trade_date" not in selected_cols or "symbol" not in selected_cols:
            logger.warning(
                "Skip parquet missing required base columns trade_date/symbol: %s",
                file_path,
            )
            return None
        df = pd.read_parquet(file_path, columns=selected_cols, engine="pyarrow")

        # 先按日期裁剪每年数据，避免把无关年份全量堆进内存
        if "trade_date" in df.columns and (clip_start is not None or clip_end is not None):
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            mask = pd.Series(True, index=df.index)
            if clip_start is not None:
                mask &= df["trade_date"] >= clip_start
            if clip_end is not None:
                mask &= df["trade_date"] <= clip_end
            df = df.loc[mask].copy()

        # 数值列统一降为 float32，降低内存峰值
        for col in df.columns:
            if col in {"trade_date", "symbol"}:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].astype(np.float32, copy=False)

        return df
    except Exception as exc:
        logger.warning(f"  ⚠ Failed to read local parquet {file_path}: {exc}")
        return None


# ── 评估指标 ─────────────────────────────────────────────────────────────────
def _ic(pred: np.ndarray, label: np.ndarray) -> float:
    mask = np.isfinite(pred) & np.isfinite(label)
    if mask.sum() < 10:
        return float("nan")
    return float(np.corrcoef(pred[mask], label[mask])[0, 1])


def _rank_ic_series(df: pd.DataFrame, pred_col: str, label_col: str) -> list[float]:
    daily = []
    for _, g in df.groupby("trade_date", sort=False):
        g = g[[pred_col, label_col]].dropna()
        if len(g) < 10:
            continue
        rp = g[pred_col].rank(method="average").to_numpy()
        rl = g[label_col].rank(method="average").to_numpy()
        v = _ic(rp, rl)
        if np.isfinite(v):
            daily.append(v)
    return daily


def _compute_metrics(df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    ic     = _ic(y_pred, y_true)
    series = _rank_ic_series(df.assign(_pred=y_pred, _label=y_true), "_pred", "_label")
    rank_ic   = float(np.nanmean(series)) if series else float("nan")
    rank_icir = float(np.mean(series) / (np.std(series) + 1e-9)) if series else float("nan")
    rmse = float(np.sqrt(np.mean(np.square(y_pred - y_true)))) if len(y_true) else float("nan")
    labels = (y_true > 0).astype(int)
    pos = int(labels.sum())
    neg = int(len(labels) - pos)
    auc = float("nan")
    if pos > 0 and neg > 0:
        ranks = pd.Series(y_pred).rank(method="average").to_numpy()
        auc = float((ranks[labels == 1].sum() - pos * (pos + 1) / 2.0) / (pos * neg))
    return {"ic": ic, "rank_ic": rank_ic, "rank_icir": rank_icir, "rmse": rmse, "auc": auc}


def _normalize_explain_cfg(raw: Any) -> dict[str, Any]:
    explain = raw if isinstance(raw, dict) else {}
    enable_shap = bool(explain.get("enable_shap", _DEFAULT_EXPLAIN_CFG["enable_shap"]))

    shap_split = str(explain.get("shap_split", _DEFAULT_EXPLAIN_CFG["shap_split"])).strip().lower()
    if shap_split not in _ALLOWED_SHAP_SPLIT:
        logger.warning("Invalid explain.shap_split=%s, fallback to 'valid'", shap_split)
        shap_split = "valid"

    sample_rows_raw = explain.get("shap_sample_rows", _DEFAULT_EXPLAIN_CFG["shap_sample_rows"])
    try:
        sample_rows = int(sample_rows_raw)
    except Exception:
        logger.warning("Invalid explain.shap_sample_rows=%s, fallback to %d", sample_rows_raw, _DEFAULT_SHAP_SAMPLE_ROWS)
        sample_rows = _DEFAULT_SHAP_SAMPLE_ROWS
    sample_rows = max(_MIN_SHAP_SAMPLE_ROWS, min(_MAX_SHAP_SAMPLE_ROWS, sample_rows))

    return {
        "enable_shap": enable_shap,
        "shap_split": shap_split,
        "shap_sample_rows": sample_rows,
    }


def _resolve_shap_source_frame(
    split_frames: dict[str, pd.DataFrame],
    preferred_split: str,
) -> tuple[str, pd.DataFrame]:
    ordered = [preferred_split] + [s for s in ("valid", "test", "train") if s != preferred_split]
    for split in ordered:
        frame = split_frames.get(split)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return split, frame
    return "", pd.DataFrame()


def _compute_shap_summary(
    *,
    model: lgb.Booster,
    split_frames: dict[str, pd.DataFrame],
    features: list[str],
    fill_values: dict[str, float],
    explain_cfg: dict[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    shap_info: dict[str, Any] = {
        "enabled": bool(explain_cfg.get("enable_shap", True)),
        "status": "disabled",
        "split": str(explain_cfg.get("shap_split", "valid")),
        "rows_requested": int(explain_cfg.get("shap_sample_rows", _DEFAULT_SHAP_SAMPLE_ROWS)),
        "rows_used": 0,
        "file": "",
        "error": "",
        "elapsed_seconds": 0.0,
    }
    if not shap_info["enabled"]:
        return shap_info

    if not features:
        shap_info["status"] = "skipped"
        shap_info["error"] = "no_feature_columns"
        return shap_info

    start_ts = time.time()
    try:
        preferred_split = str(explain_cfg.get("shap_split", "valid")).strip().lower()
        selected_split, split_df = _resolve_shap_source_frame(split_frames, preferred_split)
        if split_df.empty:
            shap_info["status"] = "skipped"
            shap_info["error"] = "no_rows_for_shap"
            return shap_info

        rows_requested = int(explain_cfg.get("shap_sample_rows", _DEFAULT_SHAP_SAMPLE_ROWS))
        sample_df = split_df
        if len(sample_df) > rows_requested:
            sample_df = sample_df.sample(rows_requested, random_state=_SHAP_SAMPLE_RANDOM_STATE)

        x_df = sample_df[features].copy()
        for c in features:
            fill_v = fill_values.get(c, 0.0)
            if fill_v is None or (isinstance(fill_v, float) and np.isnan(fill_v)):
                fill_v = 0.0
            x_df[c] = x_df[c].astype("float32").fillna(fill_v)
        x = x_df.to_numpy(dtype=np.float32)

        contrib = model.predict(
            x,
            num_iteration=model.best_iteration or None,
            pred_contrib=True,
        )
        if not isinstance(contrib, np.ndarray) or contrib.ndim != 2:
            raise RuntimeError(f"unexpected SHAP contribution shape: {getattr(contrib, 'shape', None)}")
        if contrib.shape[1] < len(features):
            raise RuntimeError(f"contrib columns mismatch: got {contrib.shape[1]}, expect >= {len(features)}")

        shap_values = contrib[:, :len(features)]
        summary_df = pd.DataFrame(
            {
                "feature": features,
                "mean_abs_shap": np.mean(np.abs(shap_values), axis=0),
                "mean_shap": np.mean(shap_values, axis=0),
                "positive_ratio": np.mean(shap_values > 0, axis=0),
            }
        ).sort_values("mean_abs_shap", ascending=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(out_path, index=False)

        shap_info.update(
            {
                "status": "completed",
                "split": selected_split,
                "rows_requested": rows_requested,
                "rows_used": int(len(sample_df)),
                "file": out_path.name,
                "error": "",
            }
        )
        return shap_info
    except Exception as exc:  # noqa: BLE001
        logger.exception("SHAP summary generation failed: %s", exc)
        shap_info["status"] = "failed"
        shap_info["error"] = str(exc)
        return shap_info
    finally:
        shap_info["elapsed_seconds"] = float(time.time() - start_ts)


# ── 数据加载 ──────────────────────────────────────────────────────────────────
_MARKET_PARQUET_FILES: dict[str, str] = {
    "HK": "model_features_hk.parquet",
    "US": "model_features_us.parquet",
    "CRYPTO": "model_features_crypto.parquet",
}


def load_data(
    train_start: str,
    train_end: str,
    features: list[str],
    target_horizon_days: int = 1,
    cache_dir: str | None = None,
    valid_end: str | None = None,
    test_end: str | None = None,
    source_mode: str = "LOCAL",
    local_dir: str | None = None,
    market: str = "CN",
    industry_as_feature: bool = False,
) -> tuple:
    local_root = Path(local_dir).expanduser() if local_dir else None
    if local_root is None:
        raise RuntimeError("local_dir must be provided; COS data download has been removed")

    market_upper = str(market or "CN").upper()

    # 仅读取训练必需列，避免整表加载导致 OOM
    horizon = max(1, int(target_horizon_days or 1))
    horizon_col = f"mom_ret_{horizon}d"
    required_columns = list(
        dict.fromkeys(
            ["trade_date", "symbol", "mom_ret_1d", horizon_col, "is_st", "volume"]
            + list(features)
        )
    )
    logger.info(
        "Memory-optimized read: selected %d columns (horizon=%s, market=%s)",
        len(required_columns),
        horizon,
        market_upper,
    )

    # 给标签构建预留边界，避免裁剪过早影响 shift/rolling
    range_start = pd.Timestamp(train_start) - pd.Timedelta(days=max(7, horizon + 3))
    upper_bound = test_end or valid_end or train_end
    range_end = pd.Timestamp(upper_bound) + pd.Timedelta(days=max(7, horizon + 3))

    if market_upper in _MARKET_PARQUET_FILES:
        # ── 非 A 股市场：从单一 parquet 文件加载 ──
        parquet_name = _MARKET_PARQUET_FILES[market_upper]
        parquet_path = local_root / parquet_name
        if not parquet_path.exists():
            raise RuntimeError(
                f"市场 {market_upper} parquet 文件不存在: {parquet_path}"
            )
        logger.info("Loading market-specific parquet: %s", parquet_path)

        # 非 A 股文件使用 'instrument' 列而非 'symbol'
        # 先检查 parquet schema，过滤掉不存在的列（如 mom_ret_2d）
        schema_cols = set(pq.ParquetFile(parquet_path).schema_arrow.names)
        # symbol/instrument 列名兼容
        has_symbol = "symbol" in schema_cols
        has_instrument = "instrument" in schema_cols
        valid_cols = []
        missing_cols = []
        for c in required_columns:
            if c in schema_cols:
                valid_cols.append(c)
            elif c == "symbol" and has_instrument:
                valid_cols.append("instrument")
            else:
                missing_cols.append(c)
        if missing_cols:
            logger.warning("Columns not in parquet (skipped): %s", missing_cols)

        try:
            df = pd.read_parquet(parquet_path, columns=valid_cols, engine="pyarrow")
        except Exception:
            df = pd.read_parquet(parquet_path, columns=valid_cols, engine="pyarrow")
        if "instrument" in df.columns and "symbol" not in df.columns:
            df = df.rename(columns={"instrument": "symbol"})

        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df = df[df["trade_date"].notna()].copy()
        # 日期裁剪
        mask = (df["trade_date"] >= range_start) & (df["trade_date"] <= range_end)
        df = df.loc[mask].copy()
        logger.info("Market %s raw data: %d rows, date range: %s to %s",
                     market_upper, len(df),
                     df["trade_date"].min() if not df.empty else "N/A",
                     df["trade_date"].max() if not df.empty else "N/A")
    else:
        # ── A 股：优先使用 core parquet（78列），回退到年度 parquet 文件 ──
        core_parquet_path = local_root / "model_features_core.parquet"

        if core_parquet_path.exists():
            # 使用精简版 core parquet（78列，内存友好）
            logger.info("Using core parquet (78 factors): %s", core_parquet_path)

            schema_cols = set(pq.ParquetFile(core_parquet_path).schema_arrow.names)
            valid_cols = [c for c in required_columns if c in schema_cols]
            missing_cols = [c for c in required_columns if c not in schema_cols]
            if missing_cols:
                logger.warning("Columns not in core parquet (skipped): %s", missing_cols)

            if "trade_date" not in valid_cols or "symbol" not in valid_cols:
                raise RuntimeError("Core parquet missing required columns: trade_date or symbol")

            df = pd.read_parquet(core_parquet_path, columns=valid_cols, engine="pyarrow")
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            df = df[df["trade_date"].notna()].copy()

            # 日期裁剪
            mask = (df["trade_date"] >= range_start) & (df["trade_date"] <= range_end)
            df = df.loc[mask].copy()

            # 数值列统一降为 float32
            for col in df.columns:
                if col in {"trade_date", "symbol"}:
                    continue
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].astype(np.float32, copy=False)

            logger.info("Core parquet loaded: %d rows, date range: %s to %s",
                       len(df),
                       df["trade_date"].min() if not df.empty else "N/A",
                       df["trade_date"].max() if not df.empty else "N/A")
        else:
            # 回退到年度 parquet 文件（197列，内存占用大）
            logger.warning("Core parquet not found, falling back to yearly parquet files")
            start_year = pd.Timestamp(train_start).year
            ends = [train_end]
            if valid_end: ends.append(valid_end)
            if test_end: ends.append(test_end)
            end_year = max(pd.Timestamp(e).year for e in ends)

            chunks = []
            for year in range(max(start_year - 1, 2016), end_year + 1):
                df_year = _load_local_parquet(
                    local_root,
                    year,
                    required_columns=required_columns,
                    clip_start=range_start,
                    clip_end=range_end,
                )
                if df_year is not None:
                    if not df_year.empty:
                        chunks.append(df_year)
                else:
                    logger.warning(f"No data file found for year {year} in {local_root}, skipping")

            if not chunks:
                raise RuntimeError("No data loaded from local storage")

            df = pd.concat(chunks, axis=0, ignore_index=True)
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            df = df[df["trade_date"].notna()].copy()
            logger.info(f"Raw concat size: {len(df)} rows. Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")

        # 过滤北交所代码（4/8开头）——仅 A 股
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df = df[~df["symbol"].str.startswith(("4", "8"))].copy()
        logger.info(f"After symbol filter: {len(df)} rows")

        # 过滤 ST/*ST 股票
        if "is_st" in df.columns:
            before = len(df)
            df["is_st"] = pd.to_numeric(df["is_st"], errors="coerce").fillna(0).astype(int)
            df = df[df["is_st"] == 0].copy()
            logger.info(f"After ST filter: {len(df)} rows (removed {before - len(df)} ST rows)")

        # 行业条件化：合并 ind_code_l1（CSRC 一级行业编码）
        if industry_as_feature or "ind_code_l1" in features:
            try:
                ind_detail_path = local_root / "2_base_sector" / "instrument_detail" / "instrument_detail.parquet"
                if ind_detail_path.exists():
                    ind_df = pd.read_parquet(ind_detail_path, engine="pyarrow")
                    sym_col = "symbol" if "symbol" in ind_df.columns else "wind_code" if "wind_code" in ind_df.columns else None
                    if sym_col and "rs_hycode_sim" in ind_df.columns:
                        ind_map = ind_df[[sym_col, "rs_hycode_sim"]].dropna()
                        ind_map = ind_map.rename(columns={sym_col: "symbol", "rs_hycode_sim": "ind_code_l1"})
                        ind_map["symbol"] = ind_map["symbol"].astype(str).str.zfill(6)
                        ind_map["ind_code_l1"] = pd.Categorical(ind_map["ind_code_l1"]).codes.astype(np.float32)
                        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
                        df = df.merge(ind_map, on="symbol", how="left")
                        df["ind_code_l1"] = df["ind_code_l1"].fillna(-1).astype(np.float32)
                        logger.info("Industry mapping merged: %d/%d rows have ind_code_l1",
                                    (df["ind_code_l1"] >= 0).sum(), len(df))
                    else:
                        logger.warning("instrument_detail.parquet missing symbol/wind_code or rs_hycode_sim columns")
                else:
                    logger.warning("instrument_detail.parquet not found at %s", ind_detail_path)
            except Exception as e:
                logger.warning("Failed to merge industry data (non-fatal): %s", e)

    # 剔除节假日填充行：QuantDB parquet 含约 6.6% 的假交易日
    # （close>0、mom_ret_1d=0，但全市场 volume==0），如春节/清明/劳动节。
    # 必须在 label 构造前剔除：shift(-N) 按行位移，若序列含假日，
    # "未来 N 个交易日收益" 实际只跨 N-k 个真实交易日，导致标签时间尺度不一致。
    if "volume" in df.columns:
        _day_vol = df.groupby("trade_date")["volume"].max()
        _real_days = _day_vol[_day_vol > 0].index
        _dropped_days = len(_day_vol) - len(_real_days)
        if _dropped_days > 0:
            _rows_before = len(df)
            df = df[df["trade_date"].isin(_real_days)].copy()
            logger.info(
                "Dropped %d non-trading days (holiday fill rows): %d -> %d rows",
                _dropped_days, _rows_before, len(df),
            )
    else:
        logger.warning(
            "Column 'volume' unavailable — cannot filter holiday fill rows; "
            "labels may span fewer real trading days than target_horizon_days"
        )

    # 标签：基于 target_horizon_days 构建 N 日远期收益
    # 注：mom_ret_{N}d 列是过去 N 日收益（backward-looking），如 mom_ret_5d[T] = (close[T]-close[T-5])/close[T-5]
    # shift(-N) 后，行 T 得到行 T+N 的值 = (close[T+N]-close[T])/close[T]，即正确的 N 日远期收益
    # 等价于: label = next_N_day_return = pct_change(N).shift(-N)
    if "mom_ret_1d" not in df.columns:
        raise RuntimeError("Column 'mom_ret_1d' not found in parquet")

    # 从参数读取预测周期（不依赖全局 cfg）
    _horizon = max(1, int(target_horizon_days or 1))

    df = df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    _mom_col = f"mom_ret_{_horizon}d"
    if _horizon == 1:
        df["label"] = df.groupby("symbol")["mom_ret_1d"].shift(-1)
    elif _mom_col in df.columns:
        df["label"] = df.groupby("symbol")[_mom_col].shift(-_horizon)
    else:
        # 回退：通过滚动累乘 1d 收益构造 N 日远期收益
        df["label"] = (
            df.groupby("symbol")["mom_ret_1d"]
            .transform(lambda s: (1 + s).rolling(_horizon).apply(np.prod, raw=True) - 1)
            .shift(-_horizon)
        )
    logger.info(f"Label built with target_horizon_days={_horizon} (column={_mom_col if _mom_col in df.columns else 'rolling'})")

    valid_count_before = len(df)
    df = df[df["label"].notna()].copy()
    logger.info(f"After label shift & dropna: {len(df)} rows (dropped {valid_count_before - len(df)} rows with missing labels)")

    # 裁剪到请求日期范围
    mask = (df["trade_date"] >= train_start) & (df["trade_date"] <= train_end)
    # 如果有验证集/测试集，扩大 mask 范围以包含它们
    if valid_end:
        mask = (df["trade_date"] >= train_start) & (df["trade_date"] <= valid_end)
    if test_end:
        mask = (df["trade_date"] >= train_start) & (df["trade_date"] <= test_end)

    df = df[mask].copy()
    logger.info(f"After date range clip ({train_start} to {test_end or valid_end or train_end}): {len(df)} rows")

    # 校验特征列
    missing = [f for f in features if f not in df.columns]
    if missing:
        logger.warning(f"Features not found in parquet (ignored): {missing}")
        features = [f for f in features if f in df.columns]
    if not features:
        raise RuntimeError("No valid feature columns found")

    keep_cols = ["symbol", "trade_date", "label"] + features
    df = df[keep_cols].reset_index(drop=True)

    # 截面 rank 标准化标签
    df["label"] = df.groupby("trade_date")["label"].rank(pct=True) - 0.5

    logger.info(
        f"Data ready: {len(df):,} rows, {len(features)} features, "
        f"{df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}"
    )
    return df, features


# ── 训练 ──────────────────────────────────────────────────────────────────────

def _split_data(df: pd.DataFrame, cfg: dict) -> tuple:
    """数据切分：显式 split 优先于 val_ratio。返回 (train_df, val_df, test_df)。"""
    model_cfg = cfg.get("model", {})

    def _frame_range_text(frame: pd.DataFrame) -> str:
        if frame.empty:
            return "EMPTY"
        return f"{frame['trade_date'].min().date()}~{frame['trade_date'].max().date()}"

    split_cfg = cfg.get("split", {})
    if split_cfg.get("valid"):
        valid_start_str, valid_end_str = split_cfg["valid"]
        requested_train = f"{split_cfg['train'][0]}~{split_cfg['train'][1]}"
        requested_val = f"{valid_start_str}~{valid_end_str}"
        train_df = df[df["trade_date"] <= pd.Timestamp(split_cfg["train"][1])].copy()
        val_df   = df[
            (df["trade_date"] >= pd.Timestamp(valid_start_str)) &
            (df["trade_date"] <= pd.Timestamp(valid_end_str))
        ].copy()
        if split_cfg.get("test"):
            test_start_str, test_end_str = split_cfg["test"]
            requested_test = f"{test_start_str}~{test_end_str}"
            test_df = df[
                (df["trade_date"] >= pd.Timestamp(test_start_str)) &
                (df["trade_date"] <= pd.Timestamp(test_end_str))
            ].copy()
        else:
            requested_test = requested_val
            test_df = val_df.copy()
        logger.info(f"Split mode: train~{split_cfg['train'][1]}  val {valid_start_str}~{valid_end_str}")
    else:
        val_ratio = float(model_cfg.get("val_ratio") or 0.15)
        dates = sorted(df["trade_date"].unique())
        if not dates:
            raise RuntimeError("No rows available for split after preprocessing. 请检查训练时间窗口与特征快照覆盖范围。")
        val_start = dates[int(len(dates) * (1 - val_ratio))]
        train_df  = df[df["trade_date"] < val_start].copy()
        val_df    = df[df["trade_date"] >= val_start].copy()
        test_df = val_df.copy()
        train_start = pd.Timestamp(df["trade_date"].min()).date()
        train_end = (pd.Timestamp(val_start) - pd.Timedelta(days=1)).date()
        requested_train = f"{train_start}~{train_end}"
        requested_val = f"{pd.Timestamp(val_start).date()}~{pd.Timestamp(df['trade_date'].max()).date()}"
        requested_test = requested_val
        logger.info(
            f"val_ratio mode: train~{pd.Timestamp(val_start).date() - pd.Timedelta(days=1)}"
            f"  val {pd.Timestamp(val_start).date()}~"
        )

    if train_df.empty or val_df.empty or test_df.empty:
        available_range = "EMPTY"
        if not df.empty:
            available_range = f"{df['trade_date'].min().date()}~{df['trade_date'].max().date()}"
        raise RuntimeError(
            "Dataset split contains empty segment. "
            f"available={available_range}; "
            f"train={len(train_df)}({_frame_range_text(train_df)}) requested={requested_train}; "
            f"val={len(val_df)}({_frame_range_text(val_df)}) requested={requested_val}; "
            f"test={len(test_df)}({_frame_range_text(test_df)}) requested={requested_test}. "
            "请调整 train/valid/test 时间窗口，确保三段均与可用数据重叠。"
        )
    return train_df, val_df, test_df


def _prepare_arrays(train_df: pd.DataFrame, val_df: pd.DataFrame, features: list[str]) -> tuple:
    """计算 fill_values 并转换为 numpy 数组。返回 (fill_values, X_train, y_train, X_val, y_val, _fill_fn)。"""
    import math
    fill_values_raw = train_df[features].median().to_dict()
    fill_values = {k: (0.0 if (isinstance(v, float) and math.isnan(v)) else v) for k, v in fill_values_raw.items()}

    def _fill(frame: pd.DataFrame) -> np.ndarray:
        x = frame[features].copy()
        for c in features:
            x[c] = x[c].astype("float32").fillna(fill_values[c])
        return x.to_numpy(dtype=np.float32)

    X_train = _fill(train_df)
    y_train = train_df["label"].astype("float32").to_numpy()
    X_val = _fill(val_df)
    y_val = val_df["label"].astype("float32").to_numpy()
    return fill_values, X_train, y_train, X_val, y_val, _fill


def _train_lgb(cfg: dict, features: list[str], X_train: np.ndarray, y_train: np.ndarray,
               X_val: np.ndarray, y_val: np.ndarray) -> Any:
    """LightGBM 训练。"""
    model_cfg = cfg.get("model", {})
    params = {**DEFAULT_LGB_PARAMS, **model_cfg.get("params", {})}
    num_boost_round = int(model_cfg.get("num_boost_round", 1000))
    early_stopping_rounds = max(1, int(model_cfg.get("early_stopping_rounds", 100) or 100))

    ds_train = lgb.Dataset(X_train, label=y_train, feature_name=features, free_raw_data=True)
    ds_val = lgb.Dataset(X_val, label=y_val, feature_name=features, free_raw_data=True)

    callbacks = [
        lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=True),
        lgb.log_evaluation(100),
    ]
    model = lgb.train(
        params, ds_train,
        num_boost_round=num_boost_round,
        valid_sets=[ds_train, ds_val],
        valid_names=["train", "valid"],
        callbacks=callbacks,
    )
    return model


def _train_xgb(cfg: dict, features: list[str], X_train: np.ndarray, y_train: np.ndarray,
               X_val: np.ndarray, y_val: np.ndarray) -> Any:
    """XGBoost 训练。"""
    import xgboost as xgb
    model_cfg = cfg.get("model", {})
    params = {**DEFAULT_XGB_PARAMS, **model_cfg.get("xgb_params", {})}
    num_boost_round = int(model_cfg.get("num_boost_round", 1000))
    early_stopping_rounds = max(1, int(model_cfg.get("early_stopping_rounds", 100) or 100))

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=features)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=features)

    evals_result: dict = {}
    model = xgb.train(
        params, dtrain,
        num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "valid")],
        evals_result=evals_result,
        early_stopping_rounds=early_stopping_rounds,
        verbose_eval=100,
    )
    return model


def _train_catboost(cfg: dict, features: list[str], X_train: np.ndarray, y_train: np.ndarray,
                    X_val: np.ndarray, y_val: np.ndarray) -> Any:
    """CatBoost 训练。支持 cat_features（行业编码等类别特征）。"""
    from catboost import CatBoost, Pool
    model_cfg = cfg.get("model", {})
    params = {**DEFAULT_CATBOOST_PARAMS, **model_cfg.get("catboost_params", {})}
    # iterations 覆盖 num_boost_round
    if "iterations" not in model_cfg.get("catboost_params", {}):
        params["iterations"] = int(model_cfg.get("num_boost_round", 1000))

    # 识别类别特征（ind_code_l1 等）
    cat_feature_indices = []
    for i, feat in enumerate(features):
        if feat in ("ind_code_l1", "ind_code_l2"):
            cat_feature_indices.append(i)
    if cat_feature_indices:
        # CatBoost 要求类别特征为 int 类型
        for idx in cat_feature_indices:
            X_train[:, idx] = X_train[:, idx].astype(int)
            X_val[:, idx] = X_val[:, idx].astype(int)

    train_pool = Pool(X_train, label=y_train, feature_names=features,
                      cat_features=cat_feature_indices if cat_feature_indices else None)
    val_pool = Pool(X_val, label=y_val, feature_names=features,
                    cat_features=cat_feature_indices if cat_feature_indices else None)

    model = CatBoost(params)
    model.fit(train_pool, eval_set=val_pool, early_stopping_rounds=max(1, int(model_cfg.get("early_stopping_rounds", 100) or 100)))
    return model


def _train_linear(cfg: dict, features: list[str], X_train: np.ndarray, y_train: np.ndarray,
                  X_val: np.ndarray, y_val: np.ndarray) -> Any:
    """Linear 模型训练（Ridge 回归）。"""
    from sklearn.linear_model import Ridge
    model_cfg = cfg.get("model", {})
    dl_params = model_cfg.get("dl_params", {})
    alpha = float(dl_params.get("alpha", 1.0))
    model = Ridge(alpha=alpha)
    model.fit(X_train, y_train)
    return model


# ── 深度学习训练 ────────────────────────────────────────────────────────────────

# Qlib TS 模型映射: model_type → (qlib_module, qlib_class)
_QLIB_TS_MODEL_MAP: dict[str, tuple[str, str]] = {
    "gru":         ("qlib.contrib.model.pytorch_gru_ts",         "GRU"),
    "lstm":        ("qlib.contrib.model.pytorch_lstm_ts",        "LSTM"),
    "alstm":       ("qlib.contrib.model.pytorch_alstm_ts",       "ALSTM"),
    "transformer": ("qlib.contrib.model.pytorch_transformer_ts", "Transformer"),
    "tcn":         ("qlib.contrib.model.pytorch_tcn_ts",         "TCN"),
}
_QLIB_FLAT_MODEL_MAP: dict[str, tuple[str, str]] = {
    "tabnet":      ("qlib.contrib.model.pytorch_tabnet",         "TabNet"),
}
_QLIB_MODEL_MAP = {**_QLIB_TS_MODEL_MAP, **_QLIB_FLAT_MODEL_MAP}


class _TSLazyDataset(torch.utils.data.Dataset):
    """Lazy TS dataset: 按需生成滚动窗口，避免一次性加载全部窗口到内存。

    存储原始数据 (per-instrument contiguous arrays)，__getitem__ 时动态切片。
    内存占用: O(total_rows * d_feat) 而非 O(N_windows * step_len * d_feat)。
    """

    def __init__(self, X: np.ndarray, y: np.ndarray, instrument_offsets: list[int], step_len: int):
        self.X = X              # [total_rows, d_feat] float32 contiguous
        self.y = y              # [total_rows] float32
        self.step_len = step_len
        # 每个 instrument 的有效窗口起始行号 (全局索引)
        self.indices: list[int] = []
        for start, end in zip(instrument_offsets[:-1], instrument_offsets[1:]):
            n = end - start
            for i in range(n - step_len + 1):
                self.indices.append(start + i)
        if not self.indices:
            raise ValueError(f"No valid TS samples (step_len={step_len}, rows={len(X)})")

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, idx: int) -> tuple["torch.Tensor", "torch.Tensor"]:
        import torch
        start = self.indices[idx]
        window = self.X[start : start + self.step_len].copy()  # [step_len, d_feat]
        label = self.y[start + self.step_len - 1]
        # Qlib TS 模型期望: data[:, 0:-1] = features, data[-1, -1] = label
        label_col = np.full((self.step_len, 1), np.float32(0.0))
        label_col[-1, 0] = label
        row = np.concatenate([window, label_col], axis=1)  # [step_len, d_feat+1]
        # Qlib train_epoch 期望 (data, weight) 元组
        weight = torch.tensor(1.0, dtype=torch.float32)
        return torch.from_numpy(row), weight


def _build_ts_dataloader(
    df_X: pd.DataFrame,
    df_y: pd.Series,
    step_len: int,
    batch_size: int,
    shuffle: bool = True,
) -> "torch.utils.data.DataLoader":
    """将扁平 DataFrame (MultiIndex: instrument x datetime) 转为 3D DataLoader。

    每个样本是 [step_len, d_feat+1]，最后一列为 label (取自最后一个时间步)。
    使用 LazyDataset 按需生成窗口，内存占用 O(rows * d_feat)。
    """
    import torch
    from torch.utils.data import DataLoader

    X_values = np.ascontiguousarray(df_X.values, dtype=np.float32)
    y_values = np.ascontiguousarray(df_y.values, dtype=np.float32)

    # 填充特征中的 NaN/inf（GRU 只 mask label 中的 NaN，不处理 feature 中的 NaN）
    nan_count = np.isnan(X_values).sum()
    inf_count = np.isinf(X_values).sum()
    if nan_count > 0 or inf_count > 0:
        logger.info("Cleaning features: %d NaN, %d inf -> 0.0", nan_count, inf_count)
        X_values = np.nan_to_num(X_values, nan=0.0, posinf=0.0, neginf=0.0)

    if isinstance(df_X.index, pd.MultiIndex):
        instruments = df_X.index.get_level_values(0).unique()
        # 预计算每个 instrument 在连续数组中的 offset
        offsets = [0]
        for inst in instruments:
            mask = df_X.index.get_level_values(0) == inst
            offsets.append(offsets[-1] + int(mask.sum()))
        # 重排为 instrument-连续布局
        order = np.concatenate([np.where(df_X.index.get_level_values(0) == inst)[0] for inst in instruments])
        X_values = X_values[order]
        y_values = y_values[order]
    else:
        offsets = [0, len(X_values)]

    dataset = _TSLazyDataset(X_values, y_values, offsets, step_len)
    logger.info("TS DataLoader: %d samples from %d rows (step_len=%d)", len(dataset), len(X_values), step_len)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False, num_workers=0)


def _train_dl(
    model_type: str,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    features: list[str],
    dl_params: dict[str, Any],
    output_dir: Path,
    hardware: dict[str, Any] | None = None,
) -> tuple:
    """Qlib 深度学习模型训练。

    返回 (model_obj, train_metrics, val_metrics, dl_metadata)
    """
    import importlib
    import copy
    import torch

    mod_path, cls_name = _QLIB_MODEL_MAP[model_type]
    mod = importlib.import_module(mod_path)
    ModelCls = getattr(mod, cls_name)

    d_feat = len(features)
    is_ts = model_type in _QLIB_TS_MODEL_MAP

    # 构建模型参数
    model_params: dict[str, Any] = {"d_feat": d_feat}
    if model_type == "tabnet":
        model_params.update({
            "n_d":     int(dl_params.get("dl_hidden_size", 64)),
            "n_a":     int(dl_params.get("dl_hidden_size", 64)),
            "n_steps": max(1, int(dl_params.get("dl_num_layers", 3))),
            "lr":      float(dl_params.get("dl_lr", 0.001)),
        })
    else:
        model_params.update({
            "hidden_size": int(dl_params.get("dl_hidden_size", 64)),
            "num_layers":  int(dl_params.get("dl_num_layers", 2)),
            "dropout":     float(dl_params.get("dl_dropout", 0.3)),
        })

    n_epochs    = int(dl_params.get("dl_n_epochs", 200))
    batch_size  = int(dl_params.get("dl_batch_size", 8000))
    lr          = float(dl_params.get("dl_lr", 0.001))
    step_len    = int(dl_params.get("dl_step_len", 20))
    early_stop  = int(dl_params.get("early_stopping_rounds", 20))
    metric_name = str(dl_params.get("metric", "")).lower()

    # 确定 GPU
    gpu_id = 0
    if hardware and not hardware.get("gpu_available"):
        gpu_id = -1
    model_params["GPU"] = gpu_id
    model_params["n_epochs"] = n_epochs
    model_params["lr"] = lr
    model_params["batch_size"] = batch_size
    model_params["early_stop"] = early_stop
    model_params["metric"] = metric_name

    logger.info("DL model: %s, params=%s, is_ts=%s", model_type, model_params, is_ts)

    # 实例化模型
    model_obj = ModelCls(**model_params)

    # 准备训练/验证数据
    X_train = train_df[features]
    y_train = train_df["label"]
    X_val = val_df[features]
    y_val = val_df["label"]

    if is_ts:
        train_loader = _build_ts_dataloader(X_train, y_train, step_len, batch_size, shuffle=True)
        val_loader = _build_ts_dataloader(X_val, y_val, step_len, batch_size, shuffle=False)
        logger.info("TS DataLoader: train_batches=%d, val_batches=%d, step_len=%d",
                     len(train_loader), len(val_loader), step_len)
    else:
        # TabNet: 使用扁平数据
        train_loader = (X_train, y_train)
        val_loader = (X_val, y_val)

    # 训练循环 (直接调用 Qlib 模型的 train_epoch/test_epoch)
    best_score = -np.inf
    best_epoch = 0
    stop_steps = 0
    best_state = None
    evals: dict[str, list[float]] = {"train": [], "valid": []}

    logger.info("DL training: %d epochs, batch_size=%d, lr=%s", n_epochs, batch_size, lr)

    for epoch in range(n_epochs):
        # Train
        model_obj.train_epoch(train_loader) if is_ts else model_obj.train_epoch(X_train, y_train)

        # Evaluate (only on val set — skip train set test for speed)
        if is_ts:
            val_loss, val_score = model_obj.test_epoch(val_loader)
        else:
            val_loss, val_score = model_obj.test_epoch(X_val, y_val)

        train_score = float("nan")  # placeholder, not computed each epoch
        evals["train"].append(train_score)
        evals["valid"].append(val_score)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            logger.info("Epoch %d/%d: valid=%.6f", epoch + 1, n_epochs, val_score)

        if val_score > best_score:
            best_score = val_score
            best_epoch = epoch
            stop_steps = 0
            # 保存最佳状态
            inner_model = getattr(model_obj, "model", None)
            if inner_model is None:
                for attr_name in ("GRU_model", "gru_model", "lstm_model", "alstm_model", "transformer_model", "tcn_model", "tabnet_model"):
                    inner_model = getattr(model_obj, attr_name, None)
                    if inner_model is not None:
                        break
            if inner_model is not None:
                best_state = copy.deepcopy(inner_model.state_dict())
        else:
            stop_steps += 1
            if stop_steps >= early_stop:
                logger.info("Early stop at epoch %d (best=%d, score=%.6f)", epoch, best_epoch, best_score)
                break

    # 恢复最佳模型
    if best_state is not None:
        inner_model = getattr(model_obj, "model", None)
        if inner_model is None:
            for attr_name in ("GRU_model", "gru_model", "lstm_model", "alstm_model", "transformer_model", "tcn_model", "tabnet_model"):
                inner_model = getattr(model_obj, attr_name, None)
                if inner_model is not None:
                    break
        if inner_model is not None:
            inner_model.load_state_dict(best_state)

    # 保存模型
    torch.save(best_state, str(output_dir / "model.pth"))
    logger.info("DL model saved: model.pth (best_epoch=%d, best_score=%.6f)", best_epoch, best_score)

    # 计算指标
    train_m = {"ic": evals["train"][best_epoch] if evals["train"] else float("nan"), "rank_ic": float("nan"), "rank_icir": float("nan"), "rmse": float("nan"), "auc": float("nan")}
    val_m = {"ic": evals["valid"][best_epoch] if evals["valid"] else float("nan"), "rank_ic": float("nan"), "rank_icir": float("nan"), "rmse": float("nan"), "auc": float("nan")}

    # DL 元数据 (供推理重建模型)
    dl_metadata = {
        "model_class_name": cls_name,
        "model_params": {k: v for k, v in model_params.items() if k not in ("GPU", "n_epochs", "lr", "batch_size", "early_stop", "metric")},
        "is_sequence_model": is_ts,
        "input_spec": {
            "tensor_shape": [None, step_len, d_feat] if is_ts else [None, d_feat],
            "feature_columns": features,
        },
        "dl_params": {k: v for k, v in dl_params.items()},
    }

    return model_obj, train_m, val_m, dl_metadata


def _predict_dl(
    model_dir: Path,
    df_X: pd.DataFrame,
    features: list[str],
    dl_metadata: dict[str, Any],
    batch_size: int = 8000,
) -> np.ndarray:
    """加载训练好的 DL 模型并预测。"""
    import importlib
    import torch

    cls_name = dl_metadata.get("model_class_name", "")
    model_params = dl_metadata.get("model_params", {})
    is_ts = dl_metadata.get("is_sequence_model", False)

    # 找到对应的 Qlib 模型类
    model_cls = None
    for _map in (_QLIB_TS_MODEL_MAP, _QLIB_FLAT_MODEL_MAP):
        for _mt, (_mod_path, _cls_name) in _map.items():
            if _cls_name == cls_name:
                mod = importlib.import_module(_mod_path)
                model_cls = getattr(mod, _cls_name)
                break
        if model_cls is not None:
            break

    if model_cls is None:
        raise ValueError(f"Cannot find Qlib model class: {cls_name}")

    model_params["GPU"] = -1  # CPU for inference
    model_obj = model_cls(**model_params)

    # 加载权重
    model_path = model_dir / "model.pth"
    if not model_path.exists():
        raise FileNotFoundError(f"model.pth not found at {model_path}")

    state_dict = torch.load(str(model_path), map_location="cpu")
    inner_model = getattr(model_obj, "model", None)
    if inner_model is None:
        for attr_name in ("GRU_model", "gru_model", "lstm_model", "alstm_model", "transformer_model", "tcn_model", "tabnet_model"):
            inner_model = getattr(model_obj, attr_name, None)
            if inner_model is not None:
                break
    if inner_model is not None:
        inner_model.load_state_dict(state_dict)
    model_obj.fitted = True

    # 预测
    if is_ts:
        step_len = dl_metadata.get("dl_params", {}).get("dl_step_len", 20)
        loader = _build_ts_dataloader(df_X[features], pd.Series(0.0, index=df_X.index), step_len, batch_size, shuffle=False)
        # 找到内部模型（GRU 用 GRU_model，LSTM 用 lstm_model 等）
        inner_model = getattr(model_obj, "model", None)
        if inner_model is None:
            for attr_name in ("GRU_model", "gru_model", "lstm_model", "alstm_model", "transformer_model", "tcn_model", "tabnet_model"):
                inner_model = getattr(model_obj, attr_name, None)
                if inner_model is not None:
                    break
        inner_model.eval() if inner_model is not None else None
        preds = []
        for batch in loader:
            data = batch[0] if isinstance(batch, (list, tuple)) else batch
            feature = data[:, :, 0:-1]
            with torch.no_grad():
                pred = inner_model(feature.float()).detach().cpu().numpy()
            preds.append(pred)
        return np.concatenate(preds)
    else:
        X_values = df_X[features].values.astype(np.float32)
        X_tensor = torch.from_numpy(X_values)
        inner_model = getattr(model_obj, "model", None)
        if inner_model is None:
            for attr_name in ("GRU_model", "gru_model", "lstm_model", "alstm_model", "transformer_model", "tcn_model", "tabnet_model"):
                inner_model = getattr(model_obj, attr_name, None)
                if inner_model is not None:
                    break
        inner_model.eval() if inner_model is not None else None
        preds = []
        for i in range(0, len(X_tensor), batch_size):
            batch = X_tensor[i:i+batch_size]
            with torch.no_grad():
                pred = inner_model(batch.float()).detach().cpu().numpy()
            preds.append(pred)
        return np.concatenate(preds)


def _predict_with_model(model: Any, X: np.ndarray, model_type: str, features: list[str] | None = None) -> np.ndarray:
    """统一预测接口，适配不同框架。"""
    if model_type == "lightgbm":
        return model.predict(X, num_iteration=model.best_iteration)
    elif model_type == "xgboost":
        import xgboost as xgb
        dmat = xgb.DMatrix(X, feature_names=features)
        return model.predict(dmat, iteration_range=(0, model.best_iteration + 1))
    elif model_type == "catboost":
        return model.predict(X)
    elif model_type == "linear":
        return model.predict(X)
    else:
        return model.predict(X)


def _save_model(model: Any, model_type: str, out_dir: Path) -> str:
    """保存模型到文件，返回实际文件名。"""
    if model_type == "lightgbm":
        path = out_dir / "model.lgb"
        model.save_model(str(path))
        return "model.lgb"
    elif model_type == "xgboost":
        path = out_dir / "model.xgb"
        model.save_model(str(path))
        return "model.xgb"
    elif model_type == "catboost":
        path = out_dir / "model.cbm"
        model.save_model(str(path), format="cbm")
        return "model.cbm"
    elif model_type == "linear":
        import pickle
        path = out_dir / "model.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        return "model.pkl"
    elif model_type in _DL_MODEL_TYPES:
        # DL 模型在 _train_dl() 中已保存 model.pth，此处仅返回文件名
        return "model.pth"
    else:
        import pickle
        path = out_dir / "model.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        return "model.pkl"


def _get_model_framework(model_type: str) -> str:
    """返回模型框架名。"""
    mapping = {
        "lightgbm": "lightgbm",
        "xgboost": "xgboost",
        "catboost": "catboost",
        "linear": "sklearn",
        "gru": "pytorch",
        "lstm": "pytorch",
        "alstm": "pytorch",
        "transformer": "pytorch",
        "tra": "pytorch",
        "hist": "pytorch",
        "tabnet": "pytorch",
        "tcn": "pytorch",
    }
    return mapping.get(model_type, "unknown")


def train_model(df: pd.DataFrame, features: list[str], cfg: dict, hardware: dict | None = None) -> tuple:
    """统一训练入口：根据 model_type 路由到对应训练函数。"""
    model_cfg = cfg.get("model", {})
    model_type = str(model_cfg.get("type", "lightgbm")).strip().lower()

    if model_type not in _ALL_MODEL_TYPES:
        raise ValueError(f"Unsupported model_type: {model_type}")

    # 检查深度学习模型是否有 GPU
    if model_type in _DL_MODEL_TYPES and hardware and not hardware.get("gpu_available"):
        logger.warning("DL model '%s' requested but no GPU detected. Training will be slow on CPU.", model_type)

    # 数据切分
    train_df, val_df, test_df = _split_data(df, cfg)
    fill_values, X_train, y_train, X_val, y_val, _fill = _prepare_arrays(train_df, val_df, features)

    # 路由到对应训练函数
    logger.info("Training model: %s (framework=%s)", model_type, _get_model_framework(model_type))
    train_t0 = time.time()

    if model_type == "lightgbm":
        model = _train_lgb(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "xgboost":
        model = _train_xgb(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "catboost":
        model = _train_catboost(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "linear":
        model = _train_linear(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type in _DL_MODEL_TYPES:
        dl_params = model_cfg.get("dl_params", {})
        output_dir = Path("/workspace")
        model, train_m, val_m, dl_metadata = _train_dl(
            model_type, train_df, val_df, features, dl_params, output_dir, hardware=hardware
        )
        train_elapsed = time.time() - train_t0
        logger.info("Training finished in %.2fs (%s)", train_elapsed, model_type)
        logger.info(f"Val IC={val_m['ic']:.4f}")

        # DL 模型生成全窗口预测
        y_full_pred = _predict_dl(output_dir, df, features, dl_metadata)
        full_pred_df = df[["symbol", "trade_date", "label"]].copy()
        full_pred_df["pred"] = y_full_pred
        full_pred_df["split"] = "train"
        full_pred_df.loc[
            (full_pred_df["trade_date"] >= val_df["trade_date"].min()) &
            (full_pred_df["trade_date"] <= val_df["trade_date"].max()),
            "split",
        ] = "valid"
        full_pred_df.loc[
            (full_pred_df["trade_date"] >= test_df["trade_date"].min()) &
            (full_pred_df["trade_date"] <= test_df["trade_date"].max()),
            "split",
        ] = "test"

        # 计算 test 集指标
        test_mask = full_pred_df["split"] == "test"
        y_test_pred = full_pred_df.loc[test_mask, "pred"].values
        y_test_true = full_pred_df.loc[test_mask, "label"].values
        test_m = _compute_metrics(test_df, y_test_true.astype("float32"), y_test_pred.astype("float32"))

        return (
            model,
            fill_values,
            train_m,
            val_m,
            test_m,
            full_pred_df.reset_index(drop=True),
            {
                "train": train_df.reset_index(drop=True),
                "valid": val_df.reset_index(drop=True),
                "test": test_df.reset_index(drop=True),
            },
            model_type,
            dl_metadata,
        )
    else:
        raise ValueError(f"Unsupported model_type: {model_type}")

    train_elapsed = time.time() - train_t0
    logger.info("Training finished in %.2fs (%s)", train_elapsed, model_type)

    # 统一预测 (树模型)
    y_train_pred = _predict_with_model(model, _fill(train_df), model_type, features)
    y_val_pred = _predict_with_model(model, _fill(val_df), model_type, features)
    y_test_pred = _predict_with_model(model, _fill(test_df), model_type, features)
    train_m = _compute_metrics(train_df, y_train, y_train_pred)
    val_m   = _compute_metrics(val_df,   y_val,   y_val_pred)
    test_m  = _compute_metrics(test_df,  test_df["label"].astype("float32").to_numpy(), y_test_pred)

    logger.info(f"Train IC={train_m['ic']:.4f}  RankIC={train_m['rank_ic']:.4f}")
    logger.info(f"Val   IC={val_m['ic']:.4f}    RankIC={val_m['rank_ic']:.4f}  ICIR={val_m['rank_icir']:.4f}")

    # 生成全窗口预测
    full_pred_df = df[["symbol", "trade_date", "label"]].copy()
    full_pred_df["pred"] = _predict_with_model(model, _fill(df), model_type, features)
    full_pred_df["split"] = "train"
    full_pred_df.loc[
        (full_pred_df["trade_date"] >= val_df["trade_date"].min()) &
        (full_pred_df["trade_date"] <= val_df["trade_date"].max()),
        "split",
    ] = "valid"
    full_pred_df.loc[
        (full_pred_df["trade_date"] >= test_df["trade_date"].min()) &
        (full_pred_df["trade_date"] <= test_df["trade_date"].max()),
        "split",
    ] = "test"
    return (
        model,
        fill_values,
        train_m,
        val_m,
        test_m,
        full_pred_df.reset_index(drop=True),
        {
            "train": train_df.reset_index(drop=True),
            "valid": val_df.reset_index(drop=True),
            "test": test_df.reset_index(drop=True),
        },
        model_type,
    )


# ── 因子筛选 ────────────────────────────────────────────────────────────────────
def select_top_factors(
    df: pd.DataFrame,
    features: list[str],
    label_col: str = "label",
    n_top: int = 60,
    ic_threshold: float = 0.02,
    icir_threshold: float = 0.3,
    correlation_threshold: float = 0.85,
) -> tuple[list[str], dict[str, dict]]:
    """专业因子筛选：IC/ICIR 初筛 → 相关性去冗余 → 稳定性检验。

    返回 (selected_features, ic_results)。
    """
    from scipy.stats import spearmanr

    logger.info("=== Factor Selection: IC/ICIR screening ===")
    logger.info("Input: %d features, target top-%d", len(features), n_top)

    # Step 1: 日频 Rank IC 计算
    ic_results: dict[str, dict] = {}
    for feat in features:
        daily_ics = []
        for _, g in df.groupby("trade_date", sort=False):
            valid = g[[feat, label_col]].dropna()
            if len(valid) < 30:
                continue
            ic, _ = spearmanr(valid[feat], valid[label_col])
            if np.isfinite(ic):
                daily_ics.append(ic)
        if len(daily_ics) < 20:
            ic_results[feat] = {"ic_mean": 0.0, "icir": 0.0, "ic_positive_rate": 0.0, "n_days": len(daily_ics)}
            continue
        arr = np.array(daily_ics)
        ic_results[feat] = {
            "ic_mean": float(np.mean(arr)),
            "icir": float(np.mean(arr) / (np.std(arr) + 1e-9)),
            "ic_positive_rate": float(np.mean(arr > 0)),
            "n_days": len(arr),
        }

    # Step 2: IC阈值初筛
    candidates = {
        f: r for f, r in ic_results.items()
        if abs(r["ic_mean"]) >= ic_threshold and abs(r["icir"]) >= icir_threshold
    }
    logger.info("After IC/ICIR threshold: %d candidates (|IC|>=%.2f, |ICIR|>=%.1f)",
                len(candidates), ic_threshold, icir_threshold)

    # Step 3: ICIR 排序 + 贪心去冗余
    sorted_features = sorted(candidates.keys(),
        key=lambda f: abs(candidates[f]["icir"]), reverse=True)

    selected: list[str] = []
    for feat in sorted_features:
        if len(selected) >= n_top:
            break
        if len(selected) == 0:
            selected.append(feat)
            continue
        # 抽样计算相关性（全量可能 OOM）
        sample_n = min(50000, len(df))
        corr_df = df[selected + [feat]].sample(sample_n, random_state=42).corr()
        max_corr = corr_df[feat].drop(feat).abs().max()
        if max_corr < correlation_threshold:
            selected.append(feat)

    logger.info("After correlation pruning (thresh=%.2f): %d selected",
                correlation_threshold, len(selected))

    # Step 4: 稳定性检验（滚动窗口 IC 标准差）
    stable = []
    for feat in selected:
        daily_ics = []
        for _, g in df.groupby("trade_date", sort=False):
            valid = g[[feat, label_col]].dropna()
            if len(valid) < 30:
                continue
            ic, _ = spearmanr(valid[feat], valid[label_col])
            if np.isfinite(ic):
                daily_ics.append(ic)
        if daily_ics:
            # 滚动60日 IC 标准差 / 均值 → 稳定性比率
            rolling_std = pd.Series(daily_ics).rolling(60, min_periods=20).std()
            mean_ic = abs(np.mean(daily_ics))
            if mean_ic > 0 and rolling_std.mean() / (mean_ic + 1e-9) < 2.0:
                stable.append(feat)

    if len(stable) >= 30:
        selected = stable[:n_top]
        logger.info("After stability filter: %d stable factors", len(selected))

    # 输出 top-10 供日志
    for i, feat in enumerate(selected[:10]):
        r = ic_results[feat]
        logger.info("  %2d. %-30s IC=%.4f  ICIR=%.3f  IC>0=%.1f%%",
                    i + 1, feat, r["ic_mean"], r["icir"], r["ic_positive_rate"] * 100)

    return selected, ic_results


# ── 多模型并行训练 ──────────────────────────────────────────────────────────────
def _train_single_model(
    model_type: str,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    df: pd.DataFrame,
    features: list[str],
    cfg: dict,
    hardware: dict | None = None,
) -> dict[str, Any]:
    """训练单个模型，返回结果字典（可序列化）。"""
    logger.info("--- Training %s ---", model_type)
    t0 = time.time()

    model_cfg = cfg.get("model", {})
    fill_values, X_train, y_train, X_val, y_val, _fill = _prepare_arrays(train_df, val_df, features)

    if model_type == "lightgbm":
        model = _train_lgb(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "xgboost":
        model = _train_xgb(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "catboost":
        model = _train_catboost(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type == "linear":
        model = _train_linear(cfg, features, X_train, y_train, X_val, y_val)
    elif model_type in _DL_MODEL_TYPES:
        output_dir = Path("/workspace")
        dl_params = model_cfg.get("dl_params", {})
        model, train_m, val_m, dl_metadata = _train_dl(
            model_type, train_df, val_df, features, dl_params, output_dir, hardware=hardware
        )
        y_full_pred = _predict_dl(output_dir, df, features, dl_metadata)
        full_pred_df = df[["symbol", "trade_date", "label"]].copy()
        full_pred_df["pred"] = y_full_pred
        full_pred_df["split"] = "train"
        full_pred_df.loc[
            (full_pred_df["trade_date"] >= val_df["trade_date"].min()) &
            (full_pred_df["trade_date"] <= val_df["trade_date"].max()), "split"] = "valid"
        full_pred_df.loc[
            (full_pred_df["trade_date"] >= test_df["trade_date"].min()) &
            (full_pred_df["trade_date"] <= test_df["trade_date"].max()), "split"] = "test"
        test_mask = full_pred_df["split"] == "test"
        y_test_pred = full_pred_df.loc[test_mask, "pred"].values
        y_test_true = full_pred_df.loc[test_mask, "label"].values
        test_m = _compute_metrics(test_df, y_test_true.astype("float32"), y_test_pred.astype("float32"))
        elapsed = time.time() - t0
        return {
            "model_type": model_type,
            "model": model,
            "fill_values": fill_values,
            "train_m": train_m,
            "val_m": val_m,
            "test_m": test_m,
            "pred_df": full_pred_df.reset_index(drop=True),
            "split_frames": {"train": train_df.reset_index(drop=True), "valid": val_df.reset_index(drop=True), "test": test_df.reset_index(drop=True)},
            "dl_metadata": dl_metadata,
            "elapsed": elapsed,
        }
    else:
        raise ValueError(f"Unsupported model_type: {model_type}")

    # 树模型预测
    y_train_pred = _predict_with_model(model, _fill(train_df), model_type, features)
    y_val_pred = _predict_with_model(model, _fill(val_df), model_type, features)
    y_test_pred = _predict_with_model(model, _fill(test_df), model_type, features)
    train_m = _compute_metrics(train_df, y_train, y_train_pred)
    val_m = _compute_metrics(val_df, y_val, y_val_pred)
    test_m = _compute_metrics(test_df, test_df["label"].astype("float32").to_numpy(), y_test_pred)

    full_pred_df = df[["symbol", "trade_date", "label"]].copy()
    full_pred_df["pred"] = _predict_with_model(model, _fill(df), model_type, features)
    full_pred_df["split"] = "train"
    full_pred_df.loc[
        (full_pred_df["trade_date"] >= val_df["trade_date"].min()) &
        (full_pred_df["trade_date"] <= val_df["trade_date"].max()), "split"] = "valid"
    full_pred_df.loc[
        (full_pred_df["trade_date"] >= test_df["trade_date"].min()) &
        (full_pred_df["trade_date"] <= test_df["trade_date"].max()), "split"] = "test"

    best_iteration = getattr(model, "best_iteration", None)
    if best_iteration is None and hasattr(model, "get_best_iteration"):
        try:
            best_iteration = model.get_best_iteration()
        except Exception:
            best_iteration = None

    elapsed = time.time() - t0
    logger.info("%s finished in %.2fs, best_iter=%s, val_ic=%.4f, val_icir=%.4f",
                model_type, elapsed, best_iteration, val_m["ic"], val_m["rank_icir"])

    return {
        "model_type": model_type,
        "model": model,
        "fill_values": fill_values,
        "train_m": train_m,
        "val_m": val_m,
        "test_m": test_m,
        "pred_df": full_pred_df.reset_index(drop=True),
        "split_frames": {"train": train_df.reset_index(drop=True), "valid": val_df.reset_index(drop=True), "test": test_df.reset_index(drop=True)},
        "best_iteration": best_iteration,
        "elapsed": elapsed,
    }


def train_multi_models(
    df: pd.DataFrame,
    features: list[str],
    cfg: dict,
    hardware: dict | None = None,
) -> dict[str, Any]:
    """多模型并行训练：数据加载一次，依次训练多个模型，生成对比报告。

    返回 dict 包含：
    - models: {model_type: {model, fill_values, metrics, pred_df, ...}}
    - comparison: 对比报告
    - primary_model_type: 最佳模型类型
    """
    model_cfg = cfg.get("model", {})
    model_types_raw = model_cfg.get("types", [model_cfg.get("type", "lightgbm")])
    if isinstance(model_types_raw, str):
        model_types_raw = [model_types_raw]
    model_types = [str(t).strip().lower() for t in model_types_raw]

    # 验证
    for mt in model_types:
        if mt not in _ALL_MODEL_TYPES:
            raise ValueError(f"Unsupported model_type: {mt}")

    ensemble_method = str(model_cfg.get("ensemble", "none")).strip().lower()
    if ensemble_method not in ("none", "stacking", "blending", "voting"):
        raise ValueError(f"Unsupported ensemble method: {ensemble_method}")

    logger.info("=== Multi-Model Training: %s ===", model_types)
    logger.info("Ensemble method: %s", ensemble_method)

    # 数据切分（共享）
    train_df, val_df, test_df = _split_data(df, cfg)

    # 依次训练每个模型
    model_results: dict[str, dict] = {}
    for mt in model_types:
        model_results[mt] = _train_single_model(
            mt, train_df, val_df, test_df, df, features, cfg, hardware=hardware
        )

    # 生成对比报告
    comparison_rows = []
    for mt, res in model_results.items():
        vm = res["val_m"]
        comparison_rows.append({
            "model_type": mt,
            "val_ic": round(vm["ic"], 6),
            "val_rank_ic": round(vm["rank_ic"], 6),
            "val_rank_icir": round(vm["rank_icir"], 4),
            "val_rmse": round(vm["rmse"], 6),
            "val_auc": round(vm["auc"], 6),
            "test_ic": round(res["test_m"]["ic"], 6),
            "test_rank_ic": round(res["test_m"]["rank_ic"], 6),
            "test_rank_icir": round(res["test_m"]["rank_icir"], 4),
            "elapsed_seconds": round(res["elapsed"], 1),
        })

    # 按 ICIR 排序确定最佳模型
    comparison_rows.sort(key=lambda r: abs(r["val_rank_icir"]), reverse=True)
    best = comparison_rows[0]["model_type"]

    logger.info("=== Model Comparison ===")
    logger.info("%-12s %10s %10s %10s %10s", "Model", "Val IC", "RankIC", "ICIR", "Time(s)")
    for row in comparison_rows:
        logger.info("%-12s %10.4f %10.4f %10.4f %10.1f",
                    row["model_type"], row["val_ic"], row["val_rank_ic"], row["val_rank_icir"], row["elapsed_seconds"])
    logger.info("Best model: %s (val_icir=%.4f)", best, comparison_rows[0]["val_rank_icir"])

    return {
        "models": model_results,
        "comparison": comparison_rows,
        "primary_model_type": best,
        "model_types": model_types,
        "ensemble_method": ensemble_method,
        "split_frames": {"train": train_df.reset_index(drop=True), "valid": val_df.reset_index(drop=True), "test": test_df.reset_index(drop=True)},
    }


def _generate_oof_predictions(
    model_type: str,
    train_df: pd.DataFrame,
    features: list[str],
    cfg: dict,
    n_folds: int = 5,
    hardware: dict | None = None,
) -> tuple[pd.Series, object, dict]:
    """时序扩展窗口 K-Fold 生成 OOF 预测，训练最终全量基模型。

    返回 (oof_pred_series, full_model, fill_values)
    - oof_pred_series: 与 train_df 等长的 OOF 预测（fold 外部分为 NaN）
    - full_model: 在全量 train_df 上训练的最终基模型
    - fill_values: 特征填充值
    """
    dates = sorted(train_df["trade_date"].unique())
    n_dates = len(dates)
    if n_dates < n_folds + 1:
        logger.warning("Too few dates (%d) for %d folds, reducing to %d", n_dates, n_folds, max(1, n_dates - 1))
        n_folds = max(1, n_dates - 1)

    fold_size = n_dates // (n_folds + 1)
    oof_pred = pd.Series(np.nan, index=train_df.index, name="oof_pred")

    for fold_i in range(n_folds):
        train_end_idx = fold_size * (fold_i + 1)
        val_start_idx = train_end_idx
        val_end_idx = min(train_end_idx + fold_size, n_dates)

        if val_end_idx <= val_start_idx:
            continue

        train_dates = set(dates[:train_end_idx])
        val_dates = set(dates[val_start_idx:val_end_idx])

        fold_train = train_df[train_df["trade_date"].isin(train_dates)]
        fold_val = train_df[train_df["trade_date"].isin(val_dates)]

        if len(fold_train) < 100 or len(fold_val) < 10:
            logger.warning("Fold %d too small (train=%d, val=%d), skipping", fold_i, len(fold_train), len(fold_val))
            continue

        # 训练 fold 基模型
        fold_result = _train_single_model(
            model_type, fold_train, fold_val, fold_val,
            train_df, features, cfg, hardware=hardware,
        )
        fold_model = fold_result["model"]
        fill_values = fold_result["fill_values"]

        # 预测 fold 验证集
        X_val = fold_val[features].fillna(fill_values).values
        if model_type == "lightgbm":
            fold_pred = fold_model.predict(X_val)
        elif model_type == "xgboost":
            import xgboost as xgb
            fold_pred = fold_model.predict(xgb.DMatrix(X_val))
        elif model_type == "catboost":
            from catboost import Pool
            fold_pred = fold_model.predict(Pool(X_val))[0].flatten()
        else:
            fold_pred = fold_model.predict(X_val).flatten()

        oof_pred.iloc[fold_val.index] = fold_pred
        logger.info("OOF fold %d: train=%d dates, val=%d dates, pred_rows=%d",
                     fold_i, len(train_dates), len(val_dates), len(fold_val))

    # 训练全量基模型
    val_ratio = cfg.get("model", {}).get("val_ratio", 0.15)
    split_idx = int(len(train_df) * (1 - val_ratio))
    full_train = train_df.iloc[:split_idx]
    full_val = train_df.iloc[split_idx:]

    full_result = _train_single_model(
        model_type, full_train, full_val, full_val,
        train_df, features, cfg, hardware=hardware,
    )

    return oof_pred, full_result["model"], full_result["fill_values"]


def train_stacking(
    df: pd.DataFrame,
    features: list[str],
    cfg: dict,
    model_types: list[str],
    n_folds: int = 5,
    hardware: dict | None = None,
) -> dict[str, Any]:
    """Stacking 集成训练：时序 K-Fold OOF + Ridge 元学习器。

    流程：
    1. 数据切分 train/val/test
    2. 对每个基模型生成 OOF 预测（时序扩展窗口）
    3. 构建元特征矩阵 [oof_lgb, oof_xgb, oof_cbm]
    4. 训练 Ridge 元学习器
    5. 在 val/test 上评估集成效果
    """
    from sklearn.linear_model import Ridge

    train_df, val_df, test_df = _split_data(df, cfg)

    # Step 1: 生成各基模型 OOF 预测 + 全量基模型
    oof_preds: dict[str, pd.Series] = {}
    base_models: dict[str, Any] = {}
    base_fill_values: dict[str, dict] = {}
    base_results: dict[str, dict] = {}

    for mt in model_types:
        logger.info("=== Stacking: generating OOF for %s ===", mt)
        oof_pred, full_model, fill_values = _generate_oof_predictions(
            mt, train_df, features, cfg, n_folds=n_folds, hardware=hardware,
        )
        oof_preds[mt] = oof_pred
        base_models[mt] = full_model
        base_fill_values[mt] = fill_values

        # 评估全量基模型在 val/test 上的表现
        base_result = _train_single_model(
            mt, train_df, val_df, test_df, df, features, cfg, hardware=hardware,
        )
        base_results[mt] = base_result
        logger.info("Base model %s: val_icir=%.4f, test_icir=%.4f",
                     mt, base_result["val_m"]["rank_icir"], base_result["test_m"]["rank_icir"])

    # Step 2: 构建元特征矩阵（OOF 预测作为特征）
    meta_features_train = pd.DataFrame({
        f"oof_{mt}": oof_preds[mt] for mt in model_types
    })
    # 去除 NaN 行（某些 fold 未覆盖的样本）
    valid_mask = meta_features_train.notna().all(axis=1)
    meta_X_train = meta_features_train[valid_mask].values
    label_col = "label"
    meta_y_train = train_df.loc[valid_mask, label_col].values

    logger.info("Meta-learner training samples: %d (from %d train samples)",
                len(meta_y_train), len(train_df))

    # Step 3: 训练 Ridge 元学习器
    meta_model = Ridge(alpha=1.0, fit_intercept=True, random_state=42)
    meta_model.fit(meta_X_train, meta_y_train)
    logger.info("Ridge meta-learner coefficients: %s", dict(zip(
        [f"oof_{mt}" for mt in model_types], meta_model.coef_.round(4)
    )))

    # Step 4: 在 val/test 上评估集成
    def _predict_base(model_type: str, data_df: pd.DataFrame) -> np.ndarray:
        fv = base_fill_values[model_type]
        X = data_df[features].fillna(fv).values
        model = base_models[model_type]
        if model_type == "lightgbm":
            return model.predict(X)
        elif model_type == "xgboost":
            import xgboost as xgb
            return model.predict(xgb.DMatrix(X))
        elif model_type == "catboost":
            from catboost import Pool
            return model.predict(Pool(X))[0].flatten()
        else:
            return model.predict(X).flatten()

    # Val 集成预测
    val_base_preds = {mt: _predict_base(mt, val_df) for mt in model_types}
    meta_X_val = np.column_stack([val_base_preds[mt] for mt in model_types])
    val_ensemble_pred = meta_model.predict(meta_X_val)

    # Test 集成预测
    test_base_preds = {mt: _predict_base(mt, test_df) for mt in model_types}
    meta_X_test = np.column_stack([test_base_preds[mt] for mt in model_types])
    test_ensemble_pred = meta_model.predict(meta_X_test)

    # 评估集成指标
    def _calc_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        from scipy.stats import spearmanr
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        ic = float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 2 else 0.0
        rank_ic, _ = spearmanr(y_true, y_pred)
        rank_ic = float(rank_ic) if not np.isnan(rank_ic) else 0.0
        icir = ic / (np.std(y_pred) + 1e-9)
        rank_icir = rank_ic / (np.std(y_pred) + 1e-9)
        return {"rmse": rmse, "ic": ic, "rank_ic": rank_ic, "icir": icir, "rank_icir": rank_icir, "auc": 0.0}

    val_ensemble_m = _calc_metrics(val_df[label_col].values, val_ensemble_pred)
    test_ensemble_m = _calc_metrics(test_df[label_col].values, test_ensemble_pred)

    logger.info("=== Stacking Ensemble Results ===")
    logger.info("Val:  IC=%.4f, RankIC=%.4f, ICIR=%.4f", val_ensemble_m["ic"], val_ensemble_m["rank_ic"], val_ensemble_m["rank_icir"])
    logger.info("Test: IC=%.4f, RankIC=%.4f, ICIR=%.4f", test_ensemble_m["ic"], test_ensemble_m["rank_ic"], test_ensemble_m["rank_icir"])

    # 对比：最佳单模型 vs 集成
    best_single = max(base_results.items(), key=lambda x: abs(x[1]["val_m"]["rank_icir"]))
    logger.info("Best single (%s): val_icir=%.4f vs Stacking: val_icir=%.4f",
                best_single[0], best_single[1]["val_m"]["rank_icir"], val_ensemble_m["rank_icir"])

    # 构建全量预测 DataFrame（使用集成预测覆盖 val+test，train 用 OOF）
    pred_df = df[["trade_date", "symbol"]].copy()
    pred_df["pred"] = np.nan
    # Train 部分：使用 OOF 集成预测
    oof_ensemble = meta_model.predict(meta_features_train.values)
    pred_df.loc[valid_mask, "pred"] = oof_ensemble[valid_mask.values] if hasattr(valid_mask, 'values') else oof_ensemble
    # Val 部分
    val_idx = val_df.index
    pred_df.loc[val_idx, "pred"] = val_ensemble_pred
    # Test 部分
    test_idx = test_df.index
    pred_df.loc[test_idx, "pred"] = test_ensemble_pred

    # 保存 OOF 预测（诊断用）
    oof_df = pd.DataFrame({
        "trade_date": train_df["trade_date"],
        "symbol": train_df["symbol"],
        **{f"oof_{mt}": oof_preds[mt] for mt in model_types},
        "label": train_df[label_col],
    })
    oof_path = Path("/workspace/oof_predictions.parquet")
    oof_df.to_parquet(oof_path, engine="pyarrow", compression="zstd", index=False)
    logger.info("OOF predictions saved to %s", oof_path)

    # 保存元学习器
    import pickle
    meta_model_path = Path("/workspace/meta_model.pkl")
    with open(meta_model_path, "wb") as f:
        pickle.dump({
            "model": meta_model,
            "model_types": model_types,
            "n_folds": n_folds,
        }, f)
    logger.info("Meta-learner saved to %s", meta_model_path)

    # 生成对比报告
    comparison_rows = []
    for mt, res in base_results.items():
        vm = res["val_m"]
        comparison_rows.append({
            "model_type": mt,
            "val_ic": round(vm["ic"], 6),
            "val_rank_ic": round(vm["rank_ic"], 6),
            "val_rank_icir": round(vm["rank_icir"], 4),
            "val_rmse": round(vm["rmse"], 6),
            "val_auc": round(vm["auc"], 6),
            "test_ic": round(res["test_m"]["ic"], 6),
            "test_rank_ic": round(res["test_m"]["rank_ic"], 6),
            "test_rank_icir": round(res["test_m"]["rank_icir"], 4),
            "elapsed_seconds": round(res["elapsed"], 1),
        })
    comparison_rows.append({
        "model_type": "stacking_ensemble",
        "val_ic": round(val_ensemble_m["ic"], 6),
        "val_rank_ic": round(val_ensemble_m["rank_ic"], 6),
        "val_rank_icir": round(val_ensemble_m["rank_icir"], 4),
        "val_rmse": round(val_ensemble_m["rmse"], 6),
        "val_auc": round(val_ensemble_m["auc"], 6),
        "test_ic": round(test_ensemble_m["ic"], 6),
        "test_rank_ic": round(test_ensemble_m["rank_ic"], 6),
        "test_rank_icir": round(test_ensemble_m["rank_icir"], 4),
        "elapsed_seconds": 0.0,
    })
    comparison_rows.sort(key=lambda r: abs(r["val_rank_icir"]), reverse=True)

    best_type = comparison_rows[0]["model_type"]
    primary_type = best_type if best_type in model_types else model_types[0]

    return {
        "models": base_results,
        "base_models": base_models,
        "base_fill_values": base_fill_values,
        "meta_model": meta_model,
        "comparison": comparison_rows,
        "primary_model_type": primary_type,
        "model_types": model_types,
        "ensemble_method": "stacking",
        "val_ensemble_m": val_ensemble_m,
        "test_ensemble_m": test_ensemble_m,
        "pred_df": pred_df,
        "oof_preds": oof_preds,
        "split_frames": {"train": train_df.reset_index(drop=True), "valid": val_df.reset_index(drop=True), "test": test_df.reset_index(drop=True)},
    }


# ── 主入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    # 最早期诊断日志：在任何处理之前打印，确保 Batch 环境中一定能看到
    print(f"[BOOT] python={sys.version}", flush=True)
    print(f"[BOOT] argv={sys.argv}", flush=True)

    parser = argparse.ArgumentParser(description="QuantMind Training — YAML config driven")
    parser.add_argument("--config", required=False, help="Path to config.yaml")
    try:
        args, unknown_args = parser.parse_known_args()
    except SystemExit as exc:
        if int(getattr(exc, "code", 1) or 0) == 0:
            return 0
        # Batch 运行时偶发注入畸形参数（如缺失值的已知 flag）会触发 argparse 退出码 2。
        # 这里降级为环境变量驱动启动，避免任务在入口阶段直接失败。
        logger.warning(f"Argparse failed with argv={sys.argv}; fallback to env-driven args")
        args = argparse.Namespace(config=None)
        unknown_args = []
    if unknown_args:
        logger.warning(f"Ignoring unknown CLI args from runtime: {unknown_args}")

    # 本地挂载 config.yaml，CLI 参数作为可选覆盖
    cfg_path = Path(args.config) if args.config else Path("/tmp/config.yaml")

    run_id     = "unknown"
    result: dict = {}
    callback_url    = ""
    callback_secret = ""
    result_path = Path("/workspace/result.json")

    try:
        if not cfg_path.exists():
            raise RuntimeError(f"Config file not found: {cfg_path}")
        cfg = yaml.safe_load(cfg_path.read_text())

        run_id          = cfg.get("run_id", "unknown")
        job_name        = cfg.get("job_name", "unnamed")
        result_path     = Path(cfg.get("output", {}).get("result_path", "/workspace/result.json"))
        callback_url    = cfg.get("callback", {}).get("url", "")
        callback_secret = cfg.get("callback", {}).get("secret", "")

        logger.info("=== QuantMind Training Start ===")
        logger.info(f"run_id={run_id}  job={job_name}  config={cfg_path}")

        # 硬件环境检测
        hardware = detect_hardware()

        # 数据加载（特征列自动补齐基础6列）
        submitted_features = list(dict.fromkeys([str(item).strip() for item in (cfg["data"].get("features", []) or []) if str(item).strip()]))
        auto_appended_features = [feature for feature in TRAINING_BASE_FEATURES if feature not in submitted_features]
        features = list(dict.fromkeys(TRAINING_BASE_FEATURES + submitted_features))
        source_mode = str((cfg.get("data", {}) or {}).get("source_mode") or "LOCAL").strip().upper()
        local_data_dir = str((cfg.get("data", {}) or {}).get("local_dir") or "").strip() or None
        explain_cfg = _normalize_explain_cfg(cfg.get("explain") or {})
        context_cfg = cfg.get("context", {}) or {}
        market = str(context_cfg.get("market", "CN")).upper()

        df, valid_features = load_data(
            cfg["data"]["train_start"],
            cfg["data"]["train_end"],
            features,
            target_horizon_days=int((cfg.get("label", {}) or {}).get("target_horizon_days") or 1),
            cache_dir=cfg.get("cache", {}).get("dir"),
            valid_end=cfg.get("split", {}).get("valid", [None, None])[1],
            test_end=cfg.get("split", {}).get("test", [None, None])[1],
            source_mode=source_mode,
            local_dir=local_data_dir,
            market=market,
            industry_as_feature=bool(cfg.get("context", {}).get("industry_as_feature", False)),
        )

        # ── 因子筛选 ──
        factor_selection_cfg = cfg.get("factor_selection", {}) or {}
        factor_selection_method = str(factor_selection_cfg.get("method", "")).strip().lower()
        if factor_selection_method in ("ic_icir", "combined") or submitted_features and len(submitted_features) == 1 and submitted_features[0].lower().startswith("auto_top"):
            n_top = int(factor_selection_cfg.get("n_top", 60))
            ic_thresh = float(factor_selection_cfg.get("ic_threshold", 0.02))
            icir_thresh = float(factor_selection_cfg.get("icir_threshold", 0.3))
            corr_thresh = float(factor_selection_cfg.get("correlation_threshold", 0.85))
            logger.info("=== Auto Factor Selection: top-%d ===", n_top)
            valid_features, ic_results = select_top_factors(
                df, valid_features, label_col="label",
                n_top=n_top, ic_threshold=ic_thresh,
                icir_threshold=icir_thresh, correlation_threshold=corr_thresh,
            )
            logger.info("Selected %d features from auto selection", len(valid_features))

        train_t0 = time.time()

        # ── 判断单模型 vs 多模型 ──
        model_cfg = cfg.get("model", {})
        model_types_raw = model_cfg.get("types", None)
        is_multi_model = bool(model_types_raw and isinstance(model_types_raw, list) and len(model_types_raw) > 1)

        if is_multi_model:
            # ── 多模型训练路径 ──
            ensemble_method = str(model_cfg.get("ensemble", "none")).strip().lower()
            if ensemble_method == "stacking":
                multi_result = train_stacking(
                    df, valid_features, cfg,
                    model_types=[str(t).strip().lower() for t in model_types_raw],
                    n_folds=int(model_cfg.get("n_folds", 5)),
                    hardware=hardware,
                )
            else:
                multi_result = train_multi_models(df, valid_features, cfg, hardware=hardware)
            elapsed = float(time.time() - train_t0)
            primary_type = multi_result["primary_model_type"]
            is_stacking = multi_result.get("ensemble_method") == "stacking"

            # 保存各基模型
            workspace = Path("/workspace")
            saved_models: dict[str, str] = {}
            for mt, res in multi_result["models"].items():
                suffix_map = {"lightgbm": "_lgb", "xgboost": "_xgb", "catboost": "_cbm", "linear": "_lin"}
                suffix = suffix_map.get(mt, f"_{mt}")
                model_filename = _save_model(res["model"], mt, workspace.with_name(workspace.name) if False else workspace)
                ext = Path(model_filename).suffix
                new_name = f"model{suffix}{ext}"
                if model_filename != new_name:
                    (workspace / model_filename).rename(workspace / new_name)
                    model_filename = new_name
                saved_models[mt] = model_filename
                logger.info("Saved %s model: %s", mt, model_filename)

            # 获取主模型指标和预测
            primary_res = multi_result["models"][primary_type]
            if is_stacking:
                # Stacking: 使用集成预测和集成指标
                model = primary_res["model"]
                fill_values = primary_res["fill_values"]
                val_m = multi_result["val_ensemble_m"]
                test_m = multi_result["test_ensemble_m"]
                train_m = primary_res["train_m"]
                pred_df = multi_result["pred_df"]
                split_frames = primary_res["split_frames"]
                actual_model_type = "stacking"
                dl_metadata = primary_res.get("dl_metadata")
            else:
                model = primary_res["model"]
                fill_values = primary_res["fill_values"]
                train_m, val_m, test_m = primary_res["train_m"], primary_res["val_m"], primary_res["test_m"]
                pred_df = primary_res["pred_df"]
                split_frames = primary_res["split_frames"]
                actual_model_type = primary_type
                dl_metadata = primary_res.get("dl_metadata")

            best_iteration = getattr(model, "best_iteration", None)
            if best_iteration is None and hasattr(model, "get_best_iteration"):
                try:
                    best_iteration = model.get_best_iteration()
                except Exception:
                    best_iteration = None

            # 保存预测
            pred_path = Path("/workspace/pred.parquet")
            pred_df.to_parquet(pred_path, engine="pyarrow", compression="zstd", index=False)
            logger.info(f"Predictions saved to {pred_path}")

            pred_qlib = (
                pred_df[["trade_date", "symbol", "pred"]]
                .rename(columns={"trade_date": "datetime", "symbol": "instrument", "pred": "score"})
                .assign(datetime=lambda d: pd.to_datetime(d["datetime"]))
                .set_index(["datetime", "instrument"])
                .sort_index()
            )
            pred_pkl_path = Path("/workspace/pred.pkl")
            pred_qlib.to_pickle(pred_pkl_path)
            logger.info(f"Backtest-compatible pred.pkl saved ({len(pred_qlib):,} rows)")

            # 保存对比报告
            comparison_path = workspace / "model_comparison.json"
            comparison_path.write_text(json.dumps(multi_result["comparison"], ensure_ascii=False, indent=2, default=str))

            # SHAP（仅 LightGBM 基模型）
            shap_info: dict[str, Any] = {"enabled": False, "status": "disabled"}
            if "lightgbm" in multi_result["models"]:
                lgb_res = multi_result["models"]["lightgbm"]
                shap_summary_path = Path("/workspace/shap_summary.csv")
                shap_info = _compute_shap_summary(
                    model=lgb_res["model"],
                    split_frames=lgb_res["split_frames"],
                    features=valid_features,
                    fill_values=lgb_res["fill_values"],
                    explain_cfg=explain_cfg,
                    out_path=shap_summary_path,
                )
            else:
                logger.info("SHAP skipped: no LightGBM in multi-model run")

            # 保存各基模型独立预测（parquet）
            for mt, res in multi_result["models"].items():
                base_pred_path = workspace / f"pred_{mt}.parquet"
                res["pred_df"].to_parquet(base_pred_path, engine="pyarrow", compression="zstd", index=False)

            # 构造 metadata
            metadata = {
                "run_id": run_id, "job_name": job_name,
                "is_multi_model": True,
                "is_ensemble": is_stacking,
                "model_types": multi_result["model_types"],
                "primary_model_type": primary_type,
                "framework": _get_model_framework(primary_type),
                "model_type": actual_model_type,
                "model_file": saved_models.get(primary_type, ""),
                "saved_models": saved_models,
                "comparison": multi_result["comparison"],
                "ensemble_method": multi_result["ensemble_method"],
                "hardware": hardware,
                "feature_count": len(valid_features),
                "requested_feature_count": len(submitted_features),
                "requested_features": submitted_features,
                "auto_appended_feature_count": len(auto_appended_features),
                "auto_appended_features": auto_appended_features,
                "features": valid_features,
                "feature_columns": valid_features,
                "fill_values": fill_values,
                "train_start": cfg["data"]["train_start"],
                "train_end":   cfg["data"]["train_end"],
                "val_start":   (cfg.get("split", {}).get("valid") or [None, None])[0] or "",
                "val_end":     (cfg.get("split", {}).get("valid") or [None, None])[1] or "",
                "test_start":  (cfg.get("split", {}).get("test")  or [None, None])[0] or "",
                "test_end":    (cfg.get("split", {}).get("test")  or [None, None])[1] or "",
                "data_source": "parquet",
                "context": context_cfg,
                "best_iteration": best_iteration,
                "target_horizon_days": int((cfg.get("label", {}) or {}).get("target_horizon_days") or 1),
                "target_mode": str((cfg.get("label", {}) or {}).get("target_mode") or "return"),
                "label_formula": str((cfg.get("label", {}) or {}).get("label_formula") or ""),
                "effective_trade_date": str((cfg.get("label", {}) or {}).get("effective_trade_date") or ""),
                "training_window": str((cfg.get("label", {}) or {}).get("training_window") or ""),
                "metrics": {
                    "train_ic": train_m["ic"], "train_rank_ic": train_m["rank_ic"], "train_rank_icir": train_m["rank_icir"],
                    "val_ic": val_m["ic"], "val_rank_ic": val_m["rank_ic"], "val_rank_icir": val_m["rank_icir"],
                    "test_ic": test_m["ic"], "test_rank_ic": test_m["rank_ic"], "test_rank_icir": test_m["rank_icir"],
                },
                "pred_coverage_start": str(pred_df["trade_date"].min().date()) if not pred_df.empty else "",
                "pred_coverage_end": str(pred_df["trade_date"].max().date()) if not pred_df.empty else "",
                "pred_rows": int(len(pred_df)),
                "shap": shap_info,
                "generated_at": datetime.utcnow().isoformat(),
                "elapsed_seconds": elapsed,
            }
            if is_stacking:
                metadata["base_model_files"] = saved_models
                metadata["meta_model_file"] = "meta_model.pkl"
                metadata["n_folds"] = int(model_cfg.get("n_folds", 5))
                metadata["base_model_fill_values"] = multi_result.get("base_fill_values", {})
                metadata["fold_method"] = "expanding_window"
                metadata["meta_learner"] = "ridge"
            if dl_metadata:
                metadata.update(dl_metadata)

            metadata_bytes = json.dumps(_sanitize_nan_inf(metadata), ensure_ascii=False, indent=2).encode()
            Path("/workspace/metadata.json").write_bytes(metadata_bytes)
            logger.info("metadata.json saved locally")

            # 复制推理脚本模板
            template_path = Path("/app/backend/services/engine/inference/templates/inference_parquet.py")
            inference_dest = Path("/workspace/inference.py")
            if template_path.is_file():
                inference_dest.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
                logger.info("inference.py copied from unified template: %s", template_path)

            result = {
                "status": "completed",
                "run_id": run_id,
                "job_name": job_name,
                "metrics": {
                    "train": {"rmse": train_m["rmse"], "auc": train_m["auc"]},
                    "val": {"rmse": val_m["rmse"], "auc": val_m["auc"]},
                    "test": {"rmse": test_m["rmse"], "auc": test_m["auc"]},
                },
                "artifacts": [
                    {"name": saved_models.get(primary_type, "model.lgb"), "local": f"/workspace/{saved_models.get(primary_type, 'model.lgb')}"},
                    {"name": "pred.parquet",  "local": "/workspace/pred.parquet"},
                    {"name": "metadata.json", "local": "/workspace/metadata.json"},
                    {"name": "inference.py",  "local": "/workspace/inference.py"},
                    {"name": "config.yaml",   "local": "/workspace/config.yaml"},
                    {"name": "result.json",   "local": "/workspace/result.json"},
                    {"name": "model_comparison.json", "local": "/workspace/model_comparison.json"},
                ] + [
                    {"name": f"pred_{mt}.parquet", "local": f"/workspace/pred_{mt}.parquet"}
                    for mt in multi_result["model_types"]
                ] + [
                    {"name": fn, "local": f"/workspace/{fn}"}
                    for fn in saved_models.values() if fn != saved_models.get(primary_type)
                ],
                "summary": {
                    "status": "Stacking集成训练完成" if is_stacking else "多模型训练完成",
                    "message": f"{'Stacking集成' if is_stacking else '训练'}完成({len(multi_result['model_types'])}个模型)，最佳={primary_type}，val_icir={val_m['rank_icir']:.4f}",
                },
                "metadata": metadata,
                "error": "",
                "logs": f"val_rmse={val_m['rmse']:.6f}, val_auc={val_m['auc']:.6f}, best={primary_type}",
            }
            if is_stacking:
                result["artifacts"].extend([
                    {"name": "meta_model.pkl", "local": "/workspace/meta_model.pkl"},
                    {"name": "oof_predictions.parquet", "local": "/workspace/oof_predictions.parquet"},
                ])
            if shap_info.get("status") == "completed" and Path("/workspace/shap_summary.csv").exists():
                result["artifacts"].append({"name": "shap_summary.csv", "local": "/workspace/shap_summary.csv"})

        else:
            # ── 单模型训练路径（向后兼容） ──
            train_result = train_model(df, valid_features, cfg, hardware=hardware)
            # train_model 返回 8-tuple (树模型) 或 9-tuple (DL 模型，含 dl_metadata)
            if len(train_result) == 9:
                model, fill_values, train_m, val_m, test_m, pred_df, split_frames, actual_model_type, dl_metadata = train_result
            else:
                model, fill_values, train_m, val_m, test_m, pred_df, split_frames, actual_model_type = train_result
                dl_metadata = None
            elapsed = float(time.time() - train_t0)

            # 获取 best_iteration（不同框架方式不同）
            best_iteration = getattr(model, "best_iteration", None)
            if best_iteration is None and hasattr(model, "get_best_iteration"):
                try:
                    best_iteration = model.get_best_iteration()
                except Exception:
                    best_iteration = None
            logger.info("Training finished in %.2fs, best_iteration=%s, model_type=%s", elapsed, best_iteration, actual_model_type)

            # 保存模型（多框架）
            workspace = Path("/workspace")
            model_filename = _save_model(model, actual_model_type, workspace)
            logger.info(f"Model saved to {workspace / model_filename}")

            # 保存预测结果（parquet 压缩用于存档，比 pickle 小 ~10x）
            pred_path = Path("/workspace/pred.parquet")
            pred_df.to_parquet(pred_path, engine="pyarrow", compression="zstd", index=False)
            logger.info(f"Predictions saved to {pred_path} ({pred_path.stat().st_size/1024/1024:.1f} MB)")

            # 同时保存回测引擎兼容格式 pred.pkl
            # 回测引擎要求: MultiIndex(datetime, instrument) + 'score' 列
            pred_qlib = (
                pred_df[["trade_date", "symbol", "pred"]]
                .rename(columns={"trade_date": "datetime", "symbol": "instrument", "pred": "score"})
                .assign(datetime=lambda d: pd.to_datetime(d["datetime"]))
                .set_index(["datetime", "instrument"])
                .sort_index()
            )
            pred_pkl_path = Path("/workspace/pred.pkl")
            pred_qlib.to_pickle(pred_pkl_path)
            logger.info(f"Backtest-compatible pred.pkl saved ({pred_pkl_path.stat().st_size/1024/1024:.1f} MB, {len(pred_qlib):,} rows)")

            shap_summary_path = Path("/workspace/shap_summary.csv")
            # SHAP: pred_contrib 仅支持 LightGBM；其他框架暂跳过
            if actual_model_type != "lightgbm":
                explain_cfg_shap = {**explain_cfg, "enable_shap": False}
                logger.info("SHAP disabled: pred_contrib not supported for %s", actual_model_type)
            else:
                explain_cfg_shap = explain_cfg
            shap_info = _compute_shap_summary(
                model=model,
                split_frames=split_frames,
                features=valid_features,
                fill_values=fill_values,
                explain_cfg=explain_cfg_shap,
                out_path=shap_summary_path,
            )
            if shap_info.get("status") == "completed":
                logger.info(
                    "SHAP summary generated: split=%s rows=%s -> %s",
                    shap_info.get("split"),
                    shap_info.get("rows_used"),
                    shap_summary_path,
                )
            elif shap_info.get("status") == "disabled":
                logger.info("SHAP summary disabled by config")
            elif shap_info.get("status") == "skipped":
                logger.warning("SHAP summary skipped: %s", shap_info.get("error") or "unknown")
            else:
                logger.warning("SHAP summary failed: %s", shap_info.get("error") or "unknown")

            # 构造 metadata
            metadata = {
                "run_id": run_id, "job_name": job_name,
                "framework": _get_model_framework(actual_model_type),
                "model_type": actual_model_type,
                "model_file": model_filename,
                "hardware": hardware,
                "feature_count": len(valid_features),
                "requested_feature_count": len(submitted_features),
                "requested_features": submitted_features,
                "auto_appended_feature_count": len(auto_appended_features),
                "auto_appended_features": auto_appended_features,
                "features": valid_features,
                "feature_columns": valid_features,
                "fill_values": fill_values,
                "train_start": cfg["data"]["train_start"],
                "train_end":   cfg["data"]["train_end"],
                "val_start":   (cfg.get("split", {}).get("valid") or [None, None])[0] or "",
                "val_end":     (cfg.get("split", {}).get("valid") or [None, None])[1] or "",
                "test_start":  (cfg.get("split", {}).get("test")  or [None, None])[0] or "",
                "test_end":    (cfg.get("split", {}).get("test")  or [None, None])[1] or "",
                "data_source": "parquet",
                "context": context_cfg,
                "best_iteration": best_iteration,
                "target_horizon_days": int((cfg.get("label", {}) or {}).get("target_horizon_days") or 1),
                "target_mode": str((cfg.get("label", {}) or {}).get("target_mode") or "return"),
                "label_formula": str((cfg.get("label", {}) or {}).get("label_formula") or ""),
                "effective_trade_date": str((cfg.get("label", {}) or {}).get("effective_trade_date") or ""),
                "training_window": str((cfg.get("label", {}) or {}).get("training_window") or ""),
                "metrics": {
                    "train_ic": train_m["ic"], "train_rank_ic": train_m["rank_ic"], "train_rank_icir": train_m["rank_icir"],
                    "val_ic": val_m["ic"], "val_rank_ic": val_m["rank_ic"], "val_rank_icir": val_m["rank_icir"],
                    "test_ic": test_m["ic"], "test_rank_ic": test_m["rank_ic"], "test_rank_icir": test_m["rank_icir"],
                },
                "pred_coverage_start": str(pred_df["trade_date"].min().date()) if not pred_df.empty else "",
                "pred_coverage_end": str(pred_df["trade_date"].max().date()) if not pred_df.empty else "",
                "pred_rows": int(len(pred_df)),
                "shap": shap_info,
                "generated_at": datetime.utcnow().isoformat(),
                "elapsed_seconds": elapsed,
            }
            # DL 模型特有元数据 (model_class_name, model_params, input_spec 等)
            if dl_metadata:
                metadata.update(dl_metadata)

            metadata_bytes = json.dumps(_sanitize_nan_inf(metadata), ensure_ascii=False, indent=2).encode()
            Path("/workspace/metadata.json").write_bytes(metadata_bytes)
            logger.info("metadata.json saved locally")

            # 复制统一推理脚本模板（而非内联生成旧版脚本）
            template_path = Path("/app/backend/services/engine/inference/templates/inference_parquet.py")
            inference_dest = Path("/workspace/inference.py")
            if template_path.is_file():
                inference_dest.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
                logger.info("inference.py copied from unified template: %s", template_path)
            else:
                # 兜底：模板不存在时写入简化版（仅记录警告）
                logger.warning("统一推理模板不存在: %s，使用简化版", template_path)
                _INFERENCE_SCRIPT_FALLBACK = '''#!/usr/bin/env python3
"""
QuantMind Parquet 数据源推理脚本 (inference.py 模板)
=====================================================
适用于训练数据来自 feature_snapshots/*.parquet 的 LightGBM/XGBoost 模型。

平台注入环境变量：
    MODEL_DIR      模型目录绝对路径（含 metadata.json + model.lgb/model.xgb）
    TRADE_DATE     推理日期（同 --date 参数，互为备份）
    OUTPUT_FORMAT  固定值 json

调用方式（由 InferenceScriptRunner 自动调用）：
    python inference.py --date YYYY-MM-DD --output /path/to/out.json

输出格式（写入 --output 文件）：
    [{"symbol": "sh600519", "score": 0.82}, ...]

exit code：
    0  = 成功
    1  = 致命错误（模型/元数据损坏）
    2  = 该日期无可用数据（触发 alpha158 兜底）
"""
from __future__ import annotations
import argparse, json, logging, os, sys
from pathlib import Path
import pickle
import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:
    lgb = None
try:
    import xgboost as xgb
except ImportError:
    xgb = None
try:
    from catboost import CatBoost
except ImportError:
    CatBoost = None
try:
    import torch
except ImportError:
    torch = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("inference_parquet")

_DEFAULT_DATA_DIR = "/app/db/feature_snapshots"

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "-d", type=str, default=os.getenv("TRADE_DATE", ""))
    p.add_argument("--output", "-o", type=str, required=True)
    p.add_argument("--model-dir", type=str, default=os.getenv("MODEL_DIR", str(Path(__file__).parent)))
    p.add_argument("--data-dir", type=str, default=os.getenv("MODEL_TRAINING_DATA_DIR", _DEFAULT_DATA_DIR))
    return p.parse_args()

def load_metadata(model_dir):
    meta_path = Path(model_dir) / "metadata.json"
    if not meta_path.exists():
        logger.error("metadata.json 不存在: %s", meta_path); sys.exit(1)
    return json.loads(meta_path.read_text(encoding="utf-8"))

def load_model(model_dir, meta):
    model_file = meta.get("model_file", "")
    model_path = Path(model_dir) / model_file if model_file else None
    if not model_path or not model_path.exists():
        for ext in ("*.xgb", "*.lgb", "*.cbm", "*.pkl", "*.pth", "*.pt", "*.txt", "*.bin"):
            candidates = list(Path(model_dir).glob(ext))
            if candidates:
                model_path = candidates[0]; break
        else:
            logger.error("未找到模型文件: %s", model_dir); sys.exit(1)
    suffix = model_path.suffix.lower()
    logger.info("加载模型: %s (格式=%s)", model_path.name, suffix)
    if suffix == ".xgb":
        if xgb is None: logger.error("XGBoost 未安装"); sys.exit(1)
        booster = xgb.Booster(); booster.load_model(str(model_path)); return ("xgb", booster)
    elif suffix == ".cbm":
        if CatBoost is None: logger.error("CatBoost 未安装"); sys.exit(1)
        m = CatBoost(); m.load_model(str(model_path), format="cbm"); return ("catboost", m)
    elif suffix == ".pkl":
        with open(model_path, "rb") as f: m = pickle.load(f)
        return ("sklearn", m)
    elif suffix in (".pth", ".pt"):
        if torch is None: logger.error("PyTorch 未安装"); sys.exit(1)
        model_class_name = meta.get("model_class_name")
        _QLIB_MAP = {"GRU":("qlib.contrib.model.pytorch_gru_ts","GRU"),"LSTM":("qlib.contrib.model.pytorch_lstm_ts","LSTM"),"ALSTM":("qlib.contrib.model.pytorch_alstm_ts","ALSTM"),"Transformer":("qlib.contrib.model.pytorch_transformer_ts","Transformer"),"TCN":("qlib.contrib.model.pytorch_tcn_ts","TCN"),"TabNet":("qlib.contrib.model.pytorch_tabnet","TabNet")}
        if model_class_name and model_class_name in _QLIB_MAP:
            import importlib
            mod_path, cls_name = _QLIB_MAP[model_class_name]
            mod = importlib.import_module(mod_path); ModelCls = getattr(mod, cls_name)
            mp = dict(meta.get("model_params", {})); mp["GPU"] = -1
            model_obj = ModelCls(**mp)
            sd = torch.load(str(model_path), map_location="cpu", weights_only=True)
            inner = getattr(model_obj, "model", None)
            if inner is None:
                for a in ("gru_model","lstm_model","alstm_model","transformer_model","tcn_model","tabnet_model"):
                    inner = getattr(model_obj, a, None)
                    if inner is not None: break
            if inner is not None and sd is not None: inner.load_state_dict(sd); inner.eval()
            model_obj.fitted = True; return ("torch_qlib", model_obj)
        m = torch.load(str(model_path), map_location="cpu", weights_only=False)
        if hasattr(m, "eval"): m.eval()
        return ("torch", m)
    else:
        if lgb is None: logger.error("LightGBM 未安装"); sys.exit(1)
        return ("lgb", lgb.Booster(model_file=str(model_path)))

_MARKET_PARQUET = {"HK": "model_features_hk.parquet", "US": "model_features_us.parquet", "CRYPTO": "model_features_crypto.parquet"}

def load_date_data(trade_date, data_dir, meta):
    market = str((meta.get("context") or {}).get("market", "")).upper()
    if market in _MARKET_PARQUET:
        parquet_path = Path(data_dir) / _MARKET_PARQUET[market]
    else:
        year = int(trade_date[:4])
        parquet_path = Path(data_dir) / f"model_features_{year}.parquet"
    if not parquet_path.exists():
        logger.warning("parquet 文件不存在: %s", parquet_path); return None
    df = pd.read_parquet(parquet_path, engine="pyarrow")
    if "symbol" not in df.columns and "instrument" in df.columns:
        df = df.rename(columns={"instrument": "symbol"})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    day_df = df[df["trade_date"] == trade_date].copy()
    if len(day_df) == 0:
        logger.warning("日期 %s 无数据", trade_date); return None
    # 过滤不可交易（停牌、零成交、ST）
    if "close" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["close"], errors="coerce") > 0]
    if "volume" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["volume"], errors="coerce") > 0]
    if "is_st" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["is_st"], errors="coerce") != 1]
    if len(day_df) == 0:
        logger.warning("日期 %s 过滤后无数据", trade_date); return None
    logger.info("找到 %d 条记录，日期=%s", len(day_df), trade_date)
    return day_df

def preprocess(df, meta):
    feature_cols = meta.get("feature_columns") or meta.get("features", [])
    fill_values  = meta.get("fill_values", {})
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        logger.warning("缺少 %d 个特征列，填 0: %s", len(missing), missing[:8])
        for c in missing: df[c] = 0.0
    X_df = df[feature_cols].copy()
    for col, val in fill_values.items():
        if col in X_df.columns: X_df[col] = X_df[col].fillna(val)
    return X_df.fillna(0.0), df["symbol"].tolist()

def main():
    args = parse_args()
    trade_date = (args.date or "").strip()
    if not trade_date:
        logger.error("未指定推理日期"); sys.exit(1)
    model_dir, data_dir, out_path = Path(args.model_dir), Path(args.data_dir), Path(args.output)
    logger.info("=== parquet 推理脚本 === date=%s  model_dir=%s", trade_date, model_dir)
    meta  = load_metadata(model_dir)
    day_df = load_date_data(trade_date, data_dir, meta)
    if day_df is None:
        print(f"日期 {trade_date} 无数据，触发兜底", file=sys.stderr); sys.exit(2)
    model_type, model = load_model(model_dir, meta)
    X_df, symbols = preprocess(day_df, meta)
    if len(X_df) == 0:
        print(f"日期 {trade_date} 预处理后无有效行", file=sys.stderr); sys.exit(2)
    X_values = X_df.values.astype(np.float32)
    best_iter = meta.get("best_iteration")
    if model_type == "xgb":
        dmat = xgb.DMatrix(X_values, feature_names=list(X_df.columns))
        scores = model.predict(dmat, iteration_range=(0, best_iter) if best_iter else None)
    elif model_type == "catboost":
        scores = model.predict(X_values)
    elif model_type == "sklearn":
        scores = model.predict_proba(X_values)[:, 1] if hasattr(model, "predict_proba") else model.predict(X_values)
    elif model_type in ("torch_qlib", "torch"):
        inner = model
        if model_type == "torch_qlib":
            inner = getattr(model, "model", None)
            if inner is None:
                for a in ("gru_model","lstm_model","alstm_model","transformer_model","tcn_model","tabnet_model"):
                    inner = getattr(model, a, None)
                    if inner is not None: break
            if inner is None: logger.error("DL 内部模型未找到"); sys.exit(1)
        inner.eval()
        xt = torch.from_numpy(X_values)
        dev = getattr(model, "device", None) or getattr(inner, "device", None)
        if dev is not None: xt = xt.to(dev)
        with torch.no_grad(): pred = inner(xt).detach().cpu().numpy()
        scores = pred.flatten()
    else:
        scores = model.predict(X_values, num_iteration=best_iter)
    signals = sorted(
        [{"symbol": s, "score": float(v)} for s, v in zip(symbols, scores) if v == v],
        key=lambda x: x["score"], reverse=True
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(signals, ensure_ascii=False), encoding="utf-8")
    logger.info("已写入信号文件: %s  (%d 条)", out_path, len(signals))

if __name__ == "__main__":
    main()
'''
                inference_dest.write_text(_INFERENCE_SCRIPT_FALLBACK, encoding="utf-8")
                logger.info("inference.py fallback version written to model directory")

            result = {
                "status": "completed",
                "run_id": run_id,
                "job_name": job_name,
                "metrics": {
                    "train": {"rmse": train_m["rmse"], "auc": train_m["auc"]},
                    "val": {"rmse": val_m["rmse"], "auc": val_m["auc"]},
                    "test": {"rmse": test_m["rmse"], "auc": test_m["auc"]},
                },
                "artifacts": [
                    {"name": model_filename,  "local": f"/workspace/{model_filename}"},
                    {"name": "pred.parquet",  "local": "/workspace/pred.parquet"},
                    {"name": "metadata.json", "local": "/workspace/metadata.json"},
                    {"name": "inference.py",  "local": "/workspace/inference.py"},
                    {"name": "config.yaml",   "local": "/workspace/config.yaml"},
                    {"name": "result.json",   "local": "/workspace/result.json"},
                ],
                "summary": {
                    "status": "训练完成",
                    "message": f"训练完成({actual_model_type})，best_iteration={best_iteration}，产物已保存到本地模型目录",
                },
                "metadata": metadata,
                "error": "",
                "logs": f"val_rmse={val_m['rmse']:.6f}, val_auc={val_m['auc']:.6f}",
            }
            if shap_info.get("status") == "completed" and shap_summary_path.exists():
                result["artifacts"].append({"name": "shap_summary.csv", "local": "/workspace/shap_summary.csv"})

    except Exception as e:
        logger.exception(f"Training failed: {e}")
        result = {"status": "failed", "run_id": run_id, "error": str(e)}

    finally:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_clean = _sanitize_nan_inf(result)
        result_json = json.dumps(result_clean, ensure_ascii=False, indent=2)
        result_path.write_text(result_json)
        logger.info(f"result.json → {result_path}")

        if callback_url:
            try:
                resp = requests.post(
                    callback_url, json=result_clean,
                    headers={"X-Internal-Call-Secret": callback_secret},
                    timeout=15,
                )
                logger.info(f"Callback → HTTP {resp.status_code}")
            except Exception as cb_err:
                logger.warning(f"Callback failed (non-fatal): {cb_err}")

    logger.info("=== Training Complete ===")
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
