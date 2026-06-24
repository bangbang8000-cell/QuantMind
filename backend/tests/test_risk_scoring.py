"""风险评分卡核心算分函数的单元测试（v2）。

测试目标：6 维度子分函数 + veto（v2 新增巨幅+巨量条款）+ 聚合公式。
不依赖 DB —— 直接构造 row 字典调 _compute_from_row。

参考设计文档：docs/risk_scorecard_design_v2.md
"""

from __future__ import annotations

import pytest

from backend.services.api.risk_scoring.scorecard import (
    DEFAULT_WEIGHTS,
    _bucket,
    _compute_from_row,
    _score_fundamental,
    _score_liquidity,
    _score_overheat,
    _score_status,
    _score_trend,
    _score_volatility,
    _veto,
)


# 一个"健康股"基线行
_HEALTHY = {
    "symbol": "600519.SH",
    "trade_date": "2026-06-22",
    "stock_name": "贵州茅台",
    "industry": "白酒",
    "close": 295.0,
    "open": 290.0,
    "high": 298.0,
    "low": 286.0,
    "volume": 5_000_000,
    "amount": 1.5e9,
    "amount_20d_avg": 1.5e9,
    "amount_5d_avg": 1.5e9,
    "amount_ratio_5d": 1.0,
    "pct_change": 2.0,
    "turnover_rate": 0.46,
    "vol_atr_14": 6.6,
    "vol_std_5": 0.018,
    "vol_std_20": 0.020,
    "float_mv": 3.7e12,
    "total_mv": 3.7e12,
    "ma5": 290.0, "ma10": 285.0, "ma20": 280.0, "ma60": 270.0,
    "macd_hist": 0.5,
    "pb": 8.5, "pe_ttm": 22.0, "roe": 0.31,
    "is_st": 0, "listed_days": 8000, "consecutive_limit_up_days": 0,
    "rsi_14": 55.0, "kdj_k": 50.0,
    "return_5d": 0.03, "return_20d": 0.05,
}


def _row(**overrides):
    out = dict(_HEALTHY)
    out.update(overrides)
    return out


# ── 一票否决 ──────────────────────────────────────────────────────────────
def test_veto_st():
    triggered, reasons = _veto(_row(is_st=1))
    assert triggered is True
    assert any("ST" in r for r in reasons)


def test_veto_newly_listed():
    triggered, reasons = _veto(_row(listed_days=30))
    assert triggered is True
    assert any("次新" in r for r in reasons)


def test_veto_halted():
    triggered, _ = _veto(_row(volume=0))
    assert triggered is True


def test_veto_limit_up_locked():
    triggered, _ = _veto(_row(pct_change=9.9, turnover_rate=0.5))
    assert triggered is True


def test_veto_limit_up_open():
    triggered, _ = _veto(_row(pct_change=9.9, turnover_rate=8.0))
    assert triggered is False


def test_veto_healthy_passes():
    triggered, reasons = _veto(_HEALTHY)
    assert triggered is False
    assert reasons == []


# v2 新增：巨幅+巨量
def test_veto_huge_swing_huge_volume_down():
    """大跌 + 巨量 → 黑天鹅 veto"""
    triggered, reasons = _veto(_row(pct_change=-9.0, amount_ratio_5d=2.5))
    assert triggered is True
    assert any("黑天鹅" in r for r in reasons)


def test_veto_huge_swing_huge_volume_up():
    """大涨 + 巨量也 veto（避免追到顶）"""
    triggered, _ = _veto(_row(pct_change=8.5, amount_ratio_5d=3.0, turnover_rate=15.0))
    assert triggered is True


def test_veto_huge_swing_normal_volume_no_veto():
    """大涨但量正常（< 2x）→ 不 veto，让其它维度判断"""
    triggered, _ = _veto(_row(pct_change=8.5, amount_ratio_5d=1.5, turnover_rate=8.0))
    assert triggered is False


def test_veto_normal_swing_huge_volume_no_veto():
    """温和波动 + 巨量 → 不 veto（健康放量）"""
    triggered, _ = _veto(_row(pct_change=3.0, amount_ratio_5d=2.5))
    assert triggered is False


# ── 流动性 ────────────────────────────────────────────────────────────────
def test_liquidity_dead_volume():
    s = _score_liquidity(_row(amount_20d_avg=5e6))
    assert s.score >= 100
    assert any("1000 万" in r for r in s.reasons)


def test_liquidity_small_cap():
    s = _score_liquidity(_row(amount_20d_avg=4e7, float_mv=1.5e9))
    assert 45 <= s.score <= 60


def test_liquidity_speculative_high_turnover():
    s = _score_liquidity(_row(amount_20d_avg=2e8, float_mv=1e10, turnover_rate=20.0))
    assert s.score == 15


