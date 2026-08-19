"""Unit and integration tests for QuantDB Market Analysis feed."""

import pytest
from backend.services.api.market_analysis import quantdb_feed


def test_quantdb_market_breadth():
    """验证全市场涨跌统计、涨跌停家数、成交额和赚钱效应指标"""
    data = quantdb_feed.get_market_breadth()
    assert isinstance(data, dict)
    assert "advance_count" in data
    assert "decline_count" in data
    assert "flat_count" in data
    assert "total_turnover_yi" in data
    assert "profit_effect" in data
    assert "limit_up_broken_ratio" in data

    total_stocks = data["advance_count"] + data["decline_count"] + data["flat_count"]
    # 真实 A 股上市公司数量在 4000 - 6000 家之间
    assert total_stocks >= 4000, f"Total stocks count {total_stocks} is too low"
    assert data["total_turnover_yi"] > 0
    assert 0 <= data["profit_effect"] <= 100


def test_quantdb_sector_heatmap_shenwan():
    """验证申万一级行业热力图聚合数据"""
    sectors = quantdb_feed.get_sector_heatmap(category="shenwan")
    assert isinstance(sectors, list)
    assert len(sectors) >= 20, f"Shenwan sector count {len(sectors)} is too low"

    for s in sectors:
        assert "name" in s
        assert "value" in s
        assert "pct_change" in s
        assert "leader" in s
        assert "leader_pct" in s


def test_quantdb_sector_heatmap_concept():
    """验证概念板块热力图聚合数据"""
    concepts = quantdb_feed.get_sector_heatmap(category="concept")
    assert isinstance(concepts, list)
    assert len(concepts) >= 10, f"Concept count {len(concepts)} is too low"


def test_quantdb_indices_overview():
    """验证五大核心大盘指数快照与分时趋势"""
    indices = quantdb_feed.get_indices_overview()
    assert isinstance(indices, list)
    assert len(indices) == 5

    symbols = [idx["symbol"] for idx in indices]
    assert "SH000001" in symbols or "000001.SH" in symbols
    assert "SZ399001" in symbols or "399001.SZ" in symbols

    for idx in indices:
        assert idx["price"] > 0
        assert "trend" in idx
        assert len(idx["trend"]) > 0


def test_quantdb_stock_money_flow():
    """验证个股主力资金流向排行"""
    flows = quantdb_feed.get_stock_money_flow(limit=10)
    assert isinstance(flows, list)
    assert len(flows) > 0
    assert len(flows) <= 10

    first = flows[0]
    assert "symbol" in first
    assert "name" in first
    assert "net_inflow" in first
    assert "main_ratio" in first
    assert "super_large" in first
    assert "large" in first


def test_quantdb_money_flow_sankey():
    """验证资金流动桑基图节点与连接关系"""
    sankey = quantdb_feed.get_money_flow_sankey()
    assert isinstance(sankey, dict)
    assert "nodes" in sankey
    assert "links" in sankey
    assert len(sankey["nodes"]) > 0
    assert len(sankey["links"]) > 0


def test_quantdb_tag_lookup():
    """验证标签查成分股以及个股查归属标签"""
    # 1. 标签查个股
    tag_res = quantdb_feed.get_stocks_by_tag(tag="低空经济", limit=15)
    assert isinstance(tag_res, list)
    assert len(tag_res) > 0

    # 2. 个股查标签 (招商银行 SH600036)
    stock_tags = quantdb_feed.get_tags_by_stock(symbol="SH600036")
    assert isinstance(stock_tags, dict)
    assert len(stock_tags) > 0


def test_quantdb_money_flow_period():
    """验证多周期资金流向排行数据"""
    periods = ["1d", "3d", "5d", "10d", "20d"]
    for p in periods:
        res = quantdb_feed.get_money_flow_period(
            period=p,
            dimension="sector",
            category="shenwan",
            limit=10,
        )
        assert isinstance(res, list)
        assert len(res) > 0
