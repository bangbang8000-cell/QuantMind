import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Select, Space, Avatar, Spin, Alert } from 'antd';
import { RobotOutlined, UserOutlined, SendOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title } = Typography;
const { TextArea } = Input;
const { Option } = Select;

const API_BASE = 'http://localhost:8000';

const AIPage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [provider, setProvider] = useState('minimaxi');

  const sendMessage = async (values) => {
    const { message: userMsg } = values;
    if (!userMsg.trim()) return;

    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);

    try {
      const res = await axios.post(`${API_BASE}/api/v1/ai/chat`, {
        message: userMsg,
        provider: provider
      });

      if (res.data.success) {
        setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: '抱歉，AI 助手暂时无法响应。请检查 API 配置或稍后重试。' 
      }]);
    }
    
    setLoading(false);
    form.resetFields();
  };

  const renderMessage = (msg, i) => (
    <div key={i} style={{ 
      display: 'flex', 
      justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
      marginBottom: 16 
    }}>
      <Space align="start">
        {msg.role === 'assistant' && (
          <Avatar icon={<RobotOutlined />} style={{ background: '#1890ff' }} />
        )}
        <div style={{ 
          maxWidth: '70%',
          padding: '12px 16px',
          borderRadius: 12,
          background: msg.role === 'user' ? '#1890ff' : '#f0f0f0',
          color: msg.role === 'user' ? '#fff' : '#333'
        }}>
          {msg.content}
        </div>
        {msg.role === 'user' && (
          <Avatar icon={<UserOutlined />} style={{ background: '#52c41a' }} />
        )}
      </Space>
    </div>
  );

  return (
    <div>
      <Title level={2}><RobotOutlined /> AI 助手</Title>

      <Alert
        message="AI 助手说明"
        description={
          <div>
            <p>支持多个国产大模型：MiniMax、GLM、Qwen、DeepSeek</p>
            <p>功能：财报解读、K线分析、智能选股、量化策略编写</p>
          </div>
        }
        type="info"
        style={{ marginBottom: 24 }}
      />

      <Card 
        title="对话助手"
        extra={
          <Select value={provider} onChange={setProvider} style={{ width: 150 }}>
            <Option value="minimaxi">MiniMax</Option>
            <Option value="zhipuai">GLM (智谱)</Option>
            <Option value="qwen">Qwen (通义)</Option>
            <Option value="deepseek">DeepSeek</Option>
          </Select>
        }
        style={{ marginBottom: 24 }}
      >
        <div style={{ height: 400, overflowY: 'auto', marginBottom: 24 }}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#999', padding: 100 }}>
              开始和 AI 助手对话吧！
            </div>
          ) : (
            messages.map(renderMessage)
          )}
          {loading && (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin tip="AI 思考中..." />
            </div>
          )}
        </div>

        <Form form={form} onFinish={sendMessage}>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="message" rules={[{ required: true, message: '请输入问题' }]} style={{ flex: 1 }}>
              <TextArea 
                placeholder="例如：帮我分析贵州茅台的财务状况" 
                autoSize={{ minRows: 1, maxRows: 4 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    form.submit();
                  }
                }}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />}>
              发送
            </Button>
          </Space.Compact>
        </Form>
      </Card>

      <Card title="快捷问题">
        <Space wrap>
          {[
            '分析贵州茅台的投资价值',
            '解释 MACD 指标如何用于选股',
            '帮我写一个双均线策略的 Python 代码',
            'A 股当前有哪些低估值的股票？',
          ].map((q, i) => (
            <Button key={i} onClick={() => {
              form.setFieldsValue({ message: q });
            }}>
              {q}
            </Button>
          ))}
        </Space>
      </Card>
    </div>
  );
};

export default AIPage;
