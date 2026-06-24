"""风险评分模块入口。"""

from backend.services.api.risk_scoring.scorecard import (
    DEFAULT_WEIGHTS,
    DimensionScore,
    RiskScoreResult,
    compute_risk_score,
    compute_risk_scores_batch,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "DimensionScore",
    "RiskScoreResult",
    "compute_risk_score",
    "compute_risk_scores_batch",
]
