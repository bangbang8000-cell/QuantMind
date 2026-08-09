"""QuantFutures 期货/贵金属数据平台测试。

策略：
- 不联网；不依赖 akshare API 的真实响应
- 校验 catalog 数据集 → akshare field 分发映射（quantfutures_daily_sync）
- 校验日K标准化（akshare → QuantDB schema，volume/amount 兜底）
- 校验分区写入（dt=YYYYMMDD/data.parquet，增量去重）
- 校验管理控制台 FUTURES 数据集目录（_default_datasets("FUTURES")）
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.scripts.akshare_futures_sync import (
    CN_MAIN,
    FOREIGN_SYMBOLS,
    KLINE_COLS,
    SGE_SYMBOLS,
    _normalise_daily,
    _write_kline_partition,
)
from backend.scripts.quantfutures_daily_sync import DATASET_FIELDS, run


def test_symbol_pools_are_populated():
    # 国际期货 / 国内主力 / 上金所现货至少各覆盖主流品种
    assert len(FOREIGN_SYMBOLS) >= 10
    assert "CL" in FOREIGN_SYMBOLS  # NYMEX 原油
    assert len(CN_MAIN) >= 10
    assert "RB0" in CN_MAIN  # 螺纹钢主力连续
    assert "AU0" in CN_MAIN  # 沪金主力连续
    assert "Au99.99" in SGE_SYMBOLS


def test_catalog_dataset_mapping_covers_sync_fields():
    # 后台 catalog 只暴露 daily_forward / futures_realtime 两个数据集，
    # 必须映射到 akshare_futures_sync 的全部 5 个 field，否则面板「同步」会静默空转
    fields = [f for fs in DATASET_FIELDS.values() for f in fs]
    assert set(fields) == {
        "foreign_realtime",
        "foreign_daily",
        "cn_realtime",
        "cn_daily",
        "sge_daily",
    }
    assert DATASET_FIELDS["daily_forward"] == ["foreign_daily", "cn_daily", "sge_daily"]
    assert DATASET_FIELDS["futures_realtime"] == ["foreign_realtime", "cn_realtime"]


def test_run_unknown_dataset_returns_empty_result():
    # 未知数据集不应抛错，返回空 result
    result = run(datasets=["not_a_dataset"])
    assert result["market"] == "futures"
    assert result["result"] == {}


def test_normalise_daily_renames_and_coerces():
    raw = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "open": 100.0, "high": 110.0,
         "low": 95.0, "close": 105.5, "volume": 1000.0},
    ])
    df = _normalise_daily(raw, symbol="CL.FUT")
    assert list(df.columns) == KLINE_COLS
    row = df.iloc[0]
    assert row["symbol"] == "CL.FUT"
    assert row["close"] == 105.5
    # amount = close × volume 估算
    assert row["amount"] == pytest.approx(105.5 * 1000.0)
    assert row["release_id"] == "akshare"
    # 期货 _normalise_daily 保留完整时间（00:00:00），与 QuantDB 分区键对齐
    assert row["time"] == pd.Timestamp("2026-08-01")


def test_normalise_daily_volume_falls_back_to_position():
    # akshare 部分接口无 volume 列，用 position（持仓量）兜底
    raw = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "open": 100.0, "high": 110.0,
         "low": 95.0, "close": 105.5, "position": 500},
    ])
    df = _normalise_daily(raw, symbol="Au99.99")
    row = df.iloc[0]
    assert row["volume"] == 500
    assert row["amount"] == pytest.approx(105.5 * 500.0)


def test_normalise_daily_drops_missing_close():
    raw = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "open": 100.0, "high": 110.0,
         "low": 95.0, "close": None, "volume": 1000.0},
    ])
    df = _normalise_daily(raw, symbol="CL.FUT")
    assert df.empty


def test_write_kline_partition_incremental_dedup(tmp_path):
    root = tmp_path / "1_kline_data" / "daily_forward"
    chunk1 = pd.DataFrame({
        "symbol": ["CL.FUT", "AU0.CN"],
        "time": pd.to_datetime(["2026-08-01", "2026-08-01"]),
        "close": [70.0, 550.0],
        "release_id": ["akshare", "akshare"],
    })
    written = _write_kline_partition(root, chunk1)
    assert written == 1
    target = root / "dt=20260801" / "data.parquet"
    assert target.is_file()

    # 增量写入同一分区：同一 (symbol, time) 应被覆盖而非新增
    chunk2 = pd.DataFrame({
        "symbol": ["CL.FUT"],
        "time": pd.to_datetime(["2026-08-01"]),
        "close": [72.0],
        "release_id": ["akshare"],
    })
    _write_kline_partition(root, chunk2)
    merged = pd.read_parquet(target)
    assert len(merged) == 2  # CL.FUT 被覆盖，不新增
    cl = merged[merged["symbol"] == "CL.FUT"].iloc[0]
    assert cl["close"] == 72.0


def test_market_console_futures_datasets():
    from backend.services.api.routers.admin.global_market_console import _default_datasets

    specs = _default_datasets("FUTURES")
    by_name = {s.dataset: s for s in specs}
    names = set(by_name)
    # 期货数据段精简：日K + 实时快照
    assert names == {"daily_forward", "futures_realtime"}
    assert by_name["daily_forward"].layout == "partition"
    assert by_name["futures_realtime"].layout == "symbol"
    # 与同步分发映射一致（catalog 数据集名必须能被 quantfutures_daily_sync 识别）
    for n in names:
        assert n in DATASET_FIELDS
