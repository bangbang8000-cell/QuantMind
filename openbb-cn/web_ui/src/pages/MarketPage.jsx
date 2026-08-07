import React, { useState, useEffect } from 'react';
import { Card, Typography, Row, Col, Spin, message, Table } from 'antd';
import { BarChartOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title } = Typography;
const API_BASE = 'http://localhost:8000';

const MarketPage = () => {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState({});
  const [hotStocks, setHotStocks] = useState([]);

  useEffect(() => {
    fetchMarketOverview();
  }, []);

  const fetchMarketOverview = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/api/v1/stocks/market-overview`, {
        params: { provider: 'akshare' }
      });
      if (res.data.success) {
        setOverview(res.data.data || {});
      }
    } catch (err) {
      message.error('获取市场概览失败');
    }
    setLoading(false);
  };

  const renderIndex = (name, data) => {
    if (!data || data.error) {
      return (
        <Card size="small" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 14, color: '#999' }}>{name}</div>
          <div style={{ fontSize: 20, color: '#999' }}>-</div>
        </Card>
      );
    }

    const isUp = data.change > 0;
    const color = isUp ? '#cf1322' : '#3f8600';

    return (
      <Card size="small" style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 14, color: '#999' }}>{name}</div>
        <div style={{ fontSize: 24, fontWeight: 'bold', color }}>
          {data.price?.toFixed(2) || '-'}
        </div>
        <div style={{ color }}>
          {isUp ? '+' : ''}{data.change?.toFixed(2) || '-'} ({data.pct_change?.toFixed(2) || '-'}%)
        </div>
      </Card>
    );
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" tip="加载市场数据..." />
      </div>
    );
  }

  return (
    <div>
      <Title level={2}><BarChartOutlined /> 市场概览</Title>

      <Title level={4}>主要指数</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
        <Col xs={12} sm={8} md={6}>
          {renderIndex('上证指数', overview['上证指数'])}
        </Col>
        <Col xs={12} sm={8} md={6}>
          {renderIndex('深证成指', overview['深证成指'])}
        </Col>
        <Col xs={12} sm={8} md={6}>
          {renderIndex('创业板指', overview['创业板指'])}
        </Col>
        <Col xs={12} sm={8} md={6}>
          {renderIndex('沪深300', overview['沪深300'])}
        </Col>
        <Col xs={12} sm={8} md={6}>
          {renderIndex('科创50', overview['科创50'])}
        </Col>
      </Row>

      <Card title="市场状况说明">
        <ul>
          <li><strong>上证指数</strong>：上海证券交易所综合股价指数，反映上海市场整体表现</li>
          <li><strong>深证成指</strong>：深圳证券交易所成分股价指数，反映深圳市场整体表现</li>
          <li><strong>创业板指</strong>：创业板综合指数，反映创业板上市股票走势</li>
          <li><strong>沪深300</strong>：沪深300指数，由沪深市场中规模和流动性最大的300只股票组成</li>
          <li><strong>科创50</strong>：科创板50指数，反映科创板市场走势</li>
        </ul>
      </Card>

      <Card title="投资小贴士" style={{ marginTop: 24 }}>
        <ul>
          <li>指数涨跌幅超过2%时，市场波动较大，建议谨慎操作</li>
          <li>关注成交量变化，量价齐升通常预示趋势延续</li>
          <li>注意市场轮动，不同板块可能出现分化</li>
          <li>做好仓位管理，避免追涨杀跌</li>
        </ul>
      </Card>
    </div>
  );
};

export default MarketPage;
