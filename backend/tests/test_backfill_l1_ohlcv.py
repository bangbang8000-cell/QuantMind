from __future__ import annotations

import pandas as pd

from backend.scripts.backfill_l1_ohlcv import backfill_l1_ohlcv


def test_backfill_l1_ohlcv_writes_missing_prices_without_changing_factor(tmp_path):
    l1_path = tmp_path / "6_ml_datasets" / "l1_factors" / "l1_factors_20240102.parquet"
    l1_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {"symbol": ["600001.SH"], "date": ["2024-01-02"], "alpha": [0.25]}
    ).to_parquet(l1_path, index=False)
    daily_path = tmp_path / "1_kline_data" / "daily_backward" / "dt=20240102"
    daily_path.mkdir(parents=True)
    pd.DataFrame(
        {
            "symbol": ["600001.SH"],
            "open": [9.0],
            "high": [11.0],
            "low": [8.0],
            "close": [10.0],
            "volume": [100.0],
            "amount": [1000.0],
        }
    ).to_parquet(daily_path / "data.parquet", index=False)

    result = backfill_l1_ohlcv(tmp_path)
    repaired = pd.read_parquet(l1_path)

    assert result["updated"] == 1
    assert result["cells_backfilled"] == 6
    assert repaired.loc[0, "alpha"] == 0.25
    assert repaired.loc[0, "close"] == 10.0
