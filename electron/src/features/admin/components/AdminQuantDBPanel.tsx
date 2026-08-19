import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Alert, Button, Card, Checkbox, Col, Descriptions, Input, Progress, Row, Select, Space,
    Statistic, Table, Tabs, Tag, Typography, message,
} from 'antd';
import {
    ApiOutlined, CalendarOutlined, CheckCircleFilled, CloseCircleFilled,
    CloudServerOutlined, DatabaseOutlined, FieldTimeOutlined, FileSearchOutlined,
    KeyOutlined, ReloadOutlined, SearchOutlined, StockOutlined,
} from '@ant-design/icons';
import { dataPlatformService, QuantDBDataset } from '../services/dataPlatformService';
import { QuantDBCatalogPanel } from './quantdb/QuantDBCatalogPanel';
import { QuantDBPreviewDrawer } from './quantdb/QuantDBPreviewDrawer';
import { describeError } from './quantdb/utils';
import { SyncSchedulePanel } from './data-management/SyncSchedulePanel';

const { Text } = Typography;

const USAGE_WARN_PERCENT = 70;
const USAGE_DANGER_PERCENT = 90;
const LOW_QUOTA_GB = 5;

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
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [info, setInfo] = useState<QuantDBInfo | null>(null);
    const [previewDataset, setPreviewDataset] = useState<QuantDBDataset | null>(null);
    const [sources, setSources] = useState<Array<{ source: string; label: string; enabled: boolean }>>([]);
    const [sourcesLoading, setSourcesLoading] = useState(false);

    const loadInfo = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await dataPlatformService.getQuantDBInfo();
            setInfo(resp.quantdb);
        } catch (error: unknown) {
            message.error(`获取 QuantDB 状态失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    }, []);

    const loadSources = useCallback(async () => {
        setSourcesLoading(true);
        try {
            const resp = await dataPlatformService.getMarketDataSources('quantdb');
            setSources(resp.sources);
        } catch (error: unknown) {
            message.error(`加载数据源配置失败: ${describeError(error)}`);
        } finally {
            setSourcesLoading(false);
        }
    }, []);

    const saveSources = useCallback(async (source: string, enabled: boolean) => {
        const next = sources.map((s) => (s.source === source ? { ...s, enabled } : s));
        setSources(next);
        try {
            const payload: Record<string, boolean> = {};
            next.forEach((s) => { payload[s.source] = s.enabled; });
            await dataPlatformService.saveMarketDataSources('quantdb', payload);
            message.success('A股数据源配置已保存');
        } catch (error: unknown) {
            message.error(`保存数据源配置失败: ${describeError(error)}`);
            loadSources();
        }
    }, [sources, loadSources]);

    useEffect(() => {
        loadSources();
    }, [loadSources]);

    useEffect(() => {
        loadInfo();
    }, [loadInfo]);

    const usagePercent = info?.usage && info.usage.limit_gb > 0
        ? Math.round((info.usage.used_gb / info.usage.limit_gb) * 100)
        : 0;

    const statusColor = info?.connected
        ? '#52c41a'
        : info?.api_key_configured ? '#faad14' : '#ff4d4f';

    const statusText = info?.connected
        ? '已连接'
        : info?.api_key_configured
            ? '已配置但未连接'
            : info?.installed ? 'SDK 已安装，未配置 Key' : '未安装';

    return (
        <div className="space-y-4">
            <Card
                title={
                    <Space>
                        <CloudServerOutlined />
                        <span>QuantDB A股 数据源</span>
                        <Tag color={statusColor}>{statusText}</Tag>
                    </Space>
                }
                extra={
                    <Button icon={<ReloadOutlined />} onClick={loadInfo} loading={loading}>
                        刷新
                    </Button>
                }
            >
                {info?.error && <Alert type="error" message={info.error} className="mb-4" showIcon />}

                <Row gutter={16}>
                    <Col span={6}>
                        <Statistic
                            title="SDK 状态"
                            value={info?.installed ? '已安装' : '未安装'}
                            prefix={info?.installed
                                ? <CheckCircleFilled style={{ color: '#52c41a' }} />
                                : <CloseCircleFilled style={{ color: '#ff4d4f' }} />}
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
                            valueStyle={{
                                fontSize: 16,
                                color: (info?.usage?.remaining_gb ?? 0) < LOW_QUOTA_GB ? '#ff4d4f' : '#52c41a',
                            }}
                        />
                    </Col>
                </Row>

                {info?.usage && (
                    <div className="mt-4">
                        <Progress
                            percent={usagePercent}
                            status={usagePercent > USAGE_DANGER_PERCENT
                                ? 'exception'
                                : usagePercent > USAGE_WARN_PERCENT ? 'active' : 'normal'}
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
            </Card>

            {/* 数据源勾选配置 */}
            <div className="p-3 bg-gray-50 rounded">
                <Space direction="vertical" className="w-full" size="small">
                    <Space>
                        <DatabaseOutlined />
                        <Text strong>数据源</Text>
                        <Text type="secondary" className="text-xs">默认 QuantDB A股/akshare/北向/南向；雅虎默认关闭不勾选</Text>
                    </Space>
                    <Space wrap size="small">
                        {sources.map((s) => (
                            <Checkbox
                                key={s.source}
                                checked={s.enabled}
                                disabled={sourcesLoading}
                                onChange={(e) => saveSources(s.source, e.target.checked)}
                            >
                                <Text className="text-xs">{s.label}</Text>
                                <Text type="secondary" className="text-xs">({s.source})</Text>
                            </Checkbox>
                        ))}
                    </Space>
                </Space>
            </div>

            {/* API Key 状态与个人中心设置入口 */}
            <div className="flex items-center justify-between bg-white border border-slate-200 rounded-xl px-4 py-2.5 shadow-2xs">
                <Space size="middle">
                    <KeyOutlined className="text-blue-500" />
                    <Text className="text-xs font-semibold">API Key 授权状态:</Text>
                    <Tag
                        color={info?.api_key_configured ? 'green' : 'red'}
                        icon={<ApiOutlined />}
                        className="m-0"
                    >
                        {info?.api_key_configured ? '已授权配置' : '未配置密钥'}
                    </Tag>
                    {info?.account?.username && (
                        <Text type="secondary" className="text-xs">
                            账户: <Text code>{info.account.username}</Text>
                        </Text>
                    )}
                </Space>
                <Button
                    type="link"
                    size="small"
                    className="text-xs text-blue-600 hover:text-blue-700 p-0 font-medium"
                    onClick={() => navigate('/user-center?tab=quantdb-key')}
                >
                    前往「个人中心」绑定或更新密钥 →
                </Button>
            </div>

            <SyncSchedulePanel market="A" defaultDays={5} />

            <QuantDBCatalogPanel
                connected={Boolean(info?.connected)}
                onPreview={setPreviewDataset}
            />

            <Card size="small">
                <Tabs
                    items={[
                        {
                            key: 'kline',
                            label: <span><StockOutlined className="mr-1" />K线查询</span>,
                            children: <KlineQueryTab connected={Boolean(info?.connected)} />,
                        },
                        {
                            key: 'tick',
                            label: <span><FieldTimeOutlined className="mr-1" />Tick查询</span>,
                            children: <TickQueryTab connected={Boolean(info?.connected)} />,
                        },
                        {
                            key: 'stocks',
                            label: <span><SearchOutlined className="mr-1" />股票列表</span>,
                            children: <StockListTab connected={Boolean(info?.connected)} />,
                        },
                        {
                            key: 'calendar',
                            label: <span><CalendarOutlined className="mr-1" />交易日历</span>,
                            children: <CalendarTab connected={Boolean(info?.connected)} />,
                        },
                        {
                            key: 'manifest',
                            label: <span><FileSearchOutlined className="mr-1" />文件清单</span>,
                            children: <ManifestTab connected={Boolean(info?.connected)} />,
                        },
                    ]}
                />
            </Card>

            <QuantDBPreviewDrawer
                dataset={previewDataset}
                onClose={() => setPreviewDataset(null)}
            />
        </div>
    );
};

/** 远端查询结果的通用表格，列由响应动态决定。 */
function ResultTable({ columns, data }: { columns: string[]; data: any[] }) {
    if (data.length === 0) return null;
    return (
        <Table
            dataSource={data}
            columns={columns.map((c) => ({
                title: c,
                dataIndex: c,
                key: c,
                width: 140,
                ellipsis: true,
            }))}
            rowKey={(_, index) => String(index)}
            size="small"
            pagination={{ pageSize: 10, size: 'small' }}
            scroll={{ x: 'max-content' }}
        />
    );
}

function KlineQueryTab({ connected }: { connected: boolean }) {
    const [symbol, setSymbol] = useState('600519.SH');
    const [adjType, setAdjType] = useState('forward');
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ rows: number; columns: string[]; data: any[] } | null>(null);

    const query = async () => {
        if (!symbol.trim()) {
            message.warning('请输入股票代码');
            return;
        }
        setLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBKline({
                symbol: symbol.trim(),
                adj_type: adjType,
                start_date: startDate || undefined,
                end_date: endDate || undefined,
            });
            setResult(resp);
            message.success(`查询成功，共 ${resp.rows} 条记录`);
        } catch (error: unknown) {
            message.error(`K线查询失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Space direction="vertical" className="w-full">
            <Alert
                type="warning"
                showIcon
                message="远端 K 线查询会下载 parquet 切片，消耗流量配额。本地已同步的数据请用上方「预览」。"
            />
            <Space wrap>
                <Input
                    placeholder="股票代码 (如 600519.SH / SH600036)"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    style={{ width: 220 }}
                    onPressEnter={query}
                />
                <Select value={adjType} onChange={setAdjType} style={{ width: 120 }}>
                    <Select.Option value="forward">前复权</Select.Option>
                    <Select.Option value="backward">后复权</Select.Option>
                    <Select.Option value="unadjusted">不复权</Select.Option>
                </Select>
                <Input
                    placeholder="开始日期 YYYY-MM-DD"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    style={{ width: 170 }}
                />
                <Input
                    placeholder="结束日期 YYYY-MM-DD"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    style={{ width: 170 }}
                />
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={query}
                    loading={loading}
                    disabled={!connected}
                >
                    查询
                </Button>
                {result && <Text type="secondary">共 {result.rows} 条</Text>}
            </Space>
            {result && <ResultTable columns={result.columns} data={result.data} />}
        </Space>
    );
}

