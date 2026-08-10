import React from 'react';
import {
    StockOutlined,
    FundOutlined,
    GlobalOutlined,
    LineChartOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons';

/** Alpha Agent 多市场显示配置 */
export const MARKET_CONFIG: Record<string, {
    label: string;
    icon: React.ReactNode;
    color: string;
    gradient: string;
}> = {
    a_share: {
        label: 'A股',
        icon: <StockOutlined />,
        color: '#ef4444',
        gradient: 'from-red-500 to-orange-500',
    },
    crypto: {
        label: '加密货币',
        icon: <FundOutlined />,
        color: '#f59e0b',
        gradient: 'from-amber-500 to-yellow-500',
    },
    hong_kong: {
        label: '港股',
        icon: <GlobalOutlined />,
        color: '#3b82f6',
        gradient: 'from-blue-500 to-cyan-500',
    },
    us_stock: {
        label: '美股',
        icon: <LineChartOutlined />,
        color: '#10b981',
        gradient: 'from-emerald-500 to-teal-500',
    },
    futures: {
        label: '期货',
        icon: <ThunderboltOutlined />,
        color: '#fa8c16',
        gradient: 'from-orange-500 to-amber-500',
    },
};
