"""回归测试：DL 时序推理窗口必须截止到 trade_date。

背景：load_window_data 曾漏掉 `window <= trade_date` 截断，tail(step_len)
取到 parquet 末尾的未来窗口，导致批量回填历史日期时所有日期分数完全相同
（且含前视偏差）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "engine"
    / "inference"
    / "templates"
    / "inference_parquet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("inference_parquet_tpl", _TEMPLATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["inference_parquet_tpl"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_snapshot(tmp_path: Path) -> Path:
    """构造 3 只股票 × 30 交易日的特征快照，最后一列 close 随日期线性变化。"""
    dates = pd.date_range("2026-01-01", periods=30, freq="B").strftime("%Y-%m-%d")
    rows = []
    for sym in ("600519", "000001", "300750"):
        for i, d in enumerate(dates):
            rows.append(
                {
                    "symbol": sym,
                    "trade_date": d,
                    "close": 100.0 + i,  # 随时间单调变化 → 窗口不同则 close 均值必不同
                    "feature1": float(i % 7),
                    "volume": 1e6,
                    "is_st": 0,
                }
            )
    df = pd.DataFrame(rows)
    p = tmp_path / "model_features_2026.parquet"
    df.to_parquet(p, engine="pyarrow")
    return p


def _meta(tmp_path: Path) -> dict:
    return {
        "context": {"market": "CN"},
        "is_sequence_model": True,
        "dl_params": {"dl_step_len": 20},
        "feature_columns": ["close", "feature1"],
    }


def test_window_does_not_contain_future_data(tmp_path):
    """窗口最大 trade_date 必须 <= 推理日（前视偏差回归）。"""
    mod = _load_module()
    snap = _make_snapshot(tmp_path)
    # 2026-02-05 前已有 25 个交易日，足够 20 天窗口
    window = mod.load_window_data("2026-02-05", tmp_path, _meta(tmp_path), 20)

    assert len(window) > 0
    max_date = window["trade_date"].max()
    assert max_date == "2026-02-05"
    # 窗口深度：每只股票 20 天
    assert window.groupby("symbol").size().max() == 20


def test_windows_differ_across_dates(tmp_path):
    """不同 trade_date 的窗口不同 → 输入特征均值不同（修复前两者完全相同）。"""
    mod = _load_module()
    snap = _make_snapshot(tmp_path)
    meta = _meta(tmp_path)

    w_early = mod.load_window_data("2026-01-20", tmp_path, meta, 20)
    w_late = mod.load_window_data("2026-02-05", tmp_path, meta, 20)

    # 修复前 bug：early/late 都取 parquet 末尾 20 天，完全相同
    early_close = (
        w_early.sort_values(["symbol", "trade_date"])
        .groupby("symbol")["close"]
        .mean()
        .to_dict()
    )
    late_close = (
        w_late.sort_values(["symbol", "trade_date"])
        .groupby("symbol")["close"]
        .mean()
        .to_dict()
    )
    assert early_close != late_close
    # 且窗口确实被 trade_date 截断
    assert w_early["trade_date"].max() == "2026-01-20"
    assert w_late["trade_date"].max() == "2026-02-05"


def test_backfill_latest_date_unchanged(tmp_path):
    """回填到快照最后一天时，窗口 = 末尾 step_len 天（与修复前一致，不回归）。"""
    mod = _load_module()
    snap = _make_snapshot(tmp_path)
    meta = _meta(tmp_path)

    w_last = mod.load_window_data("2026-02-10", tmp_path, meta, 20)
    # 30 个工作日最后一天是 2026-02-10
    assert w_last["trade_date"].max() == "2026-02-10"
    assert w_last.groupby("symbol").size().max() == 20


def test_symbols_absent_on_trade_date_are_excluded(tmp_path):
    """窗口集合与推理日股票集合一致（无当日记录的股票不进窗口）。"""
    mod = _load_module()
    snap = _make_snapshot(tmp_path)
    df = pd.read_parquet(snap)
    # 600519 的最后 5 天删除 → 推理日 2026-02-10 当天无记录
    df = df[~((df["symbol"] == "600519") & (df["trade_date"] >= "2026-02-04"))]
    df.to_parquet(snap, engine="pyarrow")

    window = mod.load_window_data("2026-02-10", tmp_path, _meta(tmp_path), 20)
    assert "600519" not in set(window["symbol"].astype(str))
