import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Spin, Tag } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { dataDashboardService, RealtimeQuote } from '../services/dataDashboardService';
import { isMarketEnabled } from '../../../config/marketFlags';

interface IndexItem {
    symbol: string;
    name: string;
    market: string;
}

const MARKET_INDICES: Record<string, IndexItem[]> = {
    CN: [
        { symbol: '000001.SH', name: '上证指数', market: 'CN' },
        { symbol: '399001.SZ', name: '深证成指', market: 'CN' },
        { symbol: '399006.SZ', name: '创业板指', market: 'CN' },
    ],
    HK: [
        { symbol: '^HSI', name: '恒生指数', market: 'HK' },
        { symbol: '^HSCE', name: '国企指数', market: 'HK' },
    ],
    US: [
        { symbol: '^DJI', name: '道琼斯', market: 'US' },
        { symbol: '^IXIC', name: '纳斯达克', market: 'US' },
        { symbol: '^GSPC', name: '标普500', market: 'US' },
    ],
    CRYPTO: [
        { symbol: 'BTCUSDT', name: 'BTC/USDT', market: 'CRYPTO' },
        { symbol: 'ETHUSDT', name: 'ETH/USDT', market: 'CRYPTO' },
    ],
    FUTURES: [
        { symbol: 'RB0.CN', name: '螺纹钢主力', market: 'FUTURES' },
        { symbol: 'CL.FUT', name: 'WTI原油', market: 'FUTURES' },
    ],
};

// 屏蔽区块链时移除 CRYPTO 条目
Object.keys(MARKET_INDICES).forEach((k) => {
    if (!isMarketEnabled(k)) {
        delete (MARKET_INDICES as Record<string, IndexItem[]>)[k];
    }
});

const MARKET_LABELS: Record<string, string> = {
    CN: 'A股',
    HK: '港股',
    US: '美股',
    CRYPTO: '区块链',
    FUTURES: '期货',
};

interface MarketOverviewProps {
    market: string;
}

export const MarketOverview: React.FC<MarketOverviewProps> = ({ market }) => {
    const [quotes, setQuotes] = useState<Record<string, RealtimeQuote>>({});
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const indices = MARKET_INDICES[market] || [];
        if (!indices.length) return;

        let cancelled = false;
        const load = () => {
        setLoading(true);
        Promise.allSettled(
            indices.map((idx) =>
                dataDashboardService.getRealtime(market, idx.symbol).then((q) => ({
                    symbol: idx.symbol,
                    quote: q,
                })),
            ),
        )
            .then((results) => {
                const map: Record<string, RealtimeQuote> = {};
                for (const r of results) {
                    if (r.status === 'fulfilled' && r.value.quote) {
                        map[r.value.symbol] = r.value.quote;
                    }
                }
                if (!cancelled) setQuotes(map);
            })
            .finally(() => { if (!cancelled) setLoading(false); });
        };
        load();
        const timer = window.setInterval(load, 15000);
        return () => { cancelled = true; window.clearInterval(timer); };
    }, [market]);

    const indices = MARKET_INDICES[market] || [];

    return (
        <Card size="small" title={`${MARKET_LABELS[market] ?? market}市场概览`}>
            {loading ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                    <Spin size="small" />
                </div>
            ) : (
                <Row gutter={[16, 8]}>
                    {indices.map((idx) => {
                        const q = quotes[idx.symbol];
                        if (!q) {
                            return (
                                <Col key={idx.symbol} xs={24} sm={8}>
                                    <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
                                        <Statistic title={idx.name} value="—" />
                                    </Card>
                                </Col>
                            );
                        }
                        const last = q.last ?? q.open ?? 0;
                        const preClose = q.pre_close ?? 0;
                        const change = preClose ? last - preClose : 0;
                        const pct = preClose ? (change / preClose) * 100 : 0;
                        const isUp = change >= 0;

                        return (
                            <Col key={idx.symbol} xs={24} sm={8}>
                                <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
                                    <Statistic
                                        title={idx.name}
                                        value={last}
                                        precision={2}
                                        valueStyle={{ color: isUp ? '#ef4444' : '#10b981', fontSize: 20 }}
                                        prefix={isUp ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                                        suffix={
                                            <span style={{ fontSize: 12, color: isUp ? '#ef4444' : '#10b981' }}>
                                                {isUp ? '+' : ''}
                                                {pct.toFixed(2)}%
                                            </span>
                                        }
                                    />
                                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                                        涨跌: {isUp ? '+' : ''}
                                        {change.toFixed(2)}
                                    </div>
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            )}
        </Card>
    );
};
