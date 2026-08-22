from __future__ import annotations

import pandas as pd
import pytest

from backend.services.engine.data_platform.quantdb_factor_reader import (
    QuantDBFactorError,
    QuantDBFactorReader,
)


def _write_factor_partition(root, source: str, frame: pd.DataFrame, dt: str) -> None:
    target = root / "6_ml_datasets" / source / f"dt={dt}"
    target.mkdir(parents=True)
    frame.to_parquet(target / "data.parquet", index=False)


def _frame(day: str, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["600001.SH", "000001.SZ"],
            "date": [day, day],
            "open": [close - 1, close - 1],
            "high": [close + 1, close + 1],
            "low": [close - 2, close - 2],
            "close": [close, close],
            "volume": [100, 100],
            "amount": [1000, 1000],
            "l1_alpha": [0.1, 0.2],
        }
    )


def test_reads_single_source_with_logical_field_alias(tmp_path):
    _write_factor_partition(
        tmp_path, "l1_l2_factors", _frame("2024-01-02", 10), "20240102"
    )
    reader = QuantDBFactorReader(tmp_path)

    status = reader.assert_ready("l1_l2_factors", start="2024-01-02", end="2024-01-02")
    assert status.ready
    assert status.min_date == "2024-01-02"
    data = reader.read_day(
        "l1_l2_factors",
        features=["alpha"],
        feature_sources={"alpha": "l1_alpha"},
        trade_date="2024-01-02",
    )

    assert set(data["symbol"]) == {"SH600001", "SZ000001"}
    assert data["alpha"].tolist() == [0.1, 0.2]


def test_rejects_source_without_common_ohlcv(tmp_path):
    _write_factor_partition(
        tmp_path,
        "l2_factors",
        pd.DataFrame(
            {"symbol": ["600001.SH"], "date": ["2024-01-02"], "l2_alpha": [1.0]}
        ),
        "20240102",
    )
    with pytest.raises(QuantDBFactorError, match="not ready"):
        QuantDBFactorReader(tmp_path).assert_ready("l2_factors")


def test_forward_labels_use_future_close_without_snapshot(tmp_path):
    for day, close in [("2024-01-02", 10), ("2024-01-03", 11), ("2024-01-04", 12)]:
        _write_factor_partition(
            tmp_path, "l1_factors", _frame(day, close), day.replace("-", "")
        )
    reader = QuantDBFactorReader(tmp_path)
    frame = reader.read_range(
        "l1_factors", features=["l1_alpha"], start="2024-01-02", end="2024-01-04"
    )
    labels = reader.forward_labels(frame, horizon=1, signal_lag_days=0)
    first = labels[
        (labels["symbol"] == "SH600001")
        & (labels["trade_date"] == pd.Timestamp("2024-01-02"))
    ]
    assert first.iloc[0]["label"] == pytest.approx(0.1)
