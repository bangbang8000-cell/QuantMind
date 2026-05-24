/**
 * NewsPage — 后台管理 → 资讯源 / 财务事件
 * 三栏自适应布局：
 *   左：Huntly 文件夹 / 订阅源树（可折叠）
 *   中：文章流（弹性宽度）
 *   右：正文（弹性宽度，最小 420，最大 600）
 * 轮询：10s 抓最新一页，HeaderBar 显示 "上次同步：X 秒前"
 * 数据来源: QuantMind 后端 /api/v1/news/* (代理 Huntly)
 */

import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  Badge,
  Button,
  Empty,
  Input,
  List,
  Segmented,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Tree,
  message,
} from 'antd';
import {
  BellOutlined,
  FireOutlined,
  GlobalOutlined,
  LinkOutlined,
  ReloadOutlined,
  StarFilled,
  StarOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import {
  NewsArticle,
  NewsArticleDetail,
  NewsFolder,
  NewsHealthInfo,
  NewsSource,
  newsService,
} from '../services/newsService';

const { Text, Title, Paragraph } = Typography;

const POLL_INTERVAL_MS = 10_000;

type FeedMode = 'all' | 'events' | 'starred';
type SelectionKey = 'all' | `folder-${number}` | `source-${number}`;

const formatRelative = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 5) return '刚刚';
  if (diff < 60) return `${Math.floor(diff)}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}天前`;
  return d.toLocaleDateString('zh-CN');
};

