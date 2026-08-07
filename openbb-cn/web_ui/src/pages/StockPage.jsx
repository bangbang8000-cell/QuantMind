import React, { useState } from 'react';
import { Form, Input, Button, Table, Card, Typography, Space, message, Tag, Select, DatePicker } from 'antd';
import { SearchOutlined, StockOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title } = Typography;
const { RangePicker } = DatePicker;

const API_BASE = 'http://localhost:8000';

const StockPage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);
  const [quoteData, setQuoteData] = useState(null);
  const [provider, setProvider] = useState('akshare');

  const searchStock = async (values) => {
    setLoading(true);
    try {
      const { keyword } = values;
      const res = await axios.get(`${API_BASE}/api/v1/stocks/search`, {
        params: { keyword, provider }
      });
      if (res.data.success) {
        setData(res.data.data);
        message.success(`找到 ${res.data.count} 条结果`);
      }
    } catch (err) {
      message.error('搜索失败: ' + (err.message || '网络错误'));
    }
    setLoading(false);
  };

  const getQuote = async (symbol) => {
    try {
      const res = await axios.get(`${API_BASE}/api/v1/stocks/quote`, {
        params: { symbol, provider: 'eastmoney' }
      });
      if (res.data.success) {
        setQuoteData(res.data.data);
      }
    } catch (err) {
      message.error('获取行情失败');
    }
  };

  const columns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 100 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 150 },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button type="link" onClick={() => getQuote(record.code)}>
          查看行情
        </Button>
      )
    }
  ];

  return (
    <div>
      <Title level={2}><StockOutlined /> 股票查询</Title>

      <Card title="搜索股票" style={{ marginBottom: 24 }}>
        <Form form={form} layout="inline" onFinish={searchStock}>
          <Form.Item name="keyword" rules={[{ required: true, message: '请输入股票代码或名称' }]}>
            <Input placeholder="输入股票代码或名称，如：茅台、600000" style={{ width: 300 }} prefix={<SearchOutlined />} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              搜索
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {data.length > 0 && (
        <Card title="搜索结果" style={{ marginBottom: 24 }}>
          <Table columns={columns} dataSource={data} rowKey="code" pagination={{ pageSize: 10 }} />
        </Card>
      )}

      {quoteData && (
        <Card title={`${quoteData.name || quoteData.symbol} 实时行情`}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
            <InfoItem label="最新价" value={quoteData.price} color={quoteData.pct_change > 0 ? '#cf1322' : '#3f8600'} />
            <InfoItem label="涨跌幅" value={`${quoteData.pct_change > 0 ? '+' : ''}${quoteData.pct_change?.toFixed(2)}%`} color={quoteData.pct_change > 0 ? '#cf1322' : '#3f8600'} />
            <InfoItem label="涨跌额" value={quoteData.change?.toFixed(2)} />
            <InfoItem label="开盘价" value={quoteData.open} />
            <InfoItem label="最高价" value={quoteData.high} />
            <InfoItem label="最低价" value={quoteData.low} />
            <InfoItem label="成交量" value={formatVolume(quoteData.volume)} />
            <InfoItem label="成交额" value={formatAmount(quoteData.amount)} />
          </div>
        </Card>
      )}
    </div>
  );
};

const InfoItem = ({ label, value, color }) => (
  <div style={{ textAlign: 'center', padding: 16, background: '#f5f5f5', borderRadius: 8 }}>
    <div style={{ color: '#999', fontSize: 12 }}>{label}</div>
    <div style={{ color: color || '#333', fontSize: 20, fontWeight: 'bold', marginTop: 8 }}>
      {value ?? '-'}
    </div>
  </div>
);

const formatVolume = (v) => {
  if (!v) return '-';
  if (v >= 100000000) return (v / 100000000).toFixed(2) + ' 亿';
  if (v >= 10000) return (v / 10000).toFixed(2) + ' 万';
  return v;
};

const formatAmount = (v) => {
  if (!v) return '-';
  if (v >= 100000000) return (v / 100000000).toFixed(2) + ' 亿';
  if (v >= 10000) return (v / 10000).toFixed(2) + ' 万';
  return v;
};

export default StockPage;
