import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Select, Table, message, Space, Tag } from 'antd';
import { LineChartOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title } = Typography;
const { Option } = Select;

const API_BASE = 'http://localhost:8000';

const TechnicalPage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [indicator, setIndicator] = useState('ma');
  const [data, setData] = useState([]);

  const fetchIndicator = async (values) => {
    setLoading(true);
    try {
      const { symbol, period } = values;
      let endpoint = `${API_BASE}/api/v1/technical/${indicator}`;
      let params = { symbol, provider: 'akshare' };
      
      if (indicator === 'ma' || indicator === 'rsi') {
        params.period = period || 20;
      }

      const res = await axios.get(endpoint, { params });
      
      if (res.data.success) {
        setData(res.data.data || []);
        message.success('获取成功');
      }
    } catch (err) {
      message.error('获取失败: ' + (err.response?.data?.detail || err.message));
    }
    setLoading(false);
  };

  const getColumns = () => {
    if (!data.length) return [];
    const cols = [
      { title: '日期', dataIndex: 'date', key: 'date', width: 120 }
    ];
    
    Object.keys(data[0]).forEach(key => {
      if (key !== 'date' && key !== 'symbol') {
        cols.push({
          title: key.toUpperCase(),
          dataIndex: key,
          key: key,
          render: (v) => v?.toFixed(4) ?? '-'
        });
      }
    });
    return cols;
  };

  return (
    <div>
      <Title level={2}><LineChartOutlined /> 技术分析</Title>

      <Card title="指标计算" style={{ marginBottom: 24 }}>
        <Form form={form} layout="inline" onFinish={fetchIndicator}>
          <Form.Item name="indicator" label="指标类型" initialValue="ma">
            <Select style={{ width: 150 }} onChange={setIndicator}>
              <Option value="ma">移动平均线 MA</Option>
              <Option value="macd">MACD</Option>
              <Option value="kdj">KDJ</Option>
              <Option value="rsi">RSI</Option>
            </Select>
          </Form.Item>
          <Form.Item name="symbol" label="股票代码" rules={[{ required: true, message: '请输入代码' }]}>
            <Input placeholder="如：000001.SZ" style={{ width: 150 }} />
          </Form.Item>
          {(indicator === 'ma' || indicator === 'rsi') && (
            <Form.Item name="period" label="周期" initialValue={20}>
              <Input type="number" style={{ width: 80 }} />
            </Form.Item>
          )}
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              计算
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {data.length > 0 && (
        <Card title={`${form.getFieldValue('symbol')} - ${indicator.toUpperCase()} 技术指标`}>
          <Table 
            columns={getColumns()} 
            dataSource={data.slice(0, 30).reverse()} 
            rowKey="date"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </Card>
      )}

      <Card title="指标说明" style={{ marginTop: 24 }}>
        <Space direction="vertical">
          <Tag color="blue">MA (移动平均线)</Tag>
          <p>MA是最常用的技术指标之一，通过将一定时期内的证券价格加以平均得出，可消除价格波动。</p>
          
          <Tag color="green">MACD</Tag>
          <p>指数平滑异同移动平均线，由DIF、DEA和MACD柱状图组成，用于判断买卖时机。</p>
          
          <Tag color="orange">KDJ</Tag>
          <p>随机指标，由K、D、J三条线组成，用于判断市场的超买超卖状态。</p>
          
          <Tag color="red">RSI</Tag>
          <p>相对强弱指数，衡量价格涨跌的相对强弱，一般在70以上为超买，30以下为超卖。</p>
        </Space>
      </Card>
    </div>
  );
};

export default TechnicalPage;