def test_liquidity_healthy_zero():
    s = _score_liquidity(_HEALTHY)
    assert s.score == 0


# ── 波动率+量能（v2 改造） ────────────────────────────────────────────────
def test_volatility_extreme_atr():
    s = _score_volatility(_row(close=100.0, vol_atr_14=25.0, pct_change=8.0))
    assert s.score >= 95


def test_volatility_high():
    s = _score_volatility(_row(close=100.0, vol_atr_14=7.0, pct_change=2.0))
    # ATR 7% (>6) = 55; 无异动; 量比 = 1 不触发量价; vs5/vs20 = 0.9 不扩张
    assert s.score == 55


def test_volatility_healthy_baseline():
    s = _score_volatility(_HEALTHY)
    # ATR 2.24% → 10; 其它都 0
    assert s.score == 10


def test_volatility_missing_atr():
    s = _score_volatility(_row(vol_atr_14=None))
    assert any("缺少" in r for r in s.reasons)


# v2 新增子项 C：波动率扩张
def test_volatility_strong_expansion():
    s = _score_volatility(_row(vol_std_5=0.05, vol_std_20=0.02))   # 2.5x
    # ATR 2.24% → 10; 扩张 2.5 > 1.8 → +30
    assert s.score == 40
    assert any("扩张" in r for r in s.reasons)


def test_volatility_moderate_expansion():
    s = _score_volatility(_row(vol_std_5=0.030, vol_std_20=0.020))   # 1.5x
    # 10 + 15 = 25
    assert s.score == 25


# v2 新增子项 D：量价配合 4 矩阵
def test_volatility_volume_dump_distribution():
    """放量下跌 → +50"""
    s = _score_volatility(_row(pct_change=-5.0, amount_ratio_5d=2.0))
    # ATR 2.24 → 10; 放量下跌 → +50; 总 60
    assert s.score == 60
    assert any("放量下跌" in r for r in s.reasons)


def test_volatility_weak_rebound():
    """缩量上涨 → +40"""
    s = _score_volatility(_row(pct_change=3.0, amount_ratio_5d=0.6))
    # 10 + 40 = 50
    assert s.score == 50
    assert any("缩量上涨" in r for r in s.reasons)


def test_volatility_quiet_decline():
    """缩量下跌 → +20"""
    s = _score_volatility(_row(pct_change=-3.0, amount_ratio_5d=0.6))
    assert s.score == 30
    assert any("缩量下跌" in r for r in s.reasons)


def test_volatility_healthy_rally_minus():
    """放量上涨 → -10"""
    s = _score_volatility(_row(pct_change=3.0, amount_ratio_5d=1.5))
    # 10 - 10 = 0 (clip)
    assert s.score == 0
    assert any("健康行情" in r for r in s.reasons)


def test_volatility_combo_extreme():
    """ATR 高 + 异动 + 扩张 + 放量下跌：所有子项命中"""
    s = _score_volatility(_row(
        close=100, vol_atr_14=9.0, pct_change=-8.0,
        vol_std_5=0.05, vol_std_20=0.02,
        amount_ratio_5d=2.0,
    ))
    # 80 (ATR>8) + 15 (异动) + 30 (扩张) + 50 (放量下跌) = 175 → clip 100
    assert s.score == 100


# ── 趋势 ──────────────────────────────────────────────────────────────────
def test_trend_full_bearish():
    s = _score_trend(_row(
        close=10.0, ma5=11, ma10=12, ma20=13, ma60=14, macd_hist=-0.5,
    ))
    assert s.score == 100


def test_trend_only_below_ma60():
    s = _score_trend(_row(
        close=14.0, ma5=15, ma10=15, ma20=13, ma60=16, macd_hist=0.5,
    ))
    assert s.score == 40


def test_trend_healthy_zero():
    s = _score_trend(_HEALTHY)
    assert s.score == 0


# ── 过热（v2 新增维度） ──────────────────────────────────────────────────
def test_overheat_short_term_surge():
    """5 日累计涨 30% → +60"""
    s = _score_overheat(_row(return_5d=0.30, return_20d=0.10))
    assert s.score == 60
    assert any("短期暴涨" in r for r in s.reasons)


def test_overheat_moderate_surge():
    """5 日涨 18% → +30"""
    s = _score_overheat(_row(return_5d=0.18))
    assert s.score == 30


def test_overheat_monthly_doubled():
    """20 日涨 60% → +20"""
    s = _score_overheat(_row(return_5d=0.05, return_20d=0.60))
    assert s.score == 20


def test_overheat_strong_rsi_with_surge():
    """RSI > 80 + 5 日涨 20% → +30 (短期强涨) + +50 (强超买共振) = 80"""
    s = _score_overheat(_row(return_5d=0.20, rsi_14=85.0))
    assert s.score == 80


