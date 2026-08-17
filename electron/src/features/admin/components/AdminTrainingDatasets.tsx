/** Versioned QuantDB factor sources for model training. */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Button, Card, Col, Form, Input, Modal, Row, Select, Space, Statistic,
  Switch, Table, Tag, Typography, message,
} from 'antd';
import { DatabaseOutlined, EditOutlined, PlusOutlined, ReloadOutlined, RocketOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { adminService } from '../services/adminService';

const { Title, Text } = Typography;

const SOURCE_OPTIONS = [
  { value: 'l1_l2_factors', label: 'L1 + L2 合并宽表（默认）' },
  { value: 'l1_factors', label: 'L1 因子' },
  { value: 'l2_factors', label: 'L2 因子' },
];

type Mapping = {
  mapping_id: string; source_dataset: string; source_column: string; key: string;
  feature_name: string; enabled: boolean; default_selected: boolean; required: boolean;
  category_id?: string; category_name?: string; order_no?: number;
};

export const AdminTrainingDatasets: React.FC = () => {
  const [source, setSource] = useState('l1_l2_factors');
  const [sources, setSources] = useState<Record<string, any>>({});
  const [fields, setFields] = useState<any[]>([]);
  const [published, setPublished] = useState<any | null>(null);
  const [draft, setDraft] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Mapping | null>(null);
  const [form] = Form.useForm();

  const mappings = useMemo<Mapping[]>(
    () => (draft?.categories || []).flatMap((category: any) => category.features || []), [draft],
  );
  const mappedFields = useMemo(() => new Set(mappings.map(item => item.source_column)), [mappings]);
  const pending = useMemo(() => fields.filter(field => !mappedFields.has(field.column_name)), [fields, mappedFields]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sourceResult, fieldsResult] = await Promise.all([
        adminService.getQuantDBFactorSources(), adminService.getQuantDBFactorFields(source),
      ]);
      setSources(sourceResult.sources || {});
      setFields(fieldsResult.fields || []);
      try {
        setPublished(await adminService.getQuantDBFactorCatalog(source));
      } catch { setPublished(null); }
      if (draft) {
        try { setDraft(await adminService.getQuantDBFactorCatalog(source, draft.version_id)); }
        catch { setDraft(null); }
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载 QuantDB 训练数据集失败');
    } finally { setLoading(false); }
  }, [source, draft?.version_id]);

  useEffect(() => { load(); }, [load]);

  const refreshDiscovery = async () => {
    setLoading(true);
    try {
      await adminService.refreshQuantDBFactorSources();
      message.success('字段发现已刷新');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '字段发现失败');
    } finally { setLoading(false); }
  };

  const createDraft = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const created = await adminService.createQuantDBFactorDraft(values.version_name, source);
      await adminService.seedQuantDBFactorDraft(created.version_id);
      setDraft(await adminService.getQuantDBFactorCatalog(source, created.version_id));
      setCreating(false);
      message.success('草稿已创建，全部发现字段已导入为待配置映射');
    } catch (error: any) {
      setCreating(false);
      if (error?.errorFields) return;
      message.error(error?.response?.data?.detail || error?.message || '创建草稿失败；请先执行字段刷新');
    }
  };

  const saveMapping = async (mapping: Mapping) => {
    if (!draft) return;
    try {
      await adminService.saveQuantDBFactorMapping(draft.version_id, {
        mapping_id: mapping.mapping_id,
        source_dataset: source,
        source_column: mapping.source_column,
        feature_key: mapping.key,
        display_name: mapping.feature_name,
        category_id: mapping.category_id || 'other',
        category_name: mapping.category_name || '其他因子',
        enabled: mapping.enabled,
        default_selected: mapping.default_selected,
        required: mapping.required,
        sort_order: mapping.order_no || 0,
      });
      setDraft(await adminService.getQuantDBFactorCatalog(source, draft.version_id));
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '保存映射失败');
    }
  };

  const publish = async () => {
    if (!draft) return;
    try {
      await adminService.publishQuantDBFactorDraft(draft.version_id);
      message.success('映射版本已发布；仅后续训练任务会使用它');
      setDraft(null);
      await load();
    } catch (error: any) { message.error(error?.response?.data?.detail || '发布失败'); }
  };

  const clonePublished = async () => {
    if (!published) return;
    try {
      const created = await adminService.cloneQuantDBFactorCatalog(
        published.version_id, `${published.version_name} 副本`,
      );
      setDraft(await adminService.getQuantDBFactorCatalog(source, created.version_id));
      message.success('已复制为草稿，可安全编辑');
    } catch (error: any) { message.error(error?.response?.data?.detail || '复制发布版本失败'); }
  };

  const columns: ColumnsType<Mapping> = [
    { title: '原始字段', dataIndex: 'source_column', width: 180, render: (v) => <Text code>{v}</Text> },
    { title: '逻辑因子', dataIndex: 'key', width: 170 },
    { title: '分类', dataIndex: 'category_name', width: 130 },
    { title: '启用', dataIndex: 'enabled', width: 80, render: (v, r) => <Switch size="small" checked={v} disabled={!draft} onChange={checked => saveMapping({ ...r, enabled: checked })} /> },
    { title: '默认', dataIndex: 'default_selected', width: 80, render: (v, r) => <Switch size="small" checked={v} disabled={!draft || !r.enabled} onChange={checked => saveMapping({ ...r, default_selected: checked })} /> },
    { title: '编辑', width: 68, render: (_, r) => <Button type="text" size="small" disabled={!draft} icon={<EditOutlined />} onClick={() => { setEditing(r); form.setFieldsValue({ feature_key: r.key, display_name: r.feature_name, category_id: r.category_id, category_name: r.category_name }); }} /> },
  ];

  return <div className="p-6 space-y-4">
    <div className="flex items-center justify-between">
      <div><Title level={4} className="!mb-0"><DatabaseOutlined /> 模型训练数据集</Title>
        <Text type="secondary">仅读取 QuantDB 原始因子；映射草稿发布后才影响新的训练任务。</Text></div>
      <Space><Select value={source} options={SOURCE_OPTIONS} style={{ width: 240 }} onChange={value => { setSource(value); setDraft(null); }} />
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
        <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={refreshDiscovery}>字段发现</Button></Space>
    </div>

    <Row gutter={[16, 16]}>
      {SOURCE_OPTIONS.map(option => {
        const status = sources[option.value] || {};
        return <Col xs={24} md={8} key={option.value}><Card size="small" title={option.label}>
          <Statistic title={status.ready ? '可用于直读训练' : '尚不可用'} value={status.files || 0} suffix="个分区文件" valueStyle={{ color: status.ready ? '#3f8600' : '#cf1322', fontSize: 18 }} />
          <div className="mt-2 text-xs text-gray-500">覆盖：{status.min_date || '--'} ～ {status.max_date || '--'} · {status.columns?.length || 0} 字段</div>
          {!status.ready && <Tag color="warning" className="mt-2">缺少：{(status.missing_required || []).join('、') || status.reason}</Tag>}
        </Card></Col>;
      })}
    </Row>

    <Alert type="info" showIcon message="单次任务只能选择一个数据源" description="默认 L1+L2 合并宽表。L1、L2 是独立训练源，禁止跨源自由拼接；数据或 OHLCV 覆盖不完整时，直读训练入口会拒绝提交。" />

    <Row gutter={[16, 16]}>
      <Col xs={24} lg={9}><Card title="字段发现 / 待分类" extra={<Tag>{fields.length} 个可映射字段</Tag>}>
        <div className="mb-2 text-xs text-gray-500">未进入当前草稿：{pending.length} 个。创建草稿会导入全部字段，默认禁用。</div>
        <Table size="small" rowKey="column_name" dataSource={pending.slice(0, 100)} pagination={false} scroll={{ y: 265 }} columns={[
          { title: '字段', dataIndex: 'column_name', render: (v: string) => <Text code>{v}</Text> },
          { title: '状态', dataIndex: 'is_present', width: 70, render: (v: boolean) => v ? <Tag color="green">存在</Tag> : <Tag>删除</Tag> },
        ]} />
      </Card></Col>
      <Col xs={24} lg={15}><Card title="分类映射草稿" extra={draft ? <Space><Tag color="blue">{draft.version_name}</Tag><Button type="primary" icon={<RocketOutlined />} onClick={publish}>发布</Button></Space> : null}>
        {!draft ? <Form form={form} layout="inline" onFinish={createDraft}>
          <Form.Item name="version_name" rules={[{ required: true, message: '请输入版本名称' }]}><Input placeholder="例如：2026-08 L1+L2 默认因子集" style={{ width: 280 }} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={creating} icon={<PlusOutlined />}>新建草稿并导入字段</Button>
        </Form> : <Table size="small" rowKey="mapping_id" dataSource={mappings} columns={columns} pagination={{ pageSize: 20, showSizeChanger: false }} scroll={{ x: 780, y: 310 }} />}
      </Card></Col>
    </Row>

    <Card title="已发布特征集版本" extra={published ? <Space><Tag color="green">当前活动版本</Tag><Button size="small" disabled={!!draft} onClick={clonePublished}>复制为草稿</Button></Space> : <Tag>未发布</Tag>}>
      {published ? <Space wrap><Text strong>{published.version_name}</Text><Tag>{published.version_id}</Tag><Tag>{published.feature_count} 个映射字段</Tag><Text type="secondary">发布后不可修改；需要调整时创建新的草稿版本。</Text></Space> : <Text type="secondary">此数据源尚未发布映射版本，训练页不会将它作为 QuantDB 直读训练集。</Text>}
    </Card>

    <Modal title="编辑逻辑映射" open={!!editing} onCancel={() => setEditing(null)} onOk={async () => {
      const values = await form.validateFields(); if (editing) { await saveMapping({ ...editing, ...values }); setEditing(null); }
    }}>
      <Form form={form} layout="vertical"><Form.Item name="feature_key" label="逻辑因子 ID" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="display_name" label="显示名" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="category_id" label="分类 ID" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="category_name" label="分类名称" rules={[{ required: true }]}><Input /></Form.Item></Form>
    </Modal>
  </div>;
};
