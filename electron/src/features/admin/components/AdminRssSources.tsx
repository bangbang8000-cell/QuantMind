/**
 * RSS 源管理（管理员）
 *
 * 代理 Huntly 的 /api/setting/feeds/* 与 /api/setting/folder/*
 * 提供：列表 / 预览 / 新增 / 删除 / 重命名 / 移动文件夹 / 常用精选一键填入 / RSSHub生成
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  GlobalOutlined,
  PlusOutlined,
  ReadOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  newsService,
  type HuntlyConnector,
  type HuntlyFeedPreview,
  type HuntlyFolder,
} from '../../news/services/newsService';

const { Title, Text, Paragraph } = Typography;

interface SourceRow extends HuntlyConnector {
  folderId: number | null;
  folderName: string;
}

const UNGROUPED_LABEL = '未分组';

// 精选优质预设源
const PRESET_FEEDS = [
  {
    category: 'A股核心快讯',
    items: [
      { name: '财联社 7x24快讯', url: 'https://feedx.net/rss/cls.xml', folder: 'A股快讯' },
      { name: '华尔街见闻 实时快讯', url: 'https://feedx.net/rss/wallstreetcn.xml', folder: 'A股快讯' },
      { name: '第一财经 每日精选', url: 'https://feedx.net/rss/yicai.xml', folder: 'A股快讯' },
      { name: '东方财富 财经要闻', url: 'https://www.eastmoney.com/rss/news.xml', folder: 'A股快讯' },
    ],
  },
  {
    category: '宏观政策与监管',
    items: [
      { name: '中国人民银行 政策动态', url: 'https://rsshub.app/pbc/goutongjiaoliu', folder: '宏观政策' },
      { name: '中国证监会 要闻发布', url: 'https://rsshub.app/csrc/news', folder: '宏观政策' },
      { name: '国家统计局 数据发布', url: 'https://rsshub.app/stats/release', folder: '宏观政策' },
    ],
  },
  {
    category: '量化研究与前沿',
    items: [
      { name: 'arXiv 计算机金融预印本', url: 'http://export.arxiv.org/rss/q-fin', folder: '量化研究' },
      { name: 'Microsoft Qlib 官方更新', url: 'https://github.com/microsoft/qlib/releases.atom', folder: '量化研究' },
    ],
  },
  {
    category: '全球市场与资产',
    items: [
      { name: '彭博市场动态 (Bloomberg)', url: 'https://feeds.bloomberg.com/markets/news.rss', folder: '全球市场' },
      { name: 'Coindesk 数字货币', url: 'https://www.coindesk.com/arc/outboundfeeds/rss/', folder: '全球市场' },
    ],
  },
];

export const AdminRssSources: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [folders, setFolders] = useState<HuntlyFolder[]>([]);

  // —— 新增源 modal
  const [addOpen, setAddOpen] = useState(false);
  const [addForm] = Form.useForm();
  const [previewing, setPreviewing] = useState(false);
  const [previewData, setPreviewData] = useState<HuntlyFeedPreview | null>(null);

  // —— 编辑源 modal
  const [editOpen, setEditOpen] = useState(false);
  const [editForm] = Form.useForm();
  const [editingId, setEditingId] = useState<number | null>(null);

  // —— 文件夹管理 modal
  const [folderOpen, setFolderOpen] = useState(false);
  const [folderName, setFolderName] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await newsService.adminListFolders();
      setFolders(r.folders || []);
    } catch (e: any) {
      message.error(`加载失败: ${e?.response?.data?.detail || e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const folderOptions = useMemo(
    () => [
      { label: UNGROUPED_LABEL, value: 0 },
      ...folders
        .filter((f) => f.id != null)
        .map((f) => ({ label: f.name || `#${f.id}`, value: f.id as number })),
    ],
    [folders],
  );

  const rows: SourceRow[] = useMemo(() => {
    const out: SourceRow[] = [];
    folders.forEach((f) => {
      const folderId = f.id ?? null;
      const folderName = f.name || UNGROUPED_LABEL;
      (f.connectors || []).forEach((c) => {
        out.push({ ...c, folderId, folderName });
      });
    });
    return out;
  }, [folders]);

  const totalInboxCount = useMemo(() => {
    return rows.reduce((acc, curr) => acc + (curr.inboxCount || 0), 0);
  }, [rows]);

  const handlePreview = async () => {
    const url = addForm.getFieldValue('subscribe_url');
    if (!url) {
      message.warning('请先填写订阅地址');
      return;
    }
    setPreviewing(true);
    setPreviewData(null);
    try {
      const data = await newsService.adminPreviewFeed(url);
      setPreviewData(data);
      if (data?.title) {
        message.success(`预览成功：${data.title}`);
        if (!addForm.getFieldValue('name')) {
          addForm.setFieldsValue({ name: data.title });
        }
      }
    } catch (e: any) {
      message.error(`预览失败: ${e?.response?.data?.detail || e?.message || e}`);
    } finally {
      setPreviewing(false);
    }
  };

  const applyPreset = (preset: { name: string; url: string; folder: string }) => {
    addForm.setFieldsValue({
      subscribe_url: preset.url,
      name: preset.name,
    });
    // 寻找匹配的 folderId
    const foundFolder = folders.find((f) => f.name === preset.folder);
    if (foundFolder && foundFolder.id) {
      addForm.setFieldsValue({ folder_id: foundFolder.id });
    }
    message.info(`已填入「${preset.name}」`);
  };

  const handleAddSubmit = async () => {
    const values = await addForm.validateFields();
    try {
      await newsService.adminCreateSource({
        subscribe_url: String(values.subscribe_url).trim(),
        folder_id: values.folder_id ?? null,
        name: values.name?.trim() || undefined,
      });
      message.success('订阅源已添加');
      setAddOpen(false);
      addForm.resetFields();
      setPreviewData(null);
      refresh();
    } catch (e: any) {
      message.error(`添加失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const openEdit = async (row: SourceRow) => {
    setEditingId(row.id);
    try {
      const detail = await newsService.adminGetSourceSetting(row.id);
      editForm.setFieldsValue({
        name: detail.name,
        folder_id: detail.folderId ?? 0,
        fetch_interval_minutes:
          detail.fetchIntervalMinutes ?? detail.defaultFetchIntervalMinutes,
        enabled: detail.enabled,
        crawl_full_content: !!detail.crawlFullContent,
        subscribe_url: detail.subscribeUrl,
      });
      setEditOpen(true);
    } catch (e: any) {
      message.error(`加载详情失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const handleEditSubmit = async () => {
    if (editingId == null) return;
    const values = await editForm.validateFields();
    try {
      await newsService.adminUpdateSource(editingId, {
        name: values.name?.trim(),
        folder_id: values.folder_id ?? null,
        fetch_interval_minutes: values.fetch_interval_minutes,
        enabled: values.enabled,
        crawl_full_content: values.crawl_full_content,
      });
      message.success('已保存');
      setEditOpen(false);
      refresh();
    } catch (e: any) {
      message.error(`保存失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const handleDelete = async (row: SourceRow) => {
    try {
      await newsService.adminDeleteSource(row.id);
      message.success(`已删除：${row.name}`);
      refresh();
    } catch (e: any) {
      message.error(`删除失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const handleAddFolder = async () => {
    const name = folderName.trim();
    if (!name) {
      message.warning('文件夹名不能为空');
      return;
    }
    try {
      await newsService.adminCreateFolder(name);
      message.success(`文件夹「${name}」已创建`);
      setFolderName('');
      refresh();
    } catch (e: any) {
      message.error(`创建失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const handleRenameFolder = async (folder: HuntlyFolder) => {
    const next = window.prompt('重命名文件夹', folder.name || '');
    if (!next || !next.trim() || next.trim() === folder.name) return;
    try {
      await newsService.adminRenameFolder(folder.id as number, next.trim());
      message.success('已重命名');
      refresh();
    } catch (e: any) {
      message.error(`重命名失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const handleDeleteFolder = async (folder: HuntlyFolder) => {
    try {
      await newsService.adminDeleteFolder(folder.id as number);
      message.success(`已删除文件夹：${folder.name}`);
      refresh();
    } catch (e: any) {
      message.error(`删除失败: ${e?.response?.data?.detail || e?.message || e}`);
    }
  };

  const getFolderTagColor = (name: string) => {
    if (name === UNGROUPED_LABEL) return 'default';
    if (name.includes('A股') || name.includes('快讯')) return 'blue';
    if (name.includes('政策') || name.includes('宏观')) return 'purple';
    if (name.includes('量化') || name.includes('研究')) return 'cyan';
    if (name.includes('全球') || name.includes('市场')) return 'geekblue';
    return 'volcano';
  };

  const columns: ColumnsType<SourceRow> = [
    {
      title: '订阅源名称',
      dataIndex: 'name',
      key: 'name',
      width: 240,
      render: (text, row) => (
        <Space>
          {row.iconUrl ? (
            <img src={row.iconUrl} alt="" style={{ width: 18, height: 18, borderRadius: 4 }} />
          ) : (
            <GlobalOutlined style={{ color: '#1890ff', fontSize: 16 }} />
          )}
          <Text strong>{text || '(未命名)'}</Text>
          {row.type ? <Tag color="default">{row.type}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '订阅地址 (Feed URL)',
      dataIndex: 'subscribeUrl',
      key: 'subscribeUrl',
      ellipsis: true,
      render: (u) => (
        <Tooltip title={u}>
          <Text type="secondary" copyable={{ tooltips: ['复制链接', '已复制'] }} ellipsis style={{ maxWidth: 360 }}>
            {u}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '所属分类',
      dataIndex: 'folderName',
      key: 'folderName',
      width: 140,
      render: (n) => <Tag color={getFolderTagColor(n)}>{n}</Tag>,
    },
    {
      title: '未读资讯',
      dataIndex: 'inboxCount',
      key: 'inboxCount',
      width: 100,
      align: 'right',
      render: (v) => (v ? <Badge count={v} overflowCount={999} /> : <Text type="secondary">0</Text>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <Tooltip title="编辑属性">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          </Tooltip>
          <Popconfirm
            title={`确定删除「${row.name || row.id}」吗？`}
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => handleDelete(row)}
          >
            <Tooltip title="删除订阅">
              <Button type="text" danger size="small" icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* 顶部标题与统计概览 */}
      <div className="flex items-center justify-between pb-2">
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ReadOutlined style={{ marginRight: 8, color: '#1890ff' }} />
            RSS 资讯源管理
          </Title>
          <Text type="secondary">
            全网金融资讯聚合引擎 · 支持 RSS / Atom / RSSHub · 后端自动 NLP 抽取与情感计算
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新状态
          </Button>
          <Button icon={<FolderOpenOutlined />} onClick={() => setFolderOpen(true)}>
            分类管理
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              addForm.resetFields();
              setPreviewData(null);
              setAddOpen(true);
            }}
          >
            新增订阅源
          </Button>
        </Space>
      </div>

      {/* 状态统计卡片 */}
      <Row gutter={16}>
        <Col span={8}>
          <Card size="small" bordered={false} style={{ background: '#f0f5ff', borderRadius: 8 }}>
            <Statistic
              title="当前活跃订阅源"
              value={rows.length}
              suffix="个"
              valueStyle={{ color: '#1d39c4', fontWeight: 600 }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" bordered={false} style={{ background: '#f6ffed', borderRadius: 8 }}>
            <Statistic
              title="资讯分类目录"
              value={folders.filter((f) => f.id != null).length}
              suffix="组"
              valueStyle={{ color: '#389e0d', fontWeight: 600 }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" bordered={false} style={{ background: '#fff7e6', borderRadius: 8 }}>
            <Statistic
              title="未读资讯总数"
              value={totalInboxCount}
              suffix="篇"
              valueStyle={{ color: '#d46b08', fontWeight: 600 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 订阅源列表表格 */}
      <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 8, overflow: 'hidden' }}>
        <Spin spinning={loading}>
          {rows.length === 0 && !loading ? (
            <Empty
              description="暂无订阅源，点击右上角「新增订阅源」一键配置"
              style={{ padding: 48 }}
            />
          ) : (
            <Table<SourceRow>
              rowKey="id"
              dataSource={rows}
              columns={columns}
              pagination={{ pageSize: 15, showSizeChanger: true }}
              size="middle"
            />
          )}
        </Spin>
      </Card>

      {/* —— 新增 RSS 源 Modal (全新美化) —— */}
      <Modal
        title={
          <Space>
            <PlusOutlined style={{ color: '#1890ff' }} />
            <span>新增 RSS 订阅源</span>
          </Space>
        }
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={handleAddSubmit}
        okText="确认添加"
        cancelText="取消"
        width={720}
        destroyOnClose
      >
        {/* 1. 常用精选推荐一键填入 */}
        <div style={{ background: '#f8fafc', padding: 12, borderRadius: 8, marginBottom: 16, border: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            <ThunderboltOutlined style={{ color: '#f59e0b', marginRight: 6 }} />
            <Text strong style={{ fontSize: 13 }}>精选金融 RSS 源一键填入：</Text>
          </div>
          <div className="space-y-2">
            {PRESET_FEEDS.map((group) => (
              <div key={group.category} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                <Text type="secondary" style={{ fontSize: 11, minWidth: 80 }}>{group.category}：</Text>
                {group.items.map((item) => (
                  <Tag
                    key={item.name}
                    color="blue"
                    style={{ cursor: 'pointer', margin: 0 }}
                    onClick={() => applyPreset(item)}
                  >
                    + {item.name}
                  </Tag>
                ))}
              </div>
            ))}
          </div>
        </div>

        <Form form={addForm} layout="vertical">
          <Form.Item
            name="subscribe_url"
            label="订阅地址 (RSS / Atom URL)"
            rules={[{ required: true, message: '请输入订阅地址' }]}
          >
            <Input
              placeholder="https://example.com/feed.xml 或 http://quantmind-rsshub:1200/..."
              addonAfter={
                <Button
                  type="link"
                  size="small"
                  icon={<EyeOutlined />}
                  loading={previewing}
                  onClick={handlePreview}
                  style={{ padding: '0 8px' }}
                >
                  测试预览
                </Button>
              }
            />
          </Form.Item>

          {/* 2. 本地 RSSHub 快捷构造 */}
          <div style={{ background: '#f0f9ff', padding: '10px 14px', borderRadius: 8, marginBottom: 16, border: '1px solid #bae6fd' }}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
              快捷生成（通过本地 RSSHub 服务）:
            </Text>
            <Row gutter={8}>
              <Col span={8}>
                <Input
                  size="small"
                  placeholder="Twitter 用户名"
                  onPressEnter={(e) => {
                    const u = (e.target as HTMLInputElement).value.trim().replace(/^@/, '');
                    if (u) addForm.setFieldValue('subscribe_url', `http://quantmind-rsshub:1200/twitter/user/${u}`);
                  }}
                />
              </Col>
              <Col span={8}>
                <Input
                  size="small"
                  placeholder="微博用户 UID"
                  onPressEnter={(e) => {
                    const u = (e.target as HTMLInputElement).value.trim();
                    if (u) addForm.setFieldValue('subscribe_url', `http://quantmind-rsshub:1200/weibo/user/${u}`);
                  }}
                />
              </Col>
              <Col span={8}>
                <Input
                  size="small"
                  placeholder="雪球用户 ID"
                  onPressEnter={(e) => {
                    const u = (e.target as HTMLInputElement).value.trim();
                    if (u) addForm.setFieldValue('subscribe_url', `http://quantmind-rsshub:1200/xueqiu/user/${u}`);
                  }}
                />
              </Col>
            </Row>
          </div>

          {/* 3. 预览反馈结果 */}
          {previewData ? (
            <Alert
              type={previewData.subscribed ? 'warning' : 'success'}
              showIcon
              style={{ marginBottom: 16 }}
              message={
                <Space>
                  <Text strong>{previewData.title || '(无标题)'}</Text>
                  {previewData.subscribed ? <Tag color="warning">该源已在列表中</Tag> : <Tag color="success">解析有效</Tag>}
                </Space>
              }
              description={
                <div style={{ marginTop: 4, fontSize: 12 }}>
                  {previewData.siteLink && (
                    <div>
                      <Text type="secondary">主页: </Text>
                      <a href={previewData.siteLink} target="_blank" rel="noreferrer">
                        {previewData.siteLink}
                      </a>
                    </div>
                  )}
                  {previewData.description && (
                    <Text type="secondary" ellipsis style={{ display: 'block', marginTop: 2 }}>
                      {previewData.description}
                    </Text>
                  )}
                </div>
              }
            />
          ) : null}

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="自定义源名称（可选）">
                <Input placeholder="留空则自动提取源标题" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="folder_id" label="归入分类目录" initialValue={0}>
                <Select options={folderOptions} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* —— 编辑 modal —— */}
      <Modal
        title="编辑订阅源"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEditSubmit}
        okText="保存"
        cancelText="取消"
        width={600}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="subscribe_url" label="订阅地址">
            <Input disabled />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="folder_id" label="所在分类目录">
            <Select options={folderOptions} />
          </Form.Item>
          <Form.Item
            name="fetch_interval_minutes"
            label="抓取间隔（分钟）"
          >
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>
          <Space size="large">
            <Form.Item name="enabled" label="启用抓取" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item
              name="crawl_full_content"
              label="深度抓取全文"
              valuePropName="checked"
              tooltip="开启后将尝试自动解析文章正文完整内容"
            >
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* —— 文件夹管理 modal —— */}
      <Modal
        title={
          <Space>
            <FolderOpenOutlined style={{ color: '#1890ff' }} />
            <span>资讯分类目录管理</span>
          </Space>
        }
        open={folderOpen}
        onCancel={() => setFolderOpen(false)}
        footer={null}
        width={540}
      >
        <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
          <Input
            placeholder="输入新分类名称 (如：A股快讯、量化研究)"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onPressEnter={handleAddFolder}
          />
          <Button type="primary" icon={<FolderAddOutlined />} onClick={handleAddFolder}>
            新建分类
          </Button>
        </Space.Compact>

        <Table<HuntlyFolder>
          rowKey={(f) => String(f.id ?? 0)}
          size="small"
          pagination={false}
          dataSource={folders.filter((f) => f.id != null)}
          columns={[
            {
              title: '分类名称',
              dataIndex: 'name',
              key: 'name',
              render: (n) => <Tag color={getFolderTagColor(n || '')}>{n}</Tag>,
            },
            {
              title: '包含订阅源',
              key: 'count',
              width: 110,
              align: 'right',
              render: (_, f) => <Text strong>{(f.connectors || []).length} 个</Text>,
            },
            {
              title: '操作',
              key: 'actions',
              width: 140,
              align: 'center',
              render: (_, f) => (
                <Space>
                  <Button size="small" type="link" onClick={() => handleRenameFolder(f)}>
                    重命名
                  </Button>
                  <Popconfirm
                    title={`确定删除分类「${f.name}」？所属订阅源将移入「未分组」`}
                    onConfirm={() => handleDeleteFolder(f)}
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    cancelText="取消"
                  >
                    <Button size="small" type="link" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
};

export default AdminRssSources;
