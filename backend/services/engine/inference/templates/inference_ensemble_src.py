#!/usr/bin/env python3
"""
QuantMind 融合模型推理脚本 (inference_ensemble_src.py)
=======================================================
用户从模型管理页多选已有模型创建融合模型后，该脚本负责对融合模型执行推理：
读取模型目录中的 ensemble_config.json，逐一加载源模型 → 预测 → 截面百分位
归一化 → 加权融合 → 共识度统计 → 输出标准信号 JSON。

支持的源模型类型：
  - LightGBM (.lgb / .txt)
  - XGBoost (.xgb)
  - CatBoost (.cbm)
  - sklearn (.pkl)
  - Stacking 融合 (is_ensemble + ensemble_method=stacking，加载基模型 + meta_model)

平台注入环境变量：
    MODEL_DIR      融合模型目录绝对路径（含 ensemble_config.json + metadata.json）
    TRADE_DATE     推理日期（同 --date 参数，互为备份）
    OUTPUT_FORMAT  固定值 json
    MODEL_TRAINING_DATA_DIR  特征 parquet 数据目录

调用方式（由 InferenceScriptRunner 自动调用）：
    python inference.py --date YYYY-MM-DD --output /path/to/out.json

输出格式（写入 --output 文件）：
    [{"symbol": "SH600519", "score": 0.15, "consensus": 3, "horizons": 3, "detail": {...}}, ...]

exit code：
    0  = 成功
    1  = 致命错误（模型/配置损坏）
    2  = 该日期无可用数据（触发 alpha158 兜底）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import sys
from pathlib import Path

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
    from catboost import CatBoost, Pool
except ImportError:
    CatBoost = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("inference_ensemble_src")

_DEFAULT_DATA_DIR = "/app/db/feature_snapshots"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def load_ensemble_config(model_dir: Path) -> dict:
    """从融合模型目录读取 ensemble_config.json。"""
    config_path = model_dir / "ensemble_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"ensemble_config.json 不存在: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict) or not config.get("models"):
        raise ValueError(f"ensemble_config.json 格式无效或 models 为空: {config_path}")
    return config


# ═══════════════════════════════════════════════════════════════════════════
# 2. 数据加载
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_parquet_path(data_dir: Path, trade_date: str) -> Path | None:
    """解析年度/市场 parquet 文件路径（A股市场）。"""
    year = int(trade_date[:4])
    p = data_dir / f"model_features_{year}.parquet"
    if p.exists():
        return p
    p = data_dir / "model_features.parquet"
    return p if p.exists() else None


def load_day_data(trade_date: str, data_dir: Path) -> pd.DataFrame | None:
    """加载指定交易日的全市场特征数据。"""
    parquet_path = _resolve_parquet_path(data_dir, trade_date)
    if parquet_path is None:
        logger.warning("找不到 parquet 文件 (data_dir=%s)", data_dir)
        return None

    df = pd.read_parquet(parquet_path, engine="pyarrow")
    if "symbol" not in df.columns and "instrument" in df.columns:
        df = df.rename(columns={"instrument": "symbol"})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    day_df = df[df["trade_date"] == trade_date].copy()

    if len(day_df) == 0:
        logger.warning("日期 %s 无数据", trade_date)
        return None

    # 过滤不可交易：价格/成交量为零或负
    if "close" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["close"], errors="coerce") > 0]
    if "volume" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["volume"], errors="coerce") > 0]

    if len(day_df) == 0:
        logger.warning("日期 %s 过滤后无可交易数据", trade_date)
        return None

    return day_df


# ═══════════════════════════════════════════════════════════════════════════
# 3. 源模型加载（支持单模型 + stacking 融合）
# ═══════════════════════════════════════════════════════════════════════════

def _load_base_model(model_path: Path, model_type: str):
    """按类型加载单个基模型权重。"""
    suffix = model_path.suffix.lower()
    if model_type == "lightgbm" or suffix in (".lgb", ".txt"):
        if lgb is None:
            raise ImportError("lightgbm 未安装")
        return lgb.Booster(model_file=str(model_path))
    if model_type == "xgboost" or suffix == ".xgb":
        if xgb is None:
            raise ImportError("xgboost 未安装")
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        return booster
    if model_type == "catboost" or suffix == ".cbm":
        if CatBoost is None:
            raise ImportError("catboost 未安装")
        cb = CatBoost()
        cb.load_model(str(model_path), format="cbm")
        return cb
    # .pkl → sklearn / pickle 模型
    with open(model_path, "rb") as f:
        return pickle.load(f)


def load_source_model(model_dir: Path) -> tuple[object, dict]:
    """加载源模型。返回 (model, meta)。

    对 stacking 融合源模型，加载全部基模型 + meta_model，包装为 StackingEnsemble。
    """
    meta_path = model_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json 不存在: {meta_path}")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    is_stacking = bool(meta.get("is_ensemble")) and str(meta.get("ensemble_method", "")).lower() == "stacking"
    if is_stacking:
        model = _load_stacking(model_dir, meta)
        return model, meta

    model_file = meta.get("model_file", "")
    model_path = model_dir / model_file if model_file else None
    if not model_path or not model_path.exists():
        for ext in ("*.xgb", "*.lgb", "*.cbm", "*.pkl", "*.txt"):
            candidates = list(model_dir.glob(ext))
            if candidates:
                model_path = candidates[0]
                break
    if not model_path or not model_path.exists():
        raise FileNotFoundError(f"未找到模型文件: {model_dir}")

    model_type = str(meta.get("model_type", "")).lower()
    return _load_base_model(model_path, model_type), meta


class _StackingEnsemble:
    """Stacking 源模型推理包装：基模型预测 → 元学习器融合。"""

    def __init__(self, base_models: dict, meta_model, model_types: list[str],
                 fill_values: dict, features: list[str]):
        self.base_models = base_models
        self.meta_model = meta_model
        self.model_types = model_types
        self.fill_values = fill_values
        self.features = features

    def predict(self, X: np.ndarray) -> np.ndarray:
        base_preds = []
        for mt in self.model_types:
            model = self.base_models.get(mt)
            if model is None:
                continue
            # 基模型训练时使用与融合模型相同的特征矩阵（stacking 用统一特征），
            # 这里直接对已填充的 X 预测
            if mt == "lightgbm":
                pred = model.predict(X)
            elif mt == "xgboost":
                # XGBoost Booster 需要特征名匹配训练时的顺序
                names = model.feature_names
                dmat = xgb.DMatrix(X, feature_names=names) if names else xgb.DMatrix(X)
                pred = model.predict(dmat)
            elif mt == "catboost":
                pred = np.asarray(model.predict(Pool(X))).flatten()
            else:
                pred = model.predict(X).flatten()
            base_preds.append(pred)
        if not base_preds:
            raise ValueError("Stacking 基模型为空")
        meta_X = np.column_stack(base_preds)
        return self.meta_model.predict(meta_X)


def _load_stacking(model_dir: Path, meta: dict) -> _StackingEnsemble:
    """加载 stacking 融合源模型的全部基模型 + meta_model。"""
    model_types = meta.get("model_types", [])
    saved_models = meta.get("saved_models", {})
    base_fv = meta.get("base_model_fill_values", {})
    global_fv = meta.get("fill_values", {})
    features = meta.get("feature_columns") or meta.get("features", [])

    base_models = {}
    for mt in model_types:
        model_file = saved_models.get(mt, "")
        if not model_file:
            continue
        model_path = model_dir / model_file
        if not model_path.exists():
            logger.warning("Stacking 基模型缺失: %s", model_path)
            continue
        base_models[mt] = _load_base_model(model_path, mt)

    meta_model_path = model_dir / meta.get("meta_model_file", "meta_model.pkl")
    if not meta_model_path.exists():
        raise FileNotFoundError(f"Stacking meta_model 不存在: {meta_model_path}")
    with open(meta_model_path, "rb") as f:
        meta_data = pickle.load(f)
    meta_model = meta_data["model"] if isinstance(meta_data, dict) else meta_data

    fill_values = {}
    for mt in model_types:
        per_model_fv = base_fv.get(mt, {}) if isinstance(base_fv, dict) else {}
        fill_values[mt] = per_model_fv if per_model_fv else (global_fv if isinstance(global_fv, dict) else {})

    logger.info("加载 Stacking 融合源模型: %d 个基模型 + 元学习器", len(base_models))
    return _StackingEnsemble(
        base_models=base_models,
        meta_model=meta_model,
        model_types=model_types,
        fill_values=fill_values,
        features=features,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 单源模型预测
# ═══════════════════════════════════════════════════════════════════════════

def predict_with_model(model, meta: dict, day_df: pd.DataFrame) -> dict[str, float]:
    """对单个源模型执行推理，返回 {symbol: raw_score}。

    meta 决定特征列与填充值；day_df 为当日全市场数据副本。
    """
    feature_cols = meta.get("feature_columns") or meta.get("features", [])
    fill_values = meta.get("fill_values", {})
    best_iter = meta.get("best_iteration")

    # features_daily.return_Nd 是未来 N 日收益，不能作为特征喂给模型（标签泄漏）
    _leaky = [c for c in ("return_1d", "return_3d", "return_5d",
                          "return_10d", "return_20d", "return_60d")
              if c in day_df.columns]
    if _leaky:
        day_df = day_df.drop(columns=_leaky, errors="ignore")

    # 缺失列补 0
    missing = [c for c in feature_cols if c not in day_df.columns]
    if missing:
        logger.warning("源模型缺 %d 个特征列，填 0: %s", len(missing), missing[:8])
        for c in missing:
            day_df[c] = 0.0

    X = day_df[feature_cols].copy()
    for col, val in fill_values.items():
        if col in X.columns:
            X[col] = X[col].fillna(val)
    X = X.fillna(0.0)
    X_values = X.values.astype(np.float32)
    symbols = day_df["symbol"].tolist()

    is_stacking = isinstance(model, _StackingEnsemble)
    if is_stacking:
        scores = model.predict(X_values)
    elif hasattr(model, "get_dump") or str(type(model).__name__) == "Booster":
        scores = model.predict(X_values, num_iteration=best_iter)
    else:
        # sklearn / pickle 模型
        if hasattr(model, "predict_proba"):
            scores = model.predict_proba(X_values)[:, 1]
        else:
            scores = model.predict(X_values)

    scores = np.asarray(scores).flatten()

    # 方向纠正：训练时 IC<0 的模型分数已翻转
    if meta.get("score_direction") == "reversed":
        scores = -scores

    result = {}
    for sym, s in zip(symbols, scores):
        f = float(s)
        if f == f:  # 过滤 NaN
            result[sym] = f
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5. 融合逻辑
# ═══════════════════════════════════════════════════════════════════════════

def fuse_scores(
    all_scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> list[dict]:
    """多源模型分数融合（按源模型 id）。

    融合策略：
    1. 每个源模型的分数做截面排名百分位（0~1，0.5=中位数）
    2. 加权平均得融合百分位
    3. 转对称分数 (pct - 0.5) * 2 → [-1, 1]
    4. 共识度 = 与多数方向一致的源模型数

    Returns:
        [{"symbol": "...", "score": 0.15, "consensus": 3, "horizons": 3, "detail": {...}}, ...]
    """
    all_symbols = set()
    for scores in all_scores.values():
        all_symbols.update(scores.keys())

    # 预计算每个源模型的排名百分位
    rank_pcts: dict[str, dict[str, float]] = {}
    for mid, scores in all_scores.items():
        if not scores:
            continue
        sorted_syms = sorted(scores.keys(), key=lambda s: scores[s])
        n = len(sorted_syms)
        rank_pcts[mid] = {sym: (i + 1) / n for i, sym in enumerate(sorted_syms)}

    if not rank_pcts:
        return []

    results = []
    for sym in all_symbols:
        raw_scores = {}
        pct_scores = {}

        for mid, pcts in rank_pcts.items():
            if sym in pcts:
                raw_scores[mid] = all_scores[mid][sym]
                pct_scores[mid] = pcts[sym]

        if not pct_scores:
            continue

        total_weight = sum(weights.get(m, 0.1) for m in pct_scores)
        fused_pct = sum(pct_scores[m] * weights.get(m, 0.1) for m in pct_scores) / total_weight
        fused = (fused_pct - 0.5) * 2

        directions = {m: 1 if p > 0.5 else -1 for m, p in pct_scores.items()}
        majority_dir = 1 if sum(directions.values()) > 0 else -1
        consensus = sum(1 for d in directions.values() if d == majority_dir)

        results.append({
            "symbol": sym,
            "score": float(fused),
            "consensus": int(consensus),
            "horizons": len(pct_scores),
            "detail": {
                m: {
                    "raw": round(raw_scores.get(m, 0), 6),
                    "pct": round(pct_scores.get(m, 0.5), 4),
                }
                for m in pct_scores
            },
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 6. 主流程
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="融合模型推理")
    p.add_argument("--date", "-d", type=str, default=os.getenv("TRADE_DATE", ""))
    p.add_argument("--output", "-o", type=str, required=True)
    p.add_argument("--model-dir", type=str, default=os.getenv("MODEL_DIR", ""))
    p.add_argument("--data-dir", type=str, default=os.getenv("MODEL_TRAINING_DATA_DIR", _DEFAULT_DATA_DIR))
    return p.parse_args()


def main():
    args = parse_args()

    trade_date = (args.date or "").strip()
    if not trade_date:
        logger.error("未指定推理日期（--date 或 TRADE_DATE 环境变量）")
        sys.exit(1)

    model_dir = Path(args.model_dir)
    data_dir = Path(args.data_dir)
    out_path = Path(args.output)

    logger.info("=== 融合模型推理 ===")
    logger.info("  date     : %s", trade_date)
    logger.info("  model_dir: %s", model_dir)
    logger.info("  data_dir : %s", data_dir)

    # 1. 加载融合配置
    config = load_ensemble_config(model_dir)
    model_configs = config.get("models", [])
    logger.info("融合 %d 个源模型: %s", len(model_configs),
                [m.get("model_id", "?") for m in model_configs])

    # 2. 加载当日数据
    day_df = load_day_data(trade_date, data_dir)
    if day_df is None:
        msg = f"日期 {trade_date} 无数据"
        logger.warning(msg)
        print(msg, file=sys.stderr)
        sys.exit(2)

    # 3. 逐源模型推理（缺失模型优雅降级）
    all_scores: dict[str, dict[str, float]] = {}
    weights: dict[str, float] = {}

    for mc in model_configs:
        mid = str(mc.get("model_id") or mc.get("name") or "?")
        m_dir = Path(mc.get("model_dir") or "")
        w = float(mc.get("weight", 0.1))

        if not m_dir.exists():
            logger.warning("源模型目录缺失，跳过 %s: %s", mid, m_dir)
            continue

        try:
            model, meta = load_source_model(m_dir)
            scores = predict_with_model(model, meta, day_df.copy())
            if scores:
                all_scores[mid] = scores
                weights[mid] = w
                logger.info("源模型 %s: %d 条信号, weight=%.3f", mid, len(scores), w)
            else:
                logger.warning("源模型 %s 预测为空，跳过", mid)
        except Exception as e:
            logger.warning("源模型 %s 推理失败: %s", mid, e)

    if not all_scores:
        logger.error("所有源模型推理均失败")
        sys.exit(1)

    # 4. 融合
    signals = fuse_scores(all_scores, weights)
    signals.sort(key=lambda x: x["score"], reverse=True)
    logger.info("融合完成: %d 条信号", len(signals))

    # 5. 输出
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False)

    logger.info("已写入融合信号: %s (%d 条)", out_path, len(signals))


if __name__ == "__main__":
    main()
