from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PredictionArtifactError(RuntimeError):
    """Raised when inference output cannot be converted to backtest artifact."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_pred_pkl_from_inference(
    *,
    run_id: str,
    user_id: str,
    tenant_id: str,
    inference_result: dict[str, Any],
    base_dir: Path,
    default_datetime: datetime | None = None,
) -> Path:
    """Convert inference result into qlib-compatible pred.pkl file."""
    predictions = _as_list(inference_result.get("predictions"))
    symbols = _as_list(inference_result.get("symbols"))

    if not predictions:
        raise PredictionArtifactError("inference result missing predictions")

    if symbols and len(symbols) != len(predictions):
        raise PredictionArtifactError(f"symbols/predictions length mismatch: {len(symbols)} != {len(predictions)}")

    if not symbols:
        symbols = [f"UNKNOWN_{idx:04d}" for idx in range(len(predictions))]

    dt = default_datetime or datetime.now()
    dt_index = pd.Timestamp(dt.strftime("%Y-%m-%d"))

    tuples: list[tuple[pd.Timestamp, str]] = []
    scores: list[float] = []
    for symbol, score in zip(symbols, predictions):
        try:
            score_val = float(score)
        except Exception as exc:  # pragma: no cover
            raise PredictionArtifactError(f"invalid prediction value {score!r}: {exc}")
        tuples.append((dt_index, str(symbol)))
        scores.append(score_val)

    df = pd.DataFrame(
        {"score": scores},
        index=pd.MultiIndex.from_tuples(tuples, names=["datetime", "instrument"]),
    )

    output_dir = base_dir / tenant_id / user_id / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "pred.pkl"
    df.to_pickle(output_path)
    return output_path


def generate_ensemble_pred(
    *,
    model_dir: Path,
    output_path: Path | None = None,
) -> Path:
    """为融合模型（ensemble_config.json）生成覆盖历史区间的 pred.pkl。

    读取融合模型的 ensemble_config.json，加载各子模型的 pred.pkl，
    按 (datetime, instrument) 对齐后做「截面排名百分位加权融合」，
    输出与单模型 pred.pkl 同构的信号文件，供 AI-IDE 回测等场景直接使用。

    权重来源：ensemble_config.json 中每个子模型的 weight 字段；
    weight_strategy=recent_ic 时，权重已在生成配置时归一化。

    Raises:
        PredictionArtifactError: 配置缺失 / 子模型 pred 缺失 / 无有效信号。
    """
    if not model_dir.is_dir():
        raise PredictionArtifactError(f"融合模型目录不存在: {model_dir}")

    config_path = model_dir / "ensemble_config.json"
    if not config_path.exists():
        raise PredictionArtifactError(f"缺少 ensemble_config.json: {config_path}")

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PredictionArtifactError(f"ensemble_config.json 解析失败: {exc}") from exc

    models = config.get("models") or []
    if not models:
        raise PredictionArtifactError(f"ensemble_config.json models 为空: {config_path}")

    child_preds: list[pd.DataFrame] = []
    weights: list[float] = []
    for mc in models:
        m_dir = Path(str(mc.get("model_dir") or ""))
        pred_path = m_dir / "pred.pkl"
        if not pred_path.exists():
            pred_parquet = m_dir / "pred.parquet"
            if not pred_parquet.exists():
                logger.warning("融合子模型缺少 pred 文件，跳过: %s", m_dir)
                continue
            pred_path = pred_parquet
        try:
            pred = pd.read_pickle(pred_path)
            if isinstance(pred, pd.Series):
                pred = pred.to_frame("score")
            if "score" not in pred.columns:
                pred = pred.rename(columns={pred.columns[-1]: "score"})
            if not (
                hasattr(pred, "index")
                and "datetime" in pred.index.names
                and "instrument" in pred.index.names
            ):
                logger.warning("融合子模型 pred 索引格式异常，跳过: %s", m_dir)
                continue
            child_preds.append(pred[["score"]])
            weights.append(float(mc.get("weight") or 0.0))
        except Exception as exc:
            logger.warning("加载融合子模型 pred 失败，跳过: %s (%s)", m_dir, exc)

    if not child_preds:
        raise PredictionArtifactError(f"融合模型的所有子模型 pred 均缺失: {model_dir}")

    # 权重归一化（若全 0，则均分）
    w = np.array(weights, dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(w)) / len(w)
    else:
        w = w / w.sum()

    # 按 (datetime, instrument) 对齐取并集索引
    all_index = child_preds[0].index
    for p in child_preds[1:]:
        all_index = all_index.union(p.index)

    fused = pd.DataFrame(index=all_index)
    for idx, (pred, weight) in enumerate(zip(child_preds, w)):
        # 每日截面排名百分位（0~1，越高越好）
        score_col = pred["score"].reindex(all_index)
        pct = score_col.groupby(level="datetime").rank(pct=True, ascending=True)
        fused[f"_pct_{idx}"] = pct * weight

    score_cols = list(fused.columns)
    fused["score"] = fused[score_cols].sum(axis=1)
    fused = fused[["score"]].sort_index()

    if fused.empty:
        raise PredictionArtifactError(f"融合 pred 为空: {model_dir}")

    out_path = output_path or (model_dir / "pred.pkl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fused.to_pickle(out_path)
    logger.info(
        "融合模型 pred 已生成: %s (%d 行, %d 个交易日, 子模型=%d)",
        out_path,
        len(fused),
        fused.index.get_level_values("datetime").nunique(),
        len(child_preds),
    )
    return out_path