def test_overheat_rsi_without_surge_no_score():
    """RSI 85 但 5 日只涨 3% → 不打分（避免误杀强势股）"""
    s = _score_overheat(_row(return_5d=0.03, rsi_14=85.0))
    assert s.score == 0


def test_overheat_rsi_kdj_resonance():
    """RSI 78 + KDJ 90 共振 → +25"""
    s = _score_overheat(_row(return_5d=0.05, rsi_14=78.0, kdj_k=90.0))
    assert s.score == 25


def test_overheat_clip_extreme_return():
    """return_5d 异常值（如指数 1039）应被 clip 到 5.0 不爆炸"""
    s = _score_overheat(_row(return_5d=1039.0, return_20d=500.0))
    # clip 到 5 后仍然 > 0.25 / > 0.5，触发 60 + 20 = 80
    assert s.score == 80


def test_overheat_healthy_zero():
    s = _score_overheat(_HEALTHY)
    assert s.score == 0


# ── 基本面 ────────────────────────────────────────────────────────────────
def test_fundamental_loss_company():
    s = _score_fundamental(_row(roe=-0.1, pb=0.7, pe_ttm=-10.0))
    assert s.score == 90


def test_fundamental_pe_bubble():
    s = _score_fundamental(_row(roe=0.05, pb=3.0, pe_ttm=300.0))
    assert s.score == 15


def test_fundamental_healthy_zero():
    s = _score_fundamental(_HEALTHY)
    assert s.score == 0


# ── 状态 ──────────────────────────────────────────────────────────────────
def test_status_3_consecutive():
    s = _score_status(_row(consecutive_limit_up_days=4))
    assert s.score == 60


def test_status_2_consecutive():
    s = _score_status(_row(consecutive_limit_up_days=2))
    assert s.score == 30


def test_status_zero():
    s = _score_status(_HEALTHY)
    assert s.score == 0


# ── 等级分桶 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("score,bucket", [
    (5.0, "极低"),
    (25.0, "低"),
    (45.0, "中"),
    (65.0, "高"),
    (85.0, "极高"),
    (100.0, "极高"),
])
def test_bucket_thresholds(score, bucket):
    assert _bucket(score) == bucket


# ── 端到端：聚合 + 权重 ────────────────────────────────────────────────────
def test_aggregate_healthy_low_risk():
    result = _compute_from_row(_HEALTHY)
    assert result.veto is False
    assert result.veto_reasons == []
    # 健康股各维度: liq=0, vol=10, trend=0, overheat=0, fund=0, status=0
    # 加权 = 0.25*0 + 0.30*10 + 0.20*0 + 0.10*0 + 0.10*0 + 0.05*0 = 3.0
    assert result.risk_score == pytest.approx(3.0, abs=0.01)
    assert result.risk_level == "极低"


def test_aggregate_veto_overrides_dimensions():
    result = _compute_from_row(_row(is_st=1))
    assert result.veto is True
    assert result.risk_score == 100.0
    assert result.risk_level == "极高"


def test_aggregate_garbage_stock():
    """综合垃圾票：小盘 + 高波动 + 全空头 + 短期暴涨 + 亏损 + 连板"""
    result = _compute_from_row(_row(
        amount_20d_avg=2e7,  float_mv=1.5e9, turnover_rate=18.0,    # 流动性
        close=10.0,          vol_atr_14=0.9, pct_change=8.0,        # 波动率 ATR 9%
        vol_std_5=0.05,      vol_std_20=0.02, amount_ratio_5d=1.5,  # 扩张
        ma5=11, ma10=12, ma20=13, ma60=14, macd_hist=-0.3,          # 趋势
        return_5d=0.30,      rsi_14=85.0,                           # 过热
        roe=-0.08, pb=0.6, pe_ttm=-5.0,                             # 基本面
        consecutive_limit_up_days=2,                                # 状态
    ))
    # 注意：pct_change=8 + amount_ratio=1.5 不触发 veto（量需 > 2.0），
    # 但 8 > 7 触发异动，且短期暴涨过热都很满
    assert result.veto is False
    assert result.risk_score >= 80
    assert result.risk_level == "极高"


def test_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)


def test_to_dict_shape_v2():
    """API 契约：to_dict() 输出结构含 6 个维度。"""
    d = _compute_from_row(_HEALTHY).to_dict()
    assert d["symbol"] == "SH600519"
    assert d["veto"] is False
    assert set(d["dimensions"].keys()) == {
        "liquidity", "volatility", "trend", "overheat", "fundamental", "status"
    }
    for dim in d["dimensions"].values():
        assert "score" in dim and "reasons" in dim
    assert d["weights"] == DEFAULT_WEIGHTS
    assert "snapshot" in d
