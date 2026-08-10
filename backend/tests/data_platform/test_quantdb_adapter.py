"""QuantDB 远端适配器测试。

策略：
- 不联网；mock QuantDBClient，校验 fetch_field 各分支对客户端方法的调用参数
- 重点覆盖 valuation 的 category_id（回归：曾误用 "4" 应为 "5"）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.services.engine.data_platform.adapters.quantdb_adapter import (
    QuantDBAdapter,
    _to_qdb_symbol,
)


@pytest.fixture()
def adapter() -> QuantDBAdapter:
    a = QuantDBAdapter()
    client = MagicMock()

    def _fake_load(category_id, sub_category, symbol=None, **kwargs):
        if sub_category == "valuation":
            return pd.DataFrame({
                "symbol": [symbol],
                "time": ["2026-08-07"],
                "close": [38.8],
                "pe_ttm": [6.49],
            })
        if sub_category == "income":
            return pd.DataFrame({
                "symbol": [symbol],
                "m_timetag": ["2026-03-31"],
                "revenue": [1.0],
            })
        if sub_category == "l1_l2_factors":
            return pd.DataFrame({
                "symbol": [symbol],
                "mom_ret_1d": [-0.0031],
            })
        return pd.DataFrame({"symbol": [symbol]})

    client.load_as_df.side_effect = _fake_load
    a._client = client
    return a


class TestSymbolConversion:
    def test_sh_prefix(self):
        assert _to_qdb_symbol("SH600036") == "600036.SH"

    def test_sz_prefix(self):
        assert _to_qdb_symbol("SZ000001") == "000001.SZ"

    def test_bj_prefix(self):
        assert _to_qdb_symbol("BJ430047") == "430047.BJ"

    def test_already_suffix(self):
        assert _to_qdb_symbol("600036.SH") == "600036.SH"

    def test_digits_auto_sh(self):
        assert _to_qdb_symbol("600036") == "600036.SH"

    def test_digits_auto_sz(self):
        assert _to_qdb_symbol("000001") == "000001.SZ"

    def test_digits_auto_bj(self):
        assert _to_qdb_symbol("430047") == "430047.BJ"


class TestFetchFieldDispatch:
    def test_valuation_uses_category_5(self, adapter: QuantDBAdapter):
        """估值数据必须使用 category_id=5（回归：曾误用 4 导致资源不存在）。"""
        df = adapter._fetch_valuation("SH600036", None, None)
        assert not df.empty
        assert adapter._client.load_as_df.call_args.kwargs["category_id"] == "5"
        assert adapter._client.load_as_df.call_args.kwargs["sub_category"] == "valuation"

    def test_financial_uses_category_3(self, adapter: QuantDBAdapter):
        df = adapter._fetch_financial("SH600036", None, None)
        assert not df.empty
        assert adapter._client.load_as_df.call_args.kwargs["category_id"] == "3"
        assert adapter._client.load_as_df.call_args.kwargs["sub_category"] == "income"

    def test_ai_factors_uses_category_6(self, adapter: QuantDBAdapter):
        df = adapter._fetch_ai_factors("SH600036")
        assert not df.empty
        assert adapter._client.load_as_df.call_args.kwargs["category_id"] == "6"

    def test_fetch_field_routes_valuation(self, adapter: QuantDBAdapter):
        df = adapter.fetch_field("valuation", "SH600036")
        assert not df.empty
        assert adapter._client.load_as_df.call_args.kwargs["category_id"] == "5"

    def test_fetch_field_unknown_raises(self, adapter: QuantDBAdapter):
        from backend.services.engine.data_platform.base import InvalidFieldRequest
        with pytest.raises(InvalidFieldRequest):
            adapter.fetch_field("not_a_real_field", "SH600036")

    def test_valuation_error_raises_data_unavailable(self):
        a = QuantDBAdapter()
        client = MagicMock()
        client.load_as_df.side_effect = RuntimeError("CDN 410")
        a._client = client
        from backend.services.engine.data_platform.base import DataUnavailable
        with pytest.raises(DataUnavailable):
            a._fetch_valuation("SH600036", None, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
