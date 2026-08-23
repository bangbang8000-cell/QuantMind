import React, { useState, useEffect, useCallback } from 'react';
import { Button, Spin, Modal, Form, Input, InputNumber, message, Select, Tag, Tooltip, Popconfirm, Empty } from 'antd';
import { Server, Plus, Trash2, Pencil, PlugZap, Activity, RefreshCw, Cpu, HardDrive, MemoryStick } from 'lucide-react';
import { adminService } from '../../admin/services/adminService';

interface CloudNodeInfo {
  id: string;
  name?: string;
  host?: string;
  type?: 'local' | 'remote';
  description?: string;
  available?: boolean;
}

interface CloudNodeDetail {
  id: string;
  name?: string;
  host?: string;
  port?: number;
  user?: string;
  work_dir?: string;
  docker_image?: string;
  gpus?: string;
  has_password?: boolean;
  has_key?: boolean;
}

interface NodeStatusData {
  online?: boolean;
  error?: string;
  cpu_cores?: number;
  cpu_load?: number;
  mem_total_mb?: number;
  mem_used_mb?: number;
  disk_total_kb?: number;
  disk_used_kb?: number;
  gpus?: { util: number; mem_used_mb: number; mem_total_mb: number; temp_c: number; name: string }[];
  containers?: { name: string; status: string }[];
  training_active?: boolean;
  gpu_error?: string;
}

interface NodeFormValues {
  name: string;
  host: string;
  port: number;
  user: string;
  ssh_password?: string;
  ssh_key?: string;
  work_dir: string;
  docker_image: string;
  gpus: string;
}

const ENV = (import.meta as any).env || {};

const DEFAULT_FORM: NodeFormValues = {
  name: ENV.VITE_AUTODL_DEFAULT_NAME || '',
  host: ENV.VITE_AUTODL_DEFAULT_HOST || '',
  port: ENV.VITE_AUTODL_DEFAULT_PORT ? Number(ENV.VITE_AUTODL_DEFAULT_PORT) : 22,
  user: ENV.VITE_AUTODL_DEFAULT_USER || 'root',
  ssh_password: '',
  ssh_key: '',
  work_dir: ENV.VITE_AUTODL_DEFAULT_WORK_DIR || '/root/workspace',
  docker_image: 'quantmind-train:latest',
  gpus: 'all',
};

