import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert, AutoComplete, Button, Empty, InputNumber, Modal, Space, Table, Tag,
    Typography, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CloudDownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import {
    dataPlatformService, QuantDBDataset, QuantDBPreview,
} from '../../services/dataPlatformService';
import { describeError } from './utils';

const { Text } = Typography;

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

interface QuantDBPreviewDrawerProps {
    dataset: QuantDBDataset | null;
    onClose: () => void;
}

export function QuantDBPreviewDrawer({ dataset, onClose }: QuantDBPreviewDrawerProps) {
    const [preview, setPreview] = useState<QuantDBPreview | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [symbol, setSymbol] = useState('');
    const [limit, setLimit] = useState(DEFAULT_LIMIT);

    const load = useCallback(async (opts: { remote?: boolean } = {}) => {
        if (!dataset) return;
        setLoading(true);
        setError(null);
        try {
            setPreview(await dataPlatformService.previewQuantDBDataset({
                dataset: dataset.dataset,
                symbol: symbol.trim() || undefined,
                limit,
                remote: opts.remote,
            }));
        } catch (err: unknown) {
            setError(describeError(err));
            setPreview(null);
        } finally {
            setLoading(false);
        }
    }, [dataset, symbol, limit]);

    // 切换数据集时重置查询条件并自动加载
    useEffect(() => {
        if (!dataset) {
            setPreview(null);
            return;
        }
        setSymbol('');
        setLimit(DEFAULT_LIMIT);
        setError(null);
        dataPlatformService
            .previewQuantDBDataset({ dataset: dataset.dataset, limit: DEFAULT_LIMIT })
            .then(setPreview)
            .catch((err: unknown) => {
                setError(describeError(err));
                setPreview(null);
            });
    }, [dataset]);

    const fetchRemote = async () => {
        await load({ remote: true });
        message.info('已通过 SDK 远端预览（不消耗下载流量）');
    };

    const columns: ColumnsType<Record<string, unknown>> = (preview?.columns ?? []).map((col) => ({
        title: (
            <Space direction="vertical" size={0}>
                <Text strong className="text-xs">{col.name}</Text>
                <Text type="secondary" style={{ fontSize: 10 }}>{col.dtype}</Text>
            </Space>
        ),
        dataIndex: col.name,
        key: col.name,
        width: 150,
        ellipsis: true,
        render: (value: unknown) => formatCell(value),
    }));

    const supportsSymbol = dataset?.layout === 'symbol';

    return (
        <Modal
            open={dataset !== null}
            onCancel={onClose}
            width="88%"
            title={dataset ? `${dataset.name} · ${dataset.dataset}` : ''}
            footer={null}
            destroyOnHidden
        >
            <Space direction="vertical" className="w-full" size="middle">
                <Space wrap>
                    {supportsSymbol && (
                        <AutoComplete
                            value={symbol}
                            onChange={setSymbol}
                            options={(preview?.symbol_choices ?? []).map((s) => ({ value: s }))}
                            filterOption={(input, option) =>
                                String(option?.value ?? '').toUpperCase().includes(input.toUpperCase())
                            }
                            placeholder="标的代码，如 600519.SH"
                            style={{ width: 220 }}
                            onSelect={() => load()}
                        />
                    )}
                    <Space size="small">
                        <Text type="secondary" className="text-xs">行数</Text>
                        <InputNumber
                            min={1}
                            max={MAX_LIMIT}
                            value={limit}
                            onChange={(v) => setLimit(v ?? DEFAULT_LIMIT)}
                            style={{ width: 90 }}
                        />
                    </Space>
                    <Button type="primary" onClick={() => load()} loading={loading}>
                        查询
                    </Button>
                    <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>
                        刷新
                    </Button>
                    <Button icon={<CloudDownloadOutlined />} onClick={fetchRemote} loading={loading}>
                        远端预览
                    </Button>
                </Space>

                {preview && (
                    <Space wrap size="small">
                        <Tag color={preview.source === 'local' ? 'green' : 'blue'}>
                            {preview.source === 'local' ? '本地 parquet（零流量）' : 'SDK 远端预览'}
                        </Tag>
                        <Tag>{preview.rows_total.toLocaleString()} 行</Tag>
                        <Tag>{preview.column_count ?? preview.columns.length} 列</Tag>
                        {preview.symbol_total !== undefined && (
                            <Tag color="purple">{preview.symbol_total.toLocaleString()} 个标的</Tag>
                        )}
                        {preview.file && (
                            <Text type="secondary" className="text-xs">{preview.file}</Text>
                        )}
                    </Space>
                )}

                {error && (
                    <Alert
                        type="error"
                        showIcon
                        message="预览失败"
                        description={error}
                    />
                )}

                {preview && preview.data.length > 0 ? (
                    <Table
                        dataSource={preview.data.map((r, i) => ({ ...r, _key: String(i) }))}
                        columns={columns}
                        rowKey="_key"
                        size="small"
                        loading={loading}
                        pagination={{ pageSize: 20, size: 'small', showSizeChanger: true }}
                        scroll={{ x: 'max-content', y: 480 }}
                        bordered
                    />
                ) : (
                    !error && !loading && (
                        <Empty description={
                            dataset?.synced
                                ? '该数据集本地无可预览样本，可尝试远端预览'
                                : '该数据集尚未同步到本地，可尝试远端预览'
                        } />
                    )
                )}
            </Space>
        </Modal>
    );
}

function formatCell(value: unknown): React.ReactNode {
    if (value === null || value === undefined) {
        return <Text type="secondary">null</Text>;
    }
    if (typeof value === 'number') {
        return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4);
    }
    if (typeof value === 'boolean') {
        return String(value);
    }
    return String(value);
}

export default QuantDBPreviewDrawer;
