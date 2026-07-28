import React, { useEffect, useState, useCallback } from 'react';
import {
    Card, Button, Space, Tag, Descriptions, Progress, Input, Select,
    Table, message, Typography, Alert, Statistic, Row, Col, Spin, Divider,
    Radio,
} from 'antd';
import {
    CloudServerOutlined, ApiOutlined, DatabaseOutlined,
    CheckCircleFilled, CloseCircleFilled, ExclamationCircleFilled,
    SearchOutlined, ReloadOutlined, StockOutlined, CalendarOutlined,
    SyncOutlined, CloudSyncOutlined,
} from '@ant-design/icons';
import { dataPlatformService } from '../services/dataPlatformService';

const { Title, Text } = Typography;

interface QuantDBInfo {
    installed: boolean;
    api_key_configured: boolean;
    connected: boolean;
    version?: string;
    account?: { username: string; email: string };
    usage?: {
        used_gb: number;
        limit_gb: number;
        remaining_gb: number;
        credit_gb?: number;
        subscription?: { status: string };
    };
    error?: string;
}

export const AdminQuantDBPanel: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [info, setInfo] = useState<QuantDBInfo | null>(null);
    const [timestamp, setTimestamp] = useState('');

    // K线查询
    const [klineSymbol, setKlineSymbol] = useState('600519.SH');
    const [klineAdj, setKlineAdj] = useState('forward');
    const [klineStart, setKlineStart] = useState('');
    const [klineEnd, setKlineEnd] = useState('');
    const [klineLoading, setKlineLoading] = useState(false);
    const [klineData, setKlineData] = useState<any[]>([]);
    const [klineColumns, setKlineColumns] = useState<string[]>([]);
    const [klineTotal, setKlineTotal] = useState(0);

    // 股票搜索
    const [stockKeyword, setStockKeyword] = useState('');
    const [stockLoading, setStockLoading] = useState(false);
    const [stockData, setStockData] = useState<any[]>([]);
    const [stockColumns, setStockColumns] = useState<string[]>([]);

    // 数据同步
    const [syncMode, setSyncMode] = useState<'kline' | 'calendar' | 'ai_factors' | 'all'>('kline');
    const [syncRunning, setSyncRunning] = useState(false);
    const [syncStatus, setSyncStatus] = useState<any>(null);

    const loadInfo = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await dataPlatformService.getQuantDBInfo();
            setInfo(resp.quantdb);
            setTimestamp(resp.timestamp);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '未知错误';
            message.error(`获取 QuantDB 状态失败: ${msg}`);
        } finally {
            setLoading(false);
        }
    }, []);

    const loadSyncStatus = useCallback(async () => {
        try {
            const resp = await dataPlatformService.getQuantDBSyncStatus();
            setSyncStatus(resp.status);
        } catch { /* ignore */ }
    }, []);

    useEffect(() => { loadInfo(); loadSyncStatus(); }, [loadInfo, loadSyncStatus]);

    const queryKline = async () => {
        if (!klineSymbol.trim()) { message.warning('请输入股票代码'); return; }
        setKlineLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBKline({
                symbol: klineSymbol.trim(),
                adj_type: klineAdj,
                start_date: klineStart || undefined,
                end_date: klineEnd || undefined,
            });
            setKlineData(resp.data || []);
            setKlineColumns(resp.columns || []);
            setKlineTotal(resp.rows || 0);
            message.success(`查询成功，共 ${resp.rows} 条记录`);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '未知错误';
            message.error(`K线查询失败: ${msg}`);
        } finally {
            setKlineLoading(false);
        }
    };

    const searchStocks = async () => {
        setStockLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBStockList({
                keyword: stockKeyword || undefined,
                limit: 100,
            });
            setStockData(resp.data || []);
            setStockColumns(resp.columns || []);
            message.success(`查询成功，共 ${resp.rows} 条`);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '未知错误';
            message.error(`股票搜索失败: ${msg}`);
        } finally {
            setStockLoading(false);
        }
    };

    const triggerSync = async () => {
        setSyncRunning(true);
        try {
            await dataPlatformService.syncQuantDBData({
                mode: syncMode,
                incremental: true,
            });
            message.success(`${syncMode === 'kline' ? 'K线' : syncMode === 'calendar' ? '日历' : syncMode === 'ai_factors' ? 'AI因子' : '全量'}同步已启动（后台运行）`);
            setTimeout(() => { loadSyncStatus(); }, 5000);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '未知错误';
            message.error(`同步启动失败: ${msg}`);
        } finally {
            setSyncRunning(false);
        }
    };

    const usagePercent = info?.usage
        ? Math.round((info.usage.used_gb / info.usage.limit_gb) * 100)
        : 0;

    const statusColor = info?.connected
        ? '#52c41a'
        : info?.api_key_configured
            ? '#faad14'
            : '#ff4d4f';

    const statusText = info?.connected
        ? '已连接'
        : info?.api_key_configured
            ? '已配置但未连接'
            : info?.installed
                ? 'SDK 已安装，未配置 Key'
                : '未安装';

    return (
        <div className="space-y-4">
            {/* 状态卡片 */}
            <Card
                title={
                    <Space>
                        <CloudServerOutlined />
                        <span>QuantDB SDK 数据源</span>
                        <Tag color={statusColor}>{statusText}</Tag>
                    </Space>
                }
                extra={
                    <Button icon={<ReloadOutlined />} onClick={loadInfo} loading={loading}>
                        刷新
                    </Button>
                }
            >
                {info?.error && (
                    <Alert type="error" message={info.error} className="mb-4" showIcon />
                )}

                <Row gutter={16}>
                    <Col span={6}>
                        <Statistic
                            title="SDK 状态"
                            value={info?.installed ? '已安装' : '未安装'}
                            prefix={info?.installed ? <CheckCircleFilled style={{ color: '#52c41a' }} /> : <CloseCircleFilled style={{ color: '#ff4d4f' }} />}
                            valueStyle={{ fontSize: 16 }}
                        />
                        {info?.version && <Text type="secondary" className="text-xs">v{info.version}</Text>}
                    </Col>
                    <Col span={6}>
                        <Statistic
                            title="API Key"
                            value={info?.api_key_configured ? '已配置' : '未配置'}
                            prefix={<ApiOutlined />}
                            valueStyle={{ fontSize: 16, color: info?.api_key_configured ? '#52c41a' : '#ff4d4f' }}
                        />
                    </Col>
                    <Col span={6}>
                        <Statistic
                            title="已用流量"
                            value={info?.usage?.used_gb?.toFixed(2) ?? '-'}
                            suffix="GB"
                            prefix={<DatabaseOutlined />}
                            valueStyle={{ fontSize: 16 }}
                        />
                    </Col>
                    <Col span={6}>
                        <Statistic
                            title="剩余流量"
                            value={info?.usage?.remaining_gb?.toFixed(2) ?? '-'}
                            suffix="GB"
                            valueStyle={{ fontSize: 16, color: (info?.usage?.remaining_gb ?? 0) < 5 ? '#ff4d4f' : '#52c41a' }}
                        />
                    </Col>
                </Row>

                {info?.usage && (
                    <div className="mt-4">
                        <Progress
                            percent={usagePercent}
                            status={usagePercent > 90 ? 'exception' : usagePercent > 70 ? 'active' : 'normal'}
                            format={() => `${info.usage!.used_gb.toFixed(1)} / ${info.usage!.limit_gb} GB`}
                        />
                        <div className="flex gap-4 mt-2">
                            {info.usage.subscription && (
                                <Tag color="blue">订阅: {info.usage.subscription.status}</Tag>
                            )}
                            {info.usage.credit_gb !== undefined && info.usage.credit_gb > 0 && (
                                <Tag color="green">赠送: {info.usage.credit_gb} GB</Tag>
                            )}
                        </div>
                    </div>
                )}

                {info?.account && (
                    <Descriptions size="small" column={2} className="mt-4">
                        <Descriptions.Item label="用户名">{info.account.username}</Descriptions.Item>
                        <Descriptions.Item label="邮箱">{info.account.email}</Descriptions.Item>
                    </Descriptions>
                )}

                <div className="mt-4 p-3 bg-gray-50 rounded text-xs text-gray-500">
                    <div className="font-medium text-gray-700 mb-1">QuantDB SDK 说明</div>
                    <ul className="list-disc pl-4 space-y-1">
                        <li>付费 CDN 数据源，Parquet 格式分发，315 维 AI/ML 因子训练集</li>
                        <li>支持前/后复权 K 线、Tick 逐笔、财报、估值、交易日历</li>
                        <li>环境变量配置：<code className="bg-gray-200 px-1 rounded">QUANTDB_API_KEY</code></li>
                        <li>安装：<code className="bg-gray-200 px-1 rounded">pip install quantdb-sdk</code></li>
                    </ul>
                </div>
            </Card>

            {/* K线查询 */}
            <Card
                title={<Space><StockOutlined />K 线数据查询</Space>}
                size="small"
            >
                <Space wrap className="mb-4">
                    <Input
                        placeholder="股票代码 (如 600519.SH / SH600036)"
                        value={klineSymbol}
                        onChange={e => setKlineSymbol(e.target.value)}
                        style={{ width: 200 }}
                        onPressEnter={queryKline}
                    />
                    <Select value={klineAdj} onChange={setKlineAdj} style={{ width: 120 }}>
                        <Select.Option value="forward">前复权</Select.Option>
                        <Select.Option value="backward">后复权</Select.Option>
                        <Select.Option value="unadjusted">不复权</Select.Option>
                    </Select>
                    <Input
                        placeholder="开始日期 (可选)"
                        value={klineStart}
                        onChange={e => setKlineStart(e.target.value)}
                        style={{ width: 140 }}
                    />
                    <Input
                        placeholder="结束日期 (可选)"
                        value={klineEnd}
                        onChange={e => setKlineEnd(e.target.value)}
                        style={{ width: 140 }}
                    />
                    <Button
                        type="primary"
                        icon={<SearchOutlined />}
                        onClick={queryKline}
                        loading={klineLoading}
                        disabled={!info?.connected}
                    >
                        查询
                    </Button>
                    {klineTotal > 0 && <Text type="secondary">共 {klineTotal} 条</Text>}
                </Space>
                {klineData.length > 0 && (
                    <Table
                        dataSource={klineData}
                        columns={klineColumns.slice(0, 10).map(c => ({
                            title: c,
                            dataIndex: c,
                            key: c,
                            width: 130,
                            ellipsis: true,
                        }))}
                        rowKey={(_, i) => String(i)}
                        size="small"
                        pagination={{ pageSize: 10, size: 'small' }}
                        scroll={{ x: 'max-content' }}
                    />
                )}
            </Card>

            {/* 数据同步到本地 */}
            <Card
                title={<Space><CloudSyncOutlined />数据同步到本地</Space>}
                size="small"
                extra={
                    <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={loadSyncStatus}
                    >
                        刷新状态
                    </Button>
                }
            >
                <Alert
                    type="info"
                    message="将 QuantDB 付费数据同步到本地 PostgreSQL + Parquet，供训练和回测使用。同步在后台线程执行，不会阻塞服务。"
                    className="mb-4"
                    showIcon
                />
                <Space direction="vertical" className="w-full">
                    <Radio.Group value={syncMode} onChange={e => setSyncMode(e.target.value)}>
                        <Radio.Button value="kline">K线日线</Radio.Button>
                        <Radio.Button value="calendar">交易日历</Radio.Button>
                        <Radio.Button value="ai_factors">AI因子</Radio.Button>
                        <Radio.Button value="all">全量同步</Radio.Button>
                    </Radio.Group>
                    <Button
                        type="primary"
                        icon={<SyncOutlined spin={syncRunning} />}
                        onClick={triggerSync}
                        loading={syncRunning}
                        disabled={!info?.connected}
                        block
                    >
                        {syncRunning ? '同步进行中...' : `同步 ${syncMode === 'kline' ? 'K线' : syncMode === 'calendar' ? '日历' : syncMode === 'ai_factors' ? 'AI因子' : '全量'} 到本地`}
                    </Button>
                </Space>
                {syncStatus && (
                    <div className="mt-4 p-3 bg-gray-50 rounded text-sm">
                        <div className="font-medium mb-2">本地数据状态</div>
                        <Space direction="vertical" size="small">
                            <Tag color={syncStatus.quantdb_cache?.calendar_cached ? 'green' : 'default'}>
                                交易日历: {syncStatus.quantdb_cache?.calendar_cached ? '已缓存' : '未缓存'}
                            </Tag>
                            <Tag color={syncStatus.quantdb_factors?.files > 0 ? 'green' : 'default'}>
                                AI因子: {syncStatus.quantdb_factors?.files || 0} 文件
                            </Tag>
                            <Tag color={syncStatus.quantdb_valuation?.files > 0 ? 'green' : 'default'}>
                                估值: {syncStatus.quantdb_valuation?.files || 0} 文件
                            </Tag>
                        </Space>
                    </div>
                )}
            </Card>

            {/* 股票搜索 */}
            <Card
                title={<Space><SearchOutlined />股票列表搜索</Space>}
                size="small"
            >
                <Space className="mb-4">
                    <Input
                        placeholder="关键词 (如 贵州茅台)"
                        value={stockKeyword}
                        onChange={e => setStockKeyword(e.target.value)}
                        style={{ width: 240 }}
                        onPressEnter={searchStocks}
                    />
                    <Button
                        type="primary"
                        icon={<SearchOutlined />}
                        onClick={searchStocks}
                        loading={stockLoading}
                        disabled={!info?.connected}
                    >
                        搜索
                    </Button>
                </Space>
                {stockData.length > 0 && (
                    <Table
                        dataSource={stockData}
                        columns={stockColumns.slice(0, 8).map(c => ({
                            title: c,
                            dataIndex: c,
                            key: c,
                            width: 130,
                            ellipsis: true,
                        }))}
                        rowKey={(_, i) => String(i)}
                        size="small"
                        pagination={{ pageSize: 10, size: 'small' }}
                        scroll={{ x: 'max-content' }}
                    />
                )}
            </Card>
        </div>
    );
};

export default AdminQuantDBPanel;
