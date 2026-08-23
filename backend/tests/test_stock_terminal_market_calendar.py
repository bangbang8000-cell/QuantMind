"""大盘 MA20 日历纯函数测试：_build_calendar_days / _merge_signal_stats。"""

from datetime import date

import pandas as pd

from backend.services.api.routers.stock_terminal import (
    _build_calendar_days,
    _merge_signal_stats,
)


def _make_df(n: int = 60, start: str = "2026-01-01") -> pd.DataFrame:
    """连续 n 个交易日、收盘价线性递增（MA20 可稳定计算）。"""
    dates = pd.bdate_range(start, periods=n)
    closes = [3000.0 + i * 5.0 for i in range(n)]
    return pd.DataFrame({"trade_date": dates, "close": closes})


def test_build_calendar_days_skips_warmup_and_before_start():
    df = _make_df(60, "2026-01-01")
    # 日历范围从 2026-02-01 开始：前 19 天 MA20 预热被跳过，2 月首个交易日应已成型
    days = _build_calendar_days(df, "2026-02-01")
    assert days, "应有日历日产出"
    assert all(d["date"] >= "2026-02-01" for d in days)
    # 2026-02-01 之前（1 月）的交易日即使有数据也不能出现
    assert not any(d["date"].startswith("2026-01") for d in days)
    # 每个字段齐全且 MA20 已成型
    for d in days:
        assert d["ma20"] is not None
        assert isinstance(d["close"], float)
        # 递增序列：收盘恒高于 MA20，偏离度为正
        assert d["dev_pct"] > 0


def test_build_calendar_days_ma20_value_and_deviation():
    # 恒定价格 3000：MA20 = 3000，偏离度 = 0
    df = pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-01", periods=25),
        "close": [3000.0] * 25,
    })
    days = _build_calendar_days(df, "2026-01-01")
    assert len(days) == 6  # 25 个交易日，前 19 天无 MA20
    for d in days:
        assert d["ma20"] == 3000.0
        assert d["dev_pct"] == 0.0


def test_build_calendar_days_below_ma20_negative_dev():
    # 先 20 天 3100，后 5 天 3000：后期收盘低于 MA20，偏离度为负
    closes = [3100.0] * 20 + [3000.0] * 5
    df = pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-01", periods=25),
        "close": closes,
    })
    days = _build_calendar_days(df, "2026-01-01")
    assert len(days) == 6
    # 第 20 天收盘=MA20（偏离 0），其后收盘跌破均线、偏离为负
    assert days[0]["dev_pct"] == 0.0
    assert all(d["dev_pct"] < 0 for d in days[1:])


def test_build_calendar_days_empty_df():
    assert _build_calendar_days(pd.DataFrame(), "2026-01-01") == []
    assert _build_calendar_days(None, "2026-01-01") == []  # type: ignore[arg-type]


def test_merge_signal_stats_merges_by_date_string():
    days = [
        {"date": "2026-08-14", "close": 3048.52, "ma20": 3010.0, "dev_pct": 1.28},
        {"date": "2026-08-15", "close": 3030.0, "ma20": 3012.0, "dev_pct": 0.6},
    ]
    # asyncpg 返回 date 对象；当日 2 条分数 -> top10_avg 取 2 条均值
    rows = [
        (date(2026, 8, 14), 2, 0.08),
        (date(2026, 8, 15), 0, None),
    ]
    _merge_signal_stats(days, rows)
    assert days[0]["signal_count"] == 2
    assert days[0]["top10_avg"] == 0.08
    assert days[0]["has_inference"] is True
    # 0 条有分数行 -> 无推理
    assert days[1]["signal_count"] == 0
    assert days[1]["top10_avg"] is None
    assert days[1]["has_inference"] is False


def test_merge_signal_stats_top10_avg_only_over_top10():
    """15 条分数 0.01~0.15：top10_avg = 前 10 高分（0.06~0.15）的均值 0.105。"""
    days = [{"date": "2026-08-14"}]
    rows = [(date(2026, 8, 14), 15, sum(x / 100 for x in range(6, 16)) / 10)]
    _merge_signal_stats(days, rows)
    assert days[0]["top10_avg"] == round(0.105, 4)
    assert days[0]["has_inference"] is True
