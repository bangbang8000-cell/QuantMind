from __future__ import annotations

import pandas as pd

from backend.shared.fundamental_aligner import FundamentalAligner


def test_filter_instruments_prefers_features_daily_and_normalizes_symbols(tmp_path):
    day_dir = tmp_path / "dt=20260821"
    day_dir.mkdir()
    pd.DataFrame(
        {
            "symbol": ["600001.SH", "000002.SZ", "600003.SH"],
            "total_mv": [3e9, 3e9, 3e9],
            "float_mv": [1e9, 1e9, 1e9],
            "pe_ttm": [20.0, -5.0, 30.0],
            "pb": [2.0, 2.0, 5.0],
            "vol_std_20": [0.03, 0.03, 0.08],
        }
    ).to_parquet(day_dir / "data.parquet", index=False)

    aligner = FundamentalAligner(parquet_path=str(tmp_path / "legacy.parquet"))
    aligner.features_daily_path = tmp_path

    filtered = aligner.filter_instruments(
        "2026-08-21",
        ["SH600001", "SZ000002", "SH600003"],
        {
            "total_mv_min": 2e9,
            "float_mv_min": 5e8,
            "pe_ttm_min": 0,
            "pb_max": 3.5,
            "vol_std_20_max": 0.06,
        },
    )

    assert filtered == ["SH600001"]

