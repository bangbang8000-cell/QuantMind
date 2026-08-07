import React, { useState } from 'react';
import { Layout, Menu, Typography, ConfigProvider } from 'antd';
import {
  BarChartOutlined,
  StockOutlined,
  LineChartOutlined,
  FundOutlined,
  RobotOutlined,
  SearchOutlined,
  HomeOutlined,
} from '@ant-design/icons';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import StockPage from './pages/StockPage';
import TechnicalPage from './pages/TechnicalPage';
import FundamentalPage from './pages/FundamentalPage';
import AIPage from './pages/AIPage';
import MarketPage from './pages/MarketPage';
import './App.css';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const AppContent = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: <Link to="/">首页</Link> },
    { key: '/stock', icon: <StockOutlined />, label: <Link to="/stock">股票查询</Link> },
    { key: '/technical', icon: <LineChartOutlined />, label: <Link to="/technical">技术分析</Link> },
    { key: '/fundamental', icon: <FundOutlined />, label: <Link to="/fundamental">基本面</Link> },
    { key: '/market', icon: <BarChartOutlined />, label: <Link to="/market">市场概览</Link> },
    { key: '/ai', icon: <RobotOutlined />, label: <Link to="/ai">AI 助手</Link> },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={220}
      >
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: collapsed ? 16 : 18, fontWeight: 'bold' }}>
          {collapsed ? 'OBB' : 'OPENBB-CN'}
        </div>
        <Menu theme="dark" selectedKeys={[location.pathname]} mode="inline" items={menuItems} />
      </Sider>
      <Layout>
        <Header style={{ background: '#001529', padding: '0 24px', display: 'flex', alignItems: 'center' }}>
          <Title level={4} style={{ color: '#fff', margin: 0 }}>
            面向中国市场的开源金融数据平台
          </Title>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/stock" element={<StockPage />} />
            <Route path="/technical" element={<TechnicalPage />} />
            <Route path="/fundamental" element={<FundamentalPage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/ai" element={<AIPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

const Home = () => {
  const features = [
    { title: '股票数据', desc: '支持 AkShare、Tushare、东方财富等多个数据源', icon: <StockOutlined /> },
    { title: '技术分析', desc: 'MA、MACD、KDJ、RSI、布林带等技术指标', icon: <LineChartOutlined /> },
    { title: '基本面分析', desc: '财务报表、估值数据、分红送转', icon: <FundOutlined /> },
    { title: 'AI 助手', desc: '接入 MiniMax、GLM、Qwen、DeepSeek 等大模型', icon: <RobotOutlined /> },
  ];

  return (
    <div>
      <Title level={2}>欢迎使用 OPENBB-CN</Title>
      <p style={{ fontSize: 16, color: '#666', marginBottom: 32 }}>
        面向中国个人投资者的开源金融数据平台，基于 OpenBB 架构扩展
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 24 }}>
        {features.map((f, i) => (
          <div key={i} style={{ padding: 24, border: '1px solid #e8e8e8', borderRadius: 8 }}>
            <div style={{ fontSize: 32, color: '#1890ff', marginBottom: 16 }}>{f.icon}</div>
            <Title level={4}>{f.title}</Title>
            <p style={{ color: '#666' }}>{f.desc}</p>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 48 }}>
        <Title level={4}>快速开始</Title>
        <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8 }}>
{`# Python SDK 使用
from openbb_core import OpenBB

obb = OpenBB()

# 获取股票数据
obb.stocks.historical("000001.SZ")
obb.stocks.quote("600000", provider="eastmoney")

# 技术分析
obb.technical.ma("000001.SZ", period=20)
obb.technical.macd("000001.SZ")

# AI 助手
obb.ai.set_provider("minimaxi", api_key="your-key")
obb.ai.chat("分析贵州茅台")`}
        </pre>
      </div>
    </div>
  );
};

const App = () => (
  <ConfigProvider
    theme={{
      token: { colorPrimary: '#1890ff' },
    }}
  >
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
