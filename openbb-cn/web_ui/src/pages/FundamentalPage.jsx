import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Select, Table, message, Descriptions, Tag } from 'antd';
import { FundOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title } = Typography;
const { Option } = Select;

const API_BASE = 'http://localhost:8000';

const FundamentalPage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [valuation, setValuation] = useState(null);
  const [dividend, setDividend] = useState([]);

  const fetchValuation = async (values) => {
    setLoading(true);
    try {
      const { symbol } = values;
      const res = await axios.get(`${API_BASE}/api/v1/fundamental/valuation`, {
        params: { symbol, provider: 'akshare' }
      });
      
      if (res.data.success && res.data.data) {
        setValuation(res.data.data);
        message.success('获取成功');
      } else {
        message.warning('暂无数据');
      }
    } catch (err) {
      message.error('获取失败: ' + (err.response?.data?.detail || err.message));
    }
    setLoading(false);
  };

  const fetchDividend = async (values) => {
    try {
      const { symbol } = values;
      const res = await axios.get(`${API_BASE}/api/v1/fundamental/dividend`, {
        params: { symbol, provider: 'akshare' }
      });
      
      if (res.data.success) {
        setDividend(res.data.data || []);
      }
    } catch (err) {
      message.error('获取失败');
    }
  };

  const onFinish = (values) => {
    fetchValuation(values);
    fetchDividend(values);
  };

  return (
    <div>
      <Title level={2}><FundOutlined /> 基本面分析</Title>

      <Card title="查询基本面数据" style={{ marginBottom: 24 }}>
        <Form form={form} layout="inline" onFinish={onFinish}>
          <Form.Item name="symbol" label="股票代码" rules={[{ required: true, message: '请输入代码' }]}>
            <Input placeholder="如：000001.SZ" style={{ width: 150 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              查询
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {valuation && (
        <Card title="估值指标" style={{ marginBottom: 24 }}>
          <Descriptions bordered column={3}>
            <Descriptions.Item label="市盈率(TTM)">
              {valuation.pe_ttm ? valuation.pe_ttm.toFixed(2) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="市盈率(LYR)">
              {valuation.pe_lYR ? valuation.pe_lYR.toFixed(2) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="市净率(PB)">
              {valuation.pb ? valuation.pb.toFixed(2) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="市销率(TTM)">
              {valuation.ps_ttm ? valuation.ps_ttm.toFixed(2) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="市现率(PCF)">
              {valuation.pcf ? valuation.pcf.toFixed(2) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="净资产收益率(ROE)">
              {valuation.roe ? `${valuation.roe.toFixed(2)}%` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="毛利率">
              {valuation.gross_margin ? `${valuation.gross_margin.toFixed(2)}%` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="净利率">
              {valuation.net_margin ? `${valuation.net_margin.toFixed(2)}%` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="数据日期">
              {valuation.date || '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card title="估值参考">
        <div style={{ marginBottom: 16 }}>
          <Tag color="green">PE &lt; 15</Tag> 较低（价值股）&nbsp;
          <Tag color="orange">15 &lt; PE &lt; 30</Tag> 适中&nbsp;
          <Tag color="red">PE &gt; 30</Tag> 较高（成长股）
        </div>
        <div>
          <Tag color="green">PB &lt; 2</Tag> 较低&nbsp;
          <Tag color="orange">2 &lt; PB &lt; 5</Tag> 适中&nbsp;
          <Tag color="red">PB &gt; 5</Tag> 较高
        </div>
      </Card>

      {dividend.length > 0 && (
        <Card title="分红送转" style={{ marginTop: 24 }}>
          <Table 
            dataSource={dividend.slice(0, 10)} 
            rowKey="code"
            size="small"
            pagination={false}
            columns={[
              { title: '股票代码', dataIndex: 'code', key: 'code' },
              { title: '股票名称', dataIndex: 'name', key: 'name' },
              { title: '分红金额', dataIndex: 'divi', key: 'divi', render: (v) => v || '-' },
              { title: '送转股数', dataIndex: 'shares', key: 'shares', render: (v) => v || '-' },
            ]}
          />
        </Card>
      )}
    </div>
  );
};

export default FundamentalPage;
