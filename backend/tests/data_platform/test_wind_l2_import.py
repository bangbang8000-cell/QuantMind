"""Wind L2 导入解析测试 — 万得逐笔行情/委托/成交 → QuantDB parquet 格式。

策略：
- 不联网；不依赖 7z 解压（用 pandas 构造测试 csv 直接喂解析函数）
- 校验行情快照 10 档盘口、价格×10000 归一、时间戳 UTC 对齐
- 校验逐笔委托/成交字段映射
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from backend.scripts.wind_l2_import import (
    _wind_time_to_ms,
    _parse_quote_csv,
    _parse_order_csv,
    _parse_trade_csv,
)


def _write_quote_csv(path: Path) -> Path:
    rows = []
    # 构造 2 行行情快照（09:30:00 与 09:30:03，价格×10000）
    for t, price in [(93000000, 113100), (93003000, 113200)]:
        row = {
            "万得代码": "000001.SZ", "交易所代码": 1, "自然日": 20260511, "时间": t,
            "成交价": price, "成交量": 0, "成交额": 0, "成交笔数": 412, "IOPV": 0,
            "成交标志": "", "BS标志": 0,
            "当日累计成交量": 10116, "当日成交额": 10876480,
            "最高价": 113300, "最低价": 112900, "开盘价": 113000, "前收盘": 113100,
        }
        for i in range(1, 11):
            row[f"申卖价{i}"] = 113100 + i * 100
            row[f"申买价{i}"] = 113100 - i * 100
            row[f"申卖量{i}"] = 1000 + i
            row[f"申买量{i}"] = 2000 + i
        row.update({
            "加权平均叫卖价": 0, "加权平均叫买价": 0, "叫卖总量": 0, "叫买总量": 0,
            "不加权指数": 0, "品种总数": 0, "上涨品种数": 0, "下跌品种数": 0, "持平品种数": 0,
        })
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="gbk")
    return path


def test_wind_time_to_ms():
    # 09:15:00 北京 → 2026-05-11 09:15:00 +08 = 1778462100000 (UTC 01:15:00)
    assert _wind_time_to_ms(91500000, "20260511") == 1778462100000
    # 09:30:59.990
    assert _wind_time_to_ms(93059990, "20260511") == 1778463059990
    # 15:00:00
    assert _wind_time_to_ms(150000000, "20260511") == 1778482800000


def test_parse_quote_csv_ten_levels(tmp_path):
    p = _write_quote_csv(tmp_path / "行情.csv")
    df = _parse_quote_csv(p, "20260511")
    assert len(df) == 2
    # 时间对齐 QuantDB tick
    assert df.iloc[0]["time"] == 1778463000000  # 09:30:00 +08
    assert df.iloc[1]["time"] == 1778463003000
    # 价格 ×10000 → 元
    assert df.iloc[0]["lastPrice"] == pytest.approx(11.31)
    assert df.iloc[0]["open"] == pytest.approx(11.30)
    assert df.iloc[0]["lastClose"] == pytest.approx(11.31)
    # 十档盘口
    ask = np.asarray(df.iloc[0]["askPrice"])
    bid = np.asarray(df.iloc[0]["bidPrice"])
    assert len(ask) == 10 and len(bid) == 10
    assert ask[0] == pytest.approx(11.32)  # 113200/10000
    assert bid[0] == pytest.approx(11.30)
    assert np.asarray(df.iloc[0]["askVol"]).tolist() == list(range(1001, 1011))
    # 累计量
    assert df.iloc[0]["volume"] == 10116
    assert df.iloc[0]["transactionNum"] == 412


def test_parse_order_csv(tmp_path):
    pd.DataFrame([
        {"万得代码": "000001.SZ", "交易所代码": 1, "自然日": 20260511, "时间": 91500000,
         "委托编号": 0, "交易所委托号": 1050, "委托类型": 0, "委托代码": "B",
         "委托价格": 101700, "委托数量": 100},
    ]).to_csv(tmp_path / "逐笔委托.csv", index=False, encoding="gbk")
    df = _parse_order_csv(tmp_path / "逐笔委托.csv", "20260511")
    assert len(df) == 1
    r = df.iloc[0]
    assert r["time"] == 1778462100000  # 09:15:00
    assert r["order_id"] == 1050
    assert r["direction"] == "B"
    assert r["price"] == pytest.approx(10.17)
    assert r["volume"] == 100


def test_parse_trade_csv(tmp_path):
    pd.DataFrame([
        {"万得代码": "000001.SZ", "交易所代码": 1, "自然日": 20260511, "时间": 91500030,
         "成交编号": 2603, "成交代码": "C", "委托代码": 0, "BS标志": "",
         "成交价格": 0, "成交数量": 100, "叫卖序号": 0, "叫买序号": 2602},
    ]).to_csv(tmp_path / "逐笔成交.csv", index=False, encoding="gbk")
    df = _parse_trade_csv(tmp_path / "逐笔成交.csv", "20260511")
    assert len(df) == 1
    r = df.iloc[0]
    assert r["time"] == 1778462100030
    assert r["trade_id"] == 2603
    assert r["trade_type"] == "C"
    assert r["bid_order_id"] == 2602
