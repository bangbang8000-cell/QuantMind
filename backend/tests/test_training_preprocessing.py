"""preprocessing 纯函数单元测试。

验证训练数据预处理核心逻辑：分类标签二值化、分位缩尾、截面 Z-score、
缺失值填充。这些函数为训练/推理共用，行为错误会直接导致模型训练偏差。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# docker/training/preprocessing.py 是独立纯函数模块（无 backend 依赖），
# 训练容器内与 train.py 同目录导入，测试时注入该目录。
_TRAINING_DIR = Path(__file__).resolve().parents[2] / "docker" / "training"
if str(_TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(_TRAINING_DIR))

from preprocessing import (  # noqa: E402
    binarize_labels,
    cross_sectional_median_fill,
    cross_sectional_preprocess,
    cross_sectional_zscore,
    winsorize,
)


# ── binarize_labels ──────────────────────────────────────────────────────────

def test_binarize_labels_positive_negative() -> None:
    y = np.array([0.02, -0.01, 0.0, 0.05, -0.03])
    out = binarize_labels(y)
    assert out.dtype == np.float32
    assert out.tolist() == [1.0, 0.0, 0.0, 1.0, 0.0]


def test_binarize_labels_preserves_nan() -> None:
    y = np.array([0.02, np.nan, -0.01])
    out = binarize_labels(y)
    assert np.isnan(out[1])
    assert out[0] == 1.0
    assert out[2] == 0.0


def test_binarize_labels_custom_threshold() -> None:
    y = np.array([0.005, 0.01, 0.02])
    out = binarize_labels(y, threshold=0.01)
    assert out.tolist() == [0.0, 0.0, 1.0]  # 严格 > threshold → 1


# ── winsorize (分位缩尾) ────────────────────────────────────────────────────

def test_winsorize_clips_extremes() -> None:
    # 1..100 均匀，99 和 100 被 p99 截断，0 被 p1 截断
    x = np.arange(1, 101, dtype=np.float64)
    out = winsorize(x, (0.01, 0.99))
    assert out.max() < 100.0
    assert out.min() > 1.0
    assert out.shape == x.shape


def test_winsorize_small_sample_unchanged() -> None:
    # 样本 < 10 不缩尾
    x = np.array([1.0, 2.0, 3.0])
    out = winsorize(x)
    assert np.array_equal(out, x.astype(np.float32))


def test_winsorize_preserves_nan() -> None:
    x = np.array([1.0, np.nan, 5.0, 100.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    out = winsorize(x)
    assert np.isnan(out[1])


# ── cross_sectional_zscore ──────────────────────────────────────────────────

def test_zscore_normalizes_per_date() -> None:
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 5 + ["2024-01-03"] * 5,
        "feat": [1, 2, 3, 4, 5, 100, 200, 300, 400, 500],
    })
    out = cross_sectional_zscore(df, ["feat"], winsor=False)
    # 每天截面均值 ≈ 0，std（ddof=0，与 numpy 一致）≈ 1
    for date, grp in out.groupby("trade_date"):
        assert abs(grp["feat"].mean()) < 1e-6
        assert abs(grp["feat"].std(ddof=0) - 1.0) < 1e-6


def test_zscore_constant_col_zero() -> None:
    df = pd.DataFrame({"trade_date": ["2024-01-02"] * 3, "feat": [5.0, 5.0, 5.0]})
    out = cross_sectional_zscore(df, ["feat"])
    assert (out["feat"] == 0.0).all()


def test_zscore_no_nan_output() -> None:
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 10,
        "feat": list(range(10)),
    })
    out = cross_sectional_zscore(df, ["feat"])
    assert not out["feat"].isna().any()


# ── cross_sectional_median_fill ─────────────────────────────────────────────

def test_median_fill_suspended_row() -> None:
    # 停牌：个别 NaN 用截面中位数填充（满足 min_rows=20 阈值）
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 30,
        "feat": list(range(30)),
    })
    df.loc[5, "feat"] = np.nan  # 停牌
    out = cross_sectional_median_fill(df, ["feat"])
    assert not out["feat"].isna().any()
    # 有效值 [0..4,6..29] 共 29 个，中位数是排序后第 15 个值 = 15
    assert out.loc[5, "feat"] == 15.0
    assert out.loc[0, "feat"] == 0.0  # 正常值不变


def test_whole_column_missing_fills_zero() -> None:
    # 整列缺失（非 NaN 行数 < 阈值）填 0
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 30,
        "feat": [np.nan] * 30,
    })
    out = cross_sectional_median_fill(df, ["feat"])
    assert (out["feat"] == 0.0).all()


# ── cross_sectional_preprocess (主入口) ─────────────────────────────────────

def test_preprocess_disabled_returns_unchanged() -> None:
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 3,
        "feat": [1.0, np.nan, 3.0],
    })
    out = cross_sectional_preprocess(df, ["feat"], enabled=False)
    pd.testing.assert_frame_equal(out, df)


def test_preprocess_enabled_normalizes() -> None:
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 10,
        "feat": list(range(10)),
    })
    out = cross_sectional_preprocess(df, ["feat"], enabled=True)
    assert abs(out["feat"].mean()) < 1e-6
    assert not out["feat"].isna().any()


def test_preprocess_exclude_skips_feature() -> None:
    # exclude 中的特征（如类别列）不参与变换
    df = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 10,
        "feat": list(range(10)),
        "ind_code_l1": [5] * 10,
    })
    out = cross_sectional_preprocess(df, ["feat", "ind_code_l1"], enabled=True, exclude={"ind_code_l1"})
    assert (out["ind_code_l1"] == 5).all()  # 原样保留
    assert abs(out["feat"].mean()) < 1e-6