function StockListTab({ connected }: { connected: boolean }) {
    const [keyword, setKeyword] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ rows: number; columns: string[]; data: any[] } | null>(null);

    const search = async () => {
        setLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBStockList({
                keyword: keyword || undefined,
                limit: 200,
            });
            setResult(resp);
            message.success(`查询成功，共 ${resp.rows} 条`);
        } catch (error: unknown) {
            message.error(`股票搜索失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Space direction="vertical" className="w-full">
            <Space>
                <Input
                    placeholder="关键词 (如 贵州茅台)"
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    style={{ width: 240 }}
                    onPressEnter={search}
                />
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={search}
                    loading={loading}
                    disabled={!connected}
                >
                    搜索
                </Button>
                {result && <Text type="secondary">共 {result.rows} 条</Text>}
            </Space>
            {result && <ResultTable columns={result.columns} data={result.data} />}
        </Space>
    );
}

function CalendarTab({ connected }: { connected: boolean }) {
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ rows: number; columns: string[]; data: any[] } | null>(null);

    const query = async () => {
        if (!startDate.trim() || !endDate.trim()) {
            message.warning('请填写开始与结束日期');
            return;
        }
        setLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBCalendar(startDate.trim(), endDate.trim());
            setResult(resp);
            message.success(`查询成功，共 ${resp.rows} 个交易日`);
        } catch (error: unknown) {
            message.error(`日历查询失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Space direction="vertical" className="w-full">
            <Space wrap>
                <Input
                    placeholder="开始日期 YYYY-MM-DD"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    style={{ width: 180 }}
                />
                <Input
                    placeholder="结束日期 YYYY-MM-DD"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    style={{ width: 180 }}
                    onPressEnter={query}
                />
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={query}
                    loading={loading}
                    disabled={!connected}
                >
                    查询
                </Button>
                {result && <Text type="secondary">共 {result.rows} 个交易日</Text>}
            </Space>
            {result && <ResultTable columns={result.columns} data={result.data} />}
        </Space>
    );
}

