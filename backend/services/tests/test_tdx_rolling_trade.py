"""TdxRollingTradeService.compute_rolling_signals 单元测试。

纯函数级测试：买卖信号计算、大盘 MA20 过滤、持仓滚动。
"""
import pytest

from backend.services.trade.services.tdx_rolling_trade_service import (
    DEFAULT_SCORE_THRESHOLD,
    TdxRollingTradeService,
)


@pytest.fixture
def svc() -> TdxRollingTradeService:
    return TdxRollingTradeService()


def _pos(symbol, volume=1000, available_volume=None, name=""):
    return {
        "symbol": symbol,
        "name": name or symbol,
        "volume": volume,
        "available_volume": available_volume if available_volume is not None else volume,
        "cost_price": 10.0,
        "market_value": 10000.0,
    }


class TestComputeRollingSignals:
    def test_buys_stocks_above_threshold_when_index_above_ma20(self, svc):
        # Arrange: 000001.SZ 11.25 元/股，1 万元可买一手
        score_map = {"000001.SZ": 2.8, "000002.SZ": 1.5}
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=[], index_above_ma20=True
        )
        # Assert
        assert [b["symbol"] for b in result["buys"]] == ["000001.SZ"]
        assert result["sells"] == []

    def test_no_buys_when_index_below_ma20(self, svc):
        # Arrange
        score_map = {"600519.SH": 2.8}
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=[], index_above_ma20=False
        )
        # Assert
        assert result["buys"] == []

    def test_sells_held_stock_dropping_below_threshold(self, svc):
        # Arrange
        score_map = {"600519.SH": 1.9}
        positions = [_pos("600519.SH")]
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=True
        )
        # Assert
        assert [s["symbol"] for s in result["sells"]] == ["600519.SH"]

    def test_sells_held_stock_missing_from_new_run(self, svc):
        # Arrange
        score_map = {}  # 最新推理无该股
        positions = [_pos("600519.SH")]
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=True
        )
        # Assert
        assert [s["symbol"] for s in result["sells"]] == ["600519.SH"]
        assert "最新推理已无该股" in result["sells"][0]["reason"]

    def test_holds_stock_still_above_threshold(self, svc):
        # Arrange
        score_map = {"600519.SH": 2.5}
        positions = [_pos("600519.SH")]
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=True
        )
        # Assert
        assert result["sells"] == []
        assert result["buys"] == []
        assert [h["symbol"] for h in result["holds"]] == ["600519.SH"]

    def test_sells_still_happen_when_index_below_ma20(self, svc):
        # Arrange
        score_map = {"600519.SH": 1.5}
        positions = [_pos("600519.SH")]
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=False
        )
        # Assert
        assert [s["symbol"] for s in result["sells"]] == ["600519.SH"]

    def test_buys_ranked_by_score_desc(self, svc):
        # Arrange: 三只低价股均可买一手
        score_map = {"000001.SZ": 2.3, "000002.SZ": 3.0, "000063.SZ": 2.7}
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=[], index_above_ma20=True
        )
        # Assert
        assert [b["symbol"] for b in result["buys"]] == [
            "000002.SZ",
            "000063.SZ",
            "000001.SZ",
        ]

    def test_no_buy_for_already_held_stock(self, svc):
        # Arrange
        score_map = {"600519.SH": 2.8}
        positions = [_pos("600519.SH")]
        # Act
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=True
        )
        # Assert
        assert result["buys"] == []

    def test_score_equal_to_threshold_sells(self, svc):
        # 规则边界: 分数 <= 阈值 应卖出（"低于2.2分，第二天要卖出"）
        score_map = {"600519.SH": DEFAULT_SCORE_THRESHOLD}
        positions = [_pos("600519.SH")]
        result = svc.compute_rolling_signals(
            score_map=score_map, positions=positions, index_above_ma20=True
        )
        assert [s["symbol"] for s in result["sells"]] == ["600519.SH"]

    def test_custom_threshold_from_config(self, svc):
        # 阈值可配置: 3.0 时 2.8 分应卖出而不是买入
        score_map = {"600519.SH": 2.8}
        positions = [_pos("600519.SH")]
        result = svc.compute_rolling_signals(
            score_map=score_map,
            positions=positions,
            index_above_ma20=True,
            score_threshold=3.0,
        )
        assert [s["symbol"] for s in result["sells"]] == ["600519.SH"]
        assert result["score_threshold"] == 3.0

    def test_custom_threshold_buys_lower_score(self, svc):
        # 阈值调低到 1.0 时, 1.5 分也应买入
        score_map = {"000001.SZ": 1.5}
        result = svc.compute_rolling_signals(
            score_map=score_map,
            positions=[],
            index_above_ma20=True,
            score_threshold=1.0,
        )
        assert [b["symbol"] for b in result["buys"]] == ["000001.SZ"]
