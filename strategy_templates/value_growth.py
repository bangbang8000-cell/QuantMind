"""
价值成长策略 (Value Growth)
[Native] 核心逻辑：在 TopK 选股基础上叠加 features_daily 的估值、规模和经营质量过滤。
"""
STRATEGY_CONFIG = {
    "class": "RedisRecordingStrategy",
    "kwargs": {
        "signal": "<PRED>",
        "topk": 30,
        "n_drop": 5,
        "f_total_mv_min": 1e9,
        "f_total_mv_max": 5e10,
        "f_float_mv_min": 5e8,
        "f_pe_ttm_min": 0.0,
        "f_pe_ttm_max": 25,
        "f_pb_max": 3.5,
        "f_ps_ttm_max": 6.0,
        "f_net_profit_ttm_min": 5e7,
        "f_revenue_ttm_min": 5e8,
    },
}