function TickQueryTab({ connected }: { connected: boolean }) {
    const [symbol, setSymbol] = useState('600519.SH');
    const [tradeDate, setTradeDate] = useState('');
    const [startTs, setStartTs] = useState('');
    const [endTs, setEndTs] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ rows: number; columns: string[]; data: any[] } | null>(null);

    const query = async () => {
        if (!symbol.trim() || !tradeDate.trim()) {
            message.warning('请输入股票代码和交易日期');
            return;
        }
        setLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBTick({
                symbol: symbol.trim(),
                trade_date: tradeDate.trim(),
                start_ts: startTs || undefined,
                end_ts: endTs || undefined,
            });
            setResult(resp);
            message.success(`查询成功，共 ${resp.rows} 条 Tick 记录`);
        } catch (error: unknown) {
            message.error(`Tick 查询失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Space direction="vertical" className="w-full">
            <Alert
                type="warning"
                showIcon
                message="Tick 分笔数据体积大，查询会消耗较多流量配额。单只股票单日约 3~5 万条记录。"
            />
            <Space wrap>
                <Input
                    placeholder="股票代码 (如 600519.SH)"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    style={{ width: 180 }}
                />
                <Input
                    placeholder="交易日期 YYYY-MM-DD"
                    value={tradeDate}
                    onChange={(e) => setTradeDate(e.target.value)}
                    style={{ width: 170 }}
                />
                <Input
                    placeholder="开始时间 HH:MM:SS (可选)"
                    value={startTs}
                    onChange={(e) => setStartTs(e.target.value)}
                    style={{ width: 180 }}
                />
                <Input
                    placeholder="结束时间 HH:MM:SS (可选)"
                    value={endTs}
                    onChange={(e) => setEndTs(e.target.value)}
                    style={{ width: 180 }}
                    onPressEnter={query}
                />
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={query}
                    loading={loading}
                    disabled={!connected}
                >
                    查询
                </Button>
                {result && <Text type="secondary">共 {result.rows} 条</Text>}
            </Space>
            {result && <ResultTable columns={result.columns} data={result.data} />}
        </Space>
    );
}

function ManifestTab({ connected }: { connected: boolean }) {
    const [categoryId, setCategoryId] = useState('1');
    const [subCategory, setSubCategory] = useState('daily_forward');
    const [tradeDate, setTradeDate] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ files: any[]; count: number; total?: number; truncated?: boolean } | null>(null);

    const query = async () => {
        if (!subCategory.trim()) {
            message.warning('请输入 sub_category');
            return;
        }
        setLoading(true);
        try {
            const resp = await dataPlatformService.queryQuantDBManifest({
                category_id: categoryId,
                sub_category: subCategory.trim(),
                trade_date: tradeDate || undefined,
            });
            setResult(resp);
            message.success(`共 ${resp.count} 个文件`);
        } catch (error: unknown) {
            message.error(`清单查询失败: ${describeError(error)}`);
        } finally {
            setLoading(false);
        }
    };

    // 列取所有行键的并集：manifest 各行字段可能不一致，只看首行会漏列。
    // render 兜底 stringify：对象/数组直接作为 React child 会整片崩溃。
    const columns = result?.files?.length
        ? Array.from(new Set(result.files.flatMap((f) => Object.keys(f ?? {})))).map((k) => ({
              title: k,
              dataIndex: k,
              key: k,
              width: 160,
              ellipsis: true,
              render: (v: unknown) =>
                  v === null || v === undefined
                      ? ''
                      : typeof v === 'object'
                        ? JSON.stringify(v)
                        : String(v),
          }))
        : [];

    return (
        <Space direction="vertical" className="w-full">
            <Alert
                type="info"
                showIcon
                message="查询远端 COS 可下载文件清单，不消耗流量配额。可用于确认某日数据是否已发布。"
            />
            <Space wrap>
                <Select value={categoryId} onChange={setCategoryId} style={{ width: 120 }}>
                    <Select.Option value="1">1 K线行情</Select.Option>
                    <Select.Option value="2">2 基础板块</Select.Option>
                    <Select.Option value="3">3 财务数据</Select.Option>
                    <Select.Option value="4">4 债券/ETF</Select.Option>
                    <Select.Option value="5">5 技术衍生</Select.Option>
                    <Select.Option value="6">6 ML数据集</Select.Option>
                </Select>
                <Input
                    placeholder="sub_category (如 daily_forward)"
                    value={subCategory}
                    onChange={(e) => setSubCategory(e.target.value)}
                    style={{ width: 200 }}
                    onPressEnter={query}
                />
                <Input
                    placeholder="交易日期 YYYYMMDD (可选)"
                    value={tradeDate}
                    onChange={(e) => setTradeDate(e.target.value)}
                    style={{ width: 180 }}
                    onPressEnter={query}
                />
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={query}
                    loading={loading}
                    disabled={!connected}
                >
                    查询
                </Button>
                {result && (
                    <Text type="secondary">
                        {result.truncated
                            ? `显示前 ${result.count} / 共 ${result.total} 个文件`
                            : `共 ${result.count} 个文件`}
                    </Text>
                )}
            </Space>
            {result && result.files.length > 0 && (
                <Table
                    dataSource={result.files}
                    columns={columns}
                    rowKey={(_, index) => String(index)}
                    size="small"
                    pagination={{ pageSize: 10, size: 'small' }}
                    scroll={{ x: 'max-content' }}
                />
            )}
        </Space>
    );
}

export default AdminQuantDBPanel;
