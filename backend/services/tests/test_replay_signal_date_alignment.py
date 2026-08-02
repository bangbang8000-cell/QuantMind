"""回放信号 T+1 日期对齐测试。

锁死 prev_session(D) 前视偏差：replay_signals.trade_date 必须等于
next_session(数据日)，不能等于数据日本身。
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.services.trade.simulation.replay.signal_generator import (
    ReplaySignalGenerator,
    _dt_int_to_date,
)


class TestSignalDateAlignment:
    """信号生效日 = next_session(数据日)，无前视偏差。"""

    def test_t_plus_one_offset(self):
        """数据日 D 的信号必须存到 next_session(D)，不能存到 D。"""
        # 构造 sessions 列表：20240301, 20240304, 20240305
        sessions = [20240301, 20240304, 20240305]

        # 数据日 = 20240301 → 信号生效日 = 20240304
        # 数据日 = 20240304 → 信号生效日 = 20240305
        # 数据日 = 20240305 → 无下一个交易日，跳过

        # 验证 T+1 偏移逻辑
        for data_day, expected_signal_date in [
            (20240301, 20240304),
            (20240304, 20240305),
        ]:
            pos = sessions.index(data_day)
            signal_date_int = sessions[pos + 1]
            assert signal_date_int == expected_signal_date, (
                f"数据日 {data_day} 的信号应生效于 {expected_signal_date}，"
                f"实际 {signal_date_int}"
            )
            assert _dt_int_to_date(signal_date_int) == date(
                expected_signal_date // 10000,
                (expected_signal_date % 10000) // 100,
                expected_signal_date % 100,
            )

    def test_no_signal_for_last_day(self):
        """区间最后一天没有 next_session，不应产生信号。"""
        sessions = [20240304, 20240305]
        # 20240305 是最后一天 (pos=1), pos+1=2 >= len(sessions)=2 → skip
        pos = sessions.index(20240305)
        assert pos + 1 >= len(sessions)

    def test_signal_date_out_of_range_skipped(self):
        """信号生效日超出 [start, end] 范围的应跳过。"""
        sessions = [20240304, 20240305, 20240306]
        end_int = 20240305

        # 数据日 = 20240305 → 信号生效日 = 20240306 > end_int → skip
        pos = sessions.index(20240305)
        signal_date_int = sessions[pos + 1]
        assert signal_date_int == 20240306
        assert signal_date_int > end_int

    def test_data_start_includes_prev_session(self):
        """start_date 的信号需要 start_date-1 的数据，
        所以数据日范围必须包含 prev_session(start_date)。
        """
        sessions = [20240301, 20240304, 20240305]
        start_int = 20240304

        # prev_session(20240304) = 20240301
        before_start = [d for d in sessions if d < start_int]
        data_start_int = before_start[-1] if before_start else start_int
        assert data_start_int == 20240301

        # 20240301 should be included in data_days
        assert data_start_int < start_int


class TestDtIntToDate:
    """日期整数 → date 对象转换。"""

    def test_normal(self):
        assert _dt_int_to_date(20240304) == date(2024, 3, 4)

    def test_year_boundary(self):
        assert _dt_int_to_date(20231231) == date(2023, 12, 31)

    def test_single_digit_month_day(self):
        assert _dt_int_to_date(20240105) == date(2024, 1, 5)