export const NewsPanel: React.FC = () => {
  const [health, setHealth] = useState<NewsHealthInfo | null>(null);
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [folders, setFolders] = useState<NewsFolder[]>([]);
  const [selection, setSelection] = useState<SelectionKey>('all');
  const [feedMode, setFeedMode] = useState<FeedMode>('all');
  const [keyword, setKeyword] = useState('');

  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [latestPublishedAt, setLatestPublishedAt] = useState<string | null>(null);
  const [lastSyncTick, setLastSyncTick] = useState<number>(Date.now());

  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);
  const [articleDetail, setArticleDetail] = useState<NewsArticleDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>(['all']);
  const [_, forceTick] = useState(0); // 强制时间标签 1s 重渲染
  const pollTimer = useRef<number | null>(null);

  // —— 数据拉取 ——
  const checkHealth = useCallback(async () => {
    try {
      setHealth(await newsService.health());
    } catch {
      setHealth({ huntly_status: 'unreachable', huntly_base_url: '?' });
    }
  }, []);

  const loadSources = useCallback(async () => {
    try {
      const { sources, folders } = await newsService.listSources();
      setSources(sources);
      setFolders(folders);
    } catch {
      setSources([]);
      setFolders([]);
    }
  }, []);

  const loadArticles = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {
        keyword: keyword || undefined,
        only_financial_event: feedMode === 'events',
        page: 1,
        page_size: 50,
      };
      if (selection.startsWith('source-')) {
        params.source_id = Number(selection.slice('source-'.length));
      } else if (selection.startsWith('folder-')) {
        params.folder_id = Number(selection.slice('folder-'.length));
      }
      const r = await newsService.listArticles(params);
      let list = r.articles ?? [];
      if (feedMode === 'starred') list = list.filter((a) => a.starred);
      setArticles(list);
      setLatestPublishedAt(r.latest_published_at ?? null);
      setLastSyncTick(Date.now());
    } catch {
      setArticles([]);
    } finally {
      setLoading(false);
    }
  }, [selection, keyword, feedMode]);

  useEffect(() => {
    checkHealth();
    loadSources();
  }, [checkHealth, loadSources]);

  useEffect(() => {
    loadArticles();
    if (pollTimer.current) window.clearInterval(pollTimer.current);
    pollTimer.current = window.setInterval(() => {
      loadArticles();
      loadSources();
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    };
  }, [loadArticles, loadSources]);

  // 1s tick for relative-time labels
  useEffect(() => {
    const t = window.setInterval(() => forceTick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (selectedArticleId == null) {
      setArticleDetail(null);
      return;
    }
    setDetailLoading(true);
    newsService
      .getArticle(selectedArticleId)
      .then((d) => {
        setArticleDetail(d);
        if (!d.read) newsService.markRead(selectedArticleId, true).catch(() => undefined);
      })
      .catch(() => setArticleDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedArticleId]);

  // —— 派生数据 ——
  const totalUnread = useMemo(
    () => sources.reduce((acc, s) => acc + (s.unread_count || 0), 0),
    [sources],
  );

  const treeData: DataNode[] = useMemo(() => {
    const allUnread = totalUnread;
    const folderMap = new Map<number, NewsSource[]>();
    sources.forEach((s) => {
      const fid = s.folder_id ?? 0;
      if (!folderMap.has(fid)) folderMap.set(fid, []);
      folderMap.get(fid)!.push(s);
    });
    const folderNodes: DataNode[] = folders.map((f) => {
      const items = folderMap.get(f.folder_id) || [];
      return {
        key: `folder-${f.folder_id}`,
        title: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>
              {f.folder_name || '未分组'}
            </span>
            <Text type="secondary" style={{ fontSize: 10 }}>{items.length}</Text>
            {f.unread_count > 0 && <Badge count={f.unread_count} size="small" />}
          </div>
        ),
        children: items.map((s) => ({
          key: `source-${s.source_id}`,
          title: (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
                {s.source_name}
              </span>
              {(s.unread_count ?? 0) > 0 && <Badge count={s.unread_count} size="small" />}
            </div>
          ),
          isLeaf: true,
        })),
      };
    });
    return [
      {
        key: 'all',
        title: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ flex: 1, fontWeight: 600 }}>全部</span>
            {allUnread > 0 && <Badge count={allUnread} size="small" style={{ backgroundColor: '#6366f1' }} />}
          </div>
        ),
        isLeaf: true,
      },
      ...folderNodes,
    ];
  }, [sources, folders, totalUnread]);

  // —— 默认展开所有 folder ——
  useEffect(() => {
    if (folders.length > 0 && expandedKeys.length <= 1) {
      setExpandedKeys(['all', ...folders.map((f) => `folder-${f.folder_id}`)]);
    }
  }, [folders]);

  const handleStar = useCallback(async (article: NewsArticle, ev: React.MouseEvent) => {
    ev.stopPropagation();
    const next = !article.starred;
    try {
      await newsService.toggleStar(article.id, next);
      setArticles((prev) => prev.map((a) => (a.id === article.id ? { ...a, starred: next } : a)));
      if (selectedArticleId === article.id && articleDetail) {
        setArticleDetail({ ...articleDetail, starred: next });
      }
    } catch {
      message.error('操作失败');
    }
  }, [selectedArticleId, articleDetail]);

  const handleRefreshAll = useCallback(async () => {
    message.loading({ content: '正在抓取最新资讯...', key: 'news-refresh', duration: 0 });
    try {
      // 简单触发：刷新文章列表 + 来源列表
      await Promise.all([loadArticles(), loadSources()]);
      message.success({ content: '已刷新', key: 'news-refresh' });
    } catch {
      message.error({ content: '刷新失败', key: 'news-refresh' });
    }
  }, [loadArticles, loadSources]);

  // —— 渲染 ——
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: 'calc(100vh - 120px)',
        minHeight: 720,
        background: '#ffffff',
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid #e2e8f0',
      }}
    >
      {/* 顶部工具栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '14px 20px',
          gap: 14,
          borderBottom: '1px solid #e2e8f0',
          background: 'linear-gradient(180deg, #fafbff 0%, #f8fafc 100%)',
          flexWrap: 'wrap',
        }}
      >
        <BellOutlined style={{ color: '#6366f1', fontSize: 20 }} />
        <Title level={5} style={{ margin: 0, fontSize: 16 }}>
          资讯监控
        </Title>
        <Tag color={health?.huntly_status === 'up' ? 'green' : 'red'} style={{ margin: 0 }}>
          {health?.huntly_status === 'up' ? 'Huntly 已连接' : '未连接'}
        </Tag>
        <Tooltip title={latestPublishedAt ? `最新一条发布于 ${new Date(latestPublishedAt).toLocaleString('zh-CN')}` : '暂无文章'}>
          <Tag icon={<SyncOutlined spin={loading} />} color="processing" style={{ margin: 0 }}>
            最新：{formatRelative(latestPublishedAt)}
          </Tag>
        </Tooltip>
        <Tooltip title={`上次轮询：${new Date(lastSyncTick).toLocaleTimeString('zh-CN')}（每 ${POLL_INTERVAL_MS / 1000}s 自动）`}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            同步 {formatRelative(new Date(lastSyncTick).toISOString())}
          </Text>
        </Tooltip>
        <Badge count={totalUnread} overflowCount={9999} style={{ backgroundColor: '#6366f1' }} />

        <Segmented
          size="small"
          value={feedMode}
          onChange={(v) => setFeedMode(v as FeedMode)}
          options={[
            { label: <span><GlobalOutlined /> 全部</span>, value: 'all' },
            { label: <span><ThunderboltOutlined /> 财务事件</span>, value: 'events' },
            { label: <span><FireOutlined /> 收藏</span>, value: 'starred' },
          ]}
          style={{ marginLeft: 8 }}
        />
        <Input.Search
          allowClear
          size="small"
          placeholder="搜索标题..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onSearch={() => loadArticles()}
          style={{ width: 260 }}
        />
        <div style={{ flex: 1 }} />
        <Tooltip title="立即刷新">
          <Button
            size="small"
            type="primary"
            ghost
            icon={<ReloadOutlined spin={loading} />}
            onClick={handleRefreshAll}
          >
            刷新
          </Button>
        </Tooltip>
        {health?.huntly_base_url && (
          <Tooltip title="打开 Huntly 后台管理订阅源">
            <a
              href={health.huntly_base_url.replace('http://quantmind-huntly', `http://${window.location.hostname}:8090`)}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 12, color: '#6366f1', whiteSpace: 'nowrap' }}
            >
              <LinkOutlined /> Huntly 后台
            </a>
          </Tooltip>
        )}
      </div>

      {/* 主体三栏 - 自适应弹性 */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        {/* 左：文件夹 / 订阅源树 */}
        <div
          style={{
            flex: '0 0 18%',
            minWidth: 240,
            maxWidth: 380,
            borderRight: '1px solid #e2e8f0',
            overflowY: 'auto',
            padding: '8px 6px',
            background: '#fafafa',
          }}
        >
          {treeData.length <= 1 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ color: '#64748b', fontSize: 12 }}>无订阅源</span>}
              style={{ marginTop: 60 }}
            />
          ) : (
            <Tree
              blockNode
              treeData={treeData}
              selectedKeys={[selection]}
              expandedKeys={expandedKeys}
              expandAction="doubleClick"
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={(keys, info) => {
                // 点击同一节点 antd 会清空 selectedKeys，这里取被点击节点的 key 保证选中
                const clicked = (info?.node as any)?.key as SelectionKey | undefined;
                const next = (keys[0] as SelectionKey) || clicked;
                if (!next) return;
                setSelection(next);
              }}
              style={{ background: 'transparent', fontSize: 13 }}
            />
          )}
        </div>

        {/* 中：文章流 */}
        <div
          style={{
            flex: 1,
            minWidth: 360,
            overflowY: 'auto',
            borderRight: '1px solid #e2e8f0',
          }}
        >
          {loading && articles.length === 0 ? (
            <div style={{ padding: 80, textAlign: 'center' }}><Spin /></div>
          ) : articles.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: '#64748b', fontSize: 13 }}>
                  {health?.huntly_status === 'up'
                    ? '暂无文章 · 请在右上角 "Huntly 后台" 添加 RSS / Twitter / GitHub 订阅源'
                    : `资讯服务未连接 (${health?.huntly_base_url || ''})`}
                </span>
              }
              style={{ marginTop: 80 }}
            />
          ) : (
            <List
              size="small"
              dataSource={articles}
              renderItem={(a) => {
                const active = selectedArticleId === a.id;
                return (
                  <List.Item
                    style={{
                      padding: '12px 18px',
                      cursor: 'pointer',
                      background: active ? 'rgba(99,102,241,0.08)' : 'transparent',
                      borderBottom: '1px solid #f1f5f9',
                      borderLeft: active ? '3px solid #6366f1' : '3px solid transparent',
                      opacity: a.read && !active ? 0.7 : 1,
                    }}
                    onClick={() => setSelectedArticleId(a.id)}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'start', gap: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                            {a.is_financial_event && (
                              <Tag color="gold" style={{ margin: 0, fontSize: 10, padding: '0 6px', lineHeight: '16px' }}>
                                <ThunderboltOutlined /> 事件
                              </Tag>
                            )}
                            <Text style={{ fontSize: 14, fontWeight: a.read ? 400 : 600, lineHeight: 1.4 }}>
                              {a.title}
                            </Text>
                          </div>
                          {a.summary && (
                            <Text style={{ color: '#64748b', fontSize: 12, display: 'block', lineHeight: 1.55 }}>
                              {a.summary.length > 160 ? `${a.summary.slice(0, 160)}...` : a.summary}
                            </Text>
                          )}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
                            <span>{a.source_name || '未知来源'}</span>
                            <span>·</span>
                            <span>{formatRelative(a.published_at)}</span>
                          </div>
                        </div>
                        <Button
                          type="text"
                          size="small"
                          icon={a.starred ? <StarFilled style={{ color: '#fbbf24' }} /> : <StarOutlined style={{ color: '#94a3b8' }} />}
                          onClick={(e) => handleStar(a, e)}
                        />
                      </div>
                    </div>
                  </List.Item>
                );
              }}
            />
          )}
        </div>

        {/* 右：正文 */}
        <div
          style={{
            flex: '0 0 38%',
            minWidth: 420,
            maxWidth: 720,
            overflowY: 'auto',
            padding: 24,
            background: '#fcfcfd',
          }}
        >
          {detailLoading ? (
            <div style={{ padding: 80, textAlign: 'center' }}><Spin /></div>
          ) : !articleDetail ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ color: '#64748b', fontSize: 12 }}>选择左侧文章查看正文</span>}
              style={{ marginTop: 80 }}
            />
          ) : (
            <div>
              <Title level={4} style={{ marginTop: 0, lineHeight: 1.4 }}>
                {articleDetail.title}
              </Title>
              <div style={{ marginBottom: 14, fontSize: 12, color: '#64748b' }}>
                {articleDetail.source_name} · {formatRelative(articleDetail.published_at)}
                {articleDetail.url && (
                  <a
                    href={articleDetail.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ marginLeft: 10, color: '#6366f1' }}
                  >
                    <LinkOutlined /> 原文
                  </a>
                )}
              </div>
              {articleDetail.is_financial_event && (
                <Tag color="gold" icon={<ThunderboltOutlined />} style={{ marginBottom: 14 }}>
                  财务事件
                </Tag>
              )}
              {articleDetail.content_html ? (
                <div
                  className="news-content"
                  style={{ fontSize: 14, lineHeight: 1.75 }}
                  dangerouslySetInnerHTML={{ __html: articleDetail.content_html }}
                />
              ) : (
                <Paragraph style={{ fontSize: 14, lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>
                  {articleDetail.content || articleDetail.summary || '(正文为空)'}
                </Paragraph>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default NewsPanel;