export const CloudNodeSettings: React.FC = () => {
  const [nodes, setNodes] = useState<CloudNodeInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Record<string, NodeStatusData>>({});
  const [testingId, setTestingId] = useState<string | null>(null);
  const [statusLoadingId, setStatusLoadingId] = useState<string | null>(null);
  const [form] = Form.useForm<NodeFormValues>();

  const loadNodes = useCallback(async () => {
    setIsLoading(true);
    try {
      const resp = await adminService.listTrainingNodes();
      const remoteNodes = (resp?.nodes || []).filter((n: CloudNodeInfo) => n.type === 'remote');
      setNodes(remoteNodes);
    } catch (error: any) {
      message.error(error.message || '加载节点列表失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNodes();
  }, [loadNodes]);

  const openCreate = () => {
    setEditingId(null);
    form.setFieldsValue(DEFAULT_FORM);
    setIsModalOpen(true);
  };

  const openEdit = async (node: CloudNodeInfo) => {
    setEditingId(node.id);
    try {
      const resp = await adminService.getTrainingNodeDetail(node.id);
      if (resp?.success && resp.node) {
        const d: CloudNodeDetail = resp.node;
        form.setFieldsValue({
          name: d.name || '',
          host: d.host || '',
          port: d.port || 22,
          user: d.user || 'root',
          ssh_password: '',
          ssh_key: '',
          work_dir: d.work_dir || '/workspace',
          docker_image: d.docker_image || 'quantmind-train:latest',
          gpus: d.gpus || 'all',
        });
      } else {
        form.setFieldsValue({ ...DEFAULT_FORM, name: node.name || '', host: node.host || '' });
      }
      setIsModalOpen(true);
    } catch (error: any) {
      message.error(error.message || '加载节点详情失败');
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        id: editingId,
        name: values.name,
        host: values.host,
        port: values.port,
        user: values.user,
        ssh_password: values.ssh_password || undefined,
        ssh_key: values.ssh_key || undefined,
        work_dir: values.work_dir,
        docker_image: values.docker_image,
        gpus: values.gpus,
      };
      const resp = await adminService.saveTrainingNode(payload);
      if (resp?.success) {
        message.success(editingId ? '节点已更新' : '节点已创建');
        setIsModalOpen(false);
        await loadNodes();
      } else {
        message.error(resp?.error || '保存失败');
      }
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error.message || '保存失败');
    }
  };

  const handleDelete = async (nodeId: string) => {
    try {
      const resp = await adminService.deleteTrainingNode(nodeId);
      if (resp?.success) {
        message.success('节点已删除');
        await loadNodes();
      } else {
        message.warning(resp?.success === false ? '节点不存在或删除失败' : '删除失败');
      }
    } catch (error: any) {
      message.error(error.message || '删除失败');
    }
  };

  const handleTest = async (nodeId: string) => {
    setTestingId(nodeId);
    try {
      const resp = await adminService.testTrainingNode(nodeId);
      if (resp?.success) {
        const ok = resp.ssh && resp.docker;
        message.success(ok ? `节点 ${nodeId} SSH 与 Docker 均可用` : `节点 SSH=${!!resp.ssh} Docker=${!!resp.docker}`);
      } else {
        message.error(resp?.error || '测试连接失败');
      }
    } catch (error: any) {
      message.error(error.message || '测试连接失败');
    } finally {
      setTestingId(null);
    }
  };

  const handleFetchStatus = async (nodeId: string) => {
    setStatusLoadingId(nodeId);
    try {
      const st = await adminService.getTrainingNodeStatus(nodeId);
      setStatusMap({ ...statusMap, [nodeId]: st as NodeStatusData });
    } catch (error: any) {
      message.error(error.message || '获取状态失败');
    } finally {
      setStatusLoadingId(null);
    }
  };

  const renderStatus = (node: CloudNodeInfo) => {
    const st = statusMap[node.id];
    if (!st) {
      return <Tag color="default">未采集</Tag>;
    }
    if (!st.online) {
      return <Tag color="red" style={{ marginRight: 0 }}>离线{st.error ? ` · ${st.error}` : ''}</Tag>;
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Tag color="green" style={{ marginRight: 0 }}>在线</Tag>
        {st.cpu_cores ? <Tag style={{ marginRight: 0 }}><Cpu size={11} className="inline mr-0.5" />{st.cpu_cores} 核</Tag> : null}
        {st.mem_total_mb ? (
          <Tag style={{ marginRight: 0 }}>
            <MemoryStick size={11} className="inline mr-0.5" />
            {(st.mem_used_mb || 0) / 1024}/{st.mem_total_mb / 1024} GB
          </Tag>
        ) : null}
        {st.disk_total_kb ? (
          <Tag style={{ marginRight: 0 }}>
            <HardDrive size={11} className="inline mr-0.5" />
            {((st.disk_used_kb || 0) / 1024 / 1024).toFixed(1)}/{ (st.disk_total_kb / 1024 / 1024).toFixed(1)} GB
          </Tag>
        ) : null}
        {st.gpus && st.gpus.length > 0
          ? st.gpus.map((g, i) => (
              <Tag key={i} color="purple" style={{ marginRight: 0 }} title={g.name}>
                GPU{i} {g.util}% {g.temp_c}°C
              </Tag>
            ))
          : st.gpu_error
            ? <Tag color="orange" style={{ marginRight: 0 }}>{st.gpu_error}</Tag>
            : null}
        {st.training_active ? <Tag color="blue" style={{ marginRight: 0 }}>训练中</Tag> : null}
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="w-full pt-1">
        <div className="w-full rounded-xl border border-gray-200 bg-white p-8 flex items-center justify-center min-h-[200px]">
          <Spin />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full pt-1 space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-indigo-100 rounded-md">
                <Server className="w-4 h-4 text-indigo-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-800">云端节点</h3>
                <p className="text-[11px] text-gray-500">配置 AutoDL 远程 GPU 训练节点，用于模型训练</p>
              </div>
            </div>
            <Button type="primary" size="small" icon={<Plus className="w-3.5 h-3.5" />} onClick={openCreate} className="!rounded-[8px]">
              新建节点
            </Button>
          </div>

          {nodes.length === 0 ? (
            <Empty description="暂无云端节点，点击「新建节点」添加 AutoDL 节点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div className="space-y-3">
              {nodes.map((node) => (
                <div key={node.id} className="rounded-xl border border-gray-200 bg-slate-50/50 p-3.5 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <Server className="w-4 h-4 text-indigo-500 shrink-0" />
                      <span className="text-sm font-bold text-gray-800 truncate">{node.name}</span>
                      <Tag color="blue" style={{ marginRight: 0 }}>{node.id}</Tag>
                      <Tag style={{ marginRight: 0 }}>{node.host}</Tag>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Tooltip title="测试连接">
                        <Button
                          size="small"
                          type="text"
                          icon={<PlugZap className="w-3.5 h-3.5" />}
                          loading={testingId === node.id}
                          onClick={() => void handleTest(node.id)}
                        />
                      </Tooltip>
                      <Tooltip title="采集状态">
                        <Button
                          size="small"
                          type="text"
                          icon={<Activity className="w-3.5 h-3.5" />}
                          loading={statusLoadingId === node.id}
                          onClick={() => void handleFetchStatus(node.id)}
                        />
                      </Tooltip>
                      <Tooltip title="编辑">
                        <Button size="small" type="text" icon={<Pencil className="w-3.5 h-3.5" />} onClick={() => void openEdit(node)} />
                      </Tooltip>
                      <Popconfirm
                        title="确认删除此节点？"
                        description="将从配置中移除该 AutoDL 节点"
                        okText="删除"
                        cancelText="取消"
                        onConfirm={() => void handleDelete(node.id)}
                      >
                        <Button size="small" type="text" danger icon={<Trash2 className="w-3.5 h-3.5" />} />
                      </Popconfirm>
                    </div>
                  </div>
                  <div>{renderStatus(node)}</div>
                  <div className="flex items-center gap-3 text-[11px] text-gray-400 flex-wrap">
                    <span>用户: {node.id ? '见详情' : ''}</span>
                    <span>镜像: {statusMap[node.id]?.gpus ? '—' : ''}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="text-[11px] text-gray-400 space-y-0.5 pt-1 border-t border-gray-100">
            <p>• 节点配置保存在服务器 config/training_nodes.yaml，重启后仍生效</p>
            <p>• SSH 密码仅保存到服务端，前端不显示明文；留空表示保持原值</p>
            <p>• 使用 GPU 需节点安装 nvidia-container-toolkit，gpus 支持 all / 数字 / 0(CPU)</p>
          </div>
        </div>
      </div>

      <Modal
        title={editingId ? '编辑云端节点' : '新建云端节点'}
        open={isModalOpen}
        onOk={() => void handleSave()}
        onCancel={() => setIsModalOpen(false)}
        okText="保存"
        cancelText="取消"
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={DEFAULT_FORM} className="!pt-2">
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="name" label="节点名称" rules={[{ required: true, message: '请输入节点名称' }]}>
              <Input placeholder="如 AutoDL A100" className="!h-8 !rounded-[8px]" />
            </Form.Item>
            <Form.Item name="host" label="节点地址" rules={[{ required: true, message: '请输入 IP/域名' }]}>
              <Input placeholder="如 192.168.31.66" className="!h-8 !rounded-[8px]" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="port" label="SSH 端口" rules={[{ required: true, message: '请输入端口' }]}>
              <InputNumber min={1} max={65535} className="!w-full !h-8 !rounded-[8px]" placeholder="22" />
            </Form.Item>
            <Form.Item name="user" label="SSH 用户" rules={[{ required: true, message: '请输入用户' }]}>
              <Input placeholder="如 root" className="!h-8 !rounded-[8px]" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="ssh_password" label="SSH 密码" extra={editingId ? '留空表示保持原值' : undefined}>
              <Input.Password placeholder="密码或留空" className="!h-8 !rounded-[8px]" />
            </Form.Item>
            <Form.Item name="ssh_key" label="SSH 密钥路径" extra={editingId ? '留空表示保持原值' : undefined}>
              <Input placeholder="/path/to/key 或留空" className="!h-8 !rounded-[8px]" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="work_dir" label="远端工作目录">
              <Input placeholder="/workspace" className="!h-8 !rounded-[8px]" />
            </Form.Item>
            <Form.Item name="gpus" label="GPU 挂载">
              <Select
                className="[&_.ant-select-selector]:!h-8 [&_.ant-select-selector]:!rounded-[8px] [&_.ant-select-selector]:!items-center"
                options={[
                  { value: 'all', label: '全部 GPU' },
                  { value: '0', label: '不使用 GPU(CPU)' },
                  { value: '1', label: '1 块 GPU' },
                  { value: '2', label: '2 块 GPU' },
                ]}
              />
            </Form.Item>
          </div>
          <Form.Item name="docker_image" label="训练镜像">
            <Input placeholder="quantmind-train:latest" className="!h-8 !rounded-[8px]" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CloudNodeSettings;
