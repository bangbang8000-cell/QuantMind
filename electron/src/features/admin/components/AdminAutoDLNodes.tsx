import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    Button,
    Card,
    Col,
    Empty,
    Row,
    Space,
    Spin,
    Tag,
    Tooltip,
    Typography,
    Progress,
} from 'antd';
import {
    CloudServerOutlined,
    ReloadOutlined,
    SyncOutlined,
    CheckCircleFilled,
    CloseCircleFilled,
    ThunderboltFilled,
    RocketFilled,
} from '@ant-design/icons';
import { adminService } from '../services/adminService';

const { Title, Text } = Typography;

interface NodeInfo {
    id: string;
    type: string;
    name: string;
    host?: string;
    available?: boolean;
}

interface NodeStatus {
    id: string;
    name: string;
    host: string;
    online: boolean;
    error?: string;
    is_local?: boolean;
    cpu_cores?: number;
    cpu_load?: number;
    mem_total_mb?: number;
    mem_used_mb?: number;
    gpus?: Array<{
        util: number;
        mem_used_mb: number;
        mem_total_mb: number;
        temp_c: number;
        name: string;
    }>;
    containers?: Array<{ name: string; status: string }>;
    training_active?: boolean;
    ping_ms?: number | null;
}

const fmtMB = (mb?: number): string =>
    mb === undefined ? '—' : mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${mb}MB`;

export const AdminAutoDLNodes: React.FC = () => {
    const [nodes, setNodes] = useState<NodeInfo[]>([]);
    const [statusMap, setStatusMap] = useState<Record<string, NodeStatus>>({});
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchAll = useCallback(async () => {
        try {
            setRefreshing(true);
            const resp = await adminService.listTrainingNodes();
            const nodeList: NodeInfo[] = resp?.nodes || [];
            setNodes(nodeList);

            // 采集每个远端节点状态
            const statuses: Record<string, NodeStatus> = {};
            const remote = nodeList.filter((n) => n.type === 'remote');
            if (remote.length > 0) {
                await Promise.all(
                    remote.map(async (n) => {
                        try {
                            const st = await adminService.getTrainingNodeStatus(n.id);
                            statuses[n.id] = st;
                        } catch {
                            statuses[n.id] = { id: n.id, name: n.name, host: n.host || '', online: false, error: '采集失败' };
                        }
                    }),
                );
            }
            setStatusMap(statuses);
        } finally {
            setRefreshing(false);
        }
    }, []);

    // 初次加载
    useEffect(() => {
        setLoading(true);
        fetchAll().finally(() => setLoading(false));
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [fetchAll]);

    // 自动刷新
    useEffect(() => {
        if (timerRef.current) clearInterval(timerRef.current);
        if (autoRefresh) {
            timerRef.current = setInterval(() => void fetchAll(), 30000);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [autoRefresh, fetchAll]);

    const renderGpuInfo = (st: NodeStatus) => {
        if (!st.gpus || st.gpus.length === 0) {
            return <Text type="secondary" style={{ fontSize: 11 }}>GPU 不可用/未检测到</Text>;
        }
        return (
            <Space size="small" wrap>
                {st.gpus.map((g, i) => (
                    <Tag key={i} color={g.util > 80 ? 'red' : g.util > 30 ? 'orange' : 'green'}>
                        {g.name || 'GPU'}: {g.util}% · {fmtMB(g.mem_used_mb)}/{fmtMB(g.mem_total_mb)} · {g.temp_c}°C
                    </Tag>
                ))}
            </Space>
        );
    };

    return (
        <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
                <div>
                    <Title level={4} style={{ margin: 0 }}>AutoDL 训练节点</Title>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        监控各 AutoDL GPU 服务器状态与训练进度
                    </Text>
                </div>
                <Space>
                    <Button
                        size="small"
                        onClick={() => setAutoRefresh(!autoRefresh)}
                        icon={<SyncOutlined spin={autoRefresh} />}
                    >
                        {autoRefresh ? '自动刷新 30s' : '自动刷新关'}
                    </Button>
                    <Button size="small" type="primary" icon={<ReloadOutlined />} onClick={() => void fetchAll()} loading={refreshing}>
                        刷新状态
                    </Button>
                </Space>
            </div>

            {loading ? (
                <div className="text-center py-10"><Spin /></div>
            ) : nodes.length === 0 ? (
                <Empty description="未配置 AutoDL 节点（在 config/training_nodes.yaml 中添加）" />
            ) : (
                <Row gutter={[16, 16]}>
                    {nodes.map((n) => {
                        const st = statusMap[n.id];
                        const isRemote = n.type === 'remote';
                        return (
                            <Col span={12} key={n.id}>
                                <Card
                                    size="small"
                                    title={
                                        <Space>
                                            <CloudServerOutlined />
                                            <Text strong>{n.name}</Text>
                                            {!isRemote && <Tag>本地</Tag>}
                                            {isRemote && st?.online && <Tag color="green">在线</Tag>}
                                            {isRemote && st && !st.online && <Tag color="red">离线</Tag>}
                                        </Space>
                                    }
                                    extra={st?.training_active ? <Tag color="processing">训练中</Tag> : isRemote && st?.online ? <Tag>空闲</Tag> : null}
                                >
                                    {!isRemote ? (
                                        <Text type="secondary">本地 Docker 训练（Docker-in-Docker）</Text>
                                    ) : !st ? (
                                        <Text type="secondary">状态加载中...</Text>
                                    ) : st.online ? (
                                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                            <Space wrap>
                                                <Text style={{ fontSize: 11 }}>💻 CPU: {st.cpu_cores ?? '—'}核 · 负载 {st.cpu_load ?? '—'}</Text>
                                                <Text style={{ fontSize: 11 }}>🧠 内存: {fmtMB(st.mem_used_mb)}/{fmtMB(st.mem_total_mb)}</Text>
                                                {st.ping_ms != null && <Text style={{ fontSize: 11 }}>📡 {st.ping_ms}ms</Text>}
                                            </Space>
                                            <div>{renderGpuInfo(st)}</div>
                                            {st.training_active && (
                                                <div>
                                                    <Space>
                                                        <ThunderboltFilled style={{ color: '#fa8c16' }} />
                                                        <Text strong style={{ fontSize: 12 }}>训练中</Text>
                                                    </Space>
                                                    <Progress percent={50} size="small" status="active" />
                                                    {(st.containers || []).map((c, i) => (
                                                        <Text key={i} type="secondary" style={{ fontSize: 11, display: 'block' }}>
                                                            {c.name}: {c.status}
                                                        </Text>
                                                    ))}
                                                </div>
                                            )}
                                        </Space>
                                    ) : (
                                        <Space direction="vertical" size="small">
                                            <Text type="danger"><CloseCircleFilled /> 节点不可达</Text>
                                            {st.error && <Text type="secondary" style={{ fontSize: 11 }}>{st.error}</Text>}
                                        </Space>
                                    )}
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            )}
        </div>
    );
};

export default AdminAutoDLNodes;
