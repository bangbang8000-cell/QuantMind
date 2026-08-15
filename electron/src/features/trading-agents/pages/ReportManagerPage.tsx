/**
 * 股票报告（Stock Report）— 分析报告档案库 + PDF 预览
 *
 * 左栏：报告文件管理（文件夹 + 文件列表 + 多选删除 + 新建文件夹）
 * 右栏：选中 PDF 的 PdfPreview（PDF.js 渲染，白底无缩略图栏）
 * 顶部：引导横幅（提示用户先通过 QuantBot 技能生成报告）
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  FileText,
  FolderPlus,
  Folder,
  Trash2,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  File as FileIcon,
  Info,
} from 'lucide-react';
import PdfPreview from '../components/PdfPreview';

const ENGINE_BASE = '/api/v1/trading-agents';

/** PDF 预览错误边界：单个 PDF 渲染失败不拖垮整个页面 */
class PdfErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: string | null }> {
  state = { error: null as string | null };

  static getDerivedStateFromError(err: any) {
    return { error: err?.message || String(err) };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ textAlign: 'center', padding: 60, color: '#ef4444', fontSize: 13 }}>
          ⚠️ PDF 渲染失败：{this.state.error}
          <br />
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: 16, padding: '6px 16px', border: '1px solid #e5e7eb', borderRadius: 6, background: '#fff', cursor: 'pointer' }}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface ReportFile {
  filename: string;
  ticker: string;
  date: string;
  time?: string;
  name: string;
  signal: string | null;
  size: number;
  modified: number;
}

interface ReportFolder {
  name: string;
  files: ReportFile[];
}

interface FileListResponse {
  root: string;
  folders: ReportFolder[];
  files: ReportFile[];
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${ENGINE_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `Request failed: ${resp.status}`);
  }
  const data = await resp.json();
  return data.data ?? data;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const SIGNAL_COLORS: Record<string, string> = {
  Buy: '#10b981',
  Overweight: '#22c55e',
  Hold: '#f59e0b',
  Underweight: '#ef4444',
  Sell: '#dc2626',
};

const ReportManagerPage: React.FC = () => {
  const [list, setList] = useState<FileListResponse>({ root: '', folders: [], files: [] });
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null); // 当前预览的文件
  const [selectedForDelete, setSelectedForDelete] = useState<Set<string>>(new Set<string>());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set<string>());
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [error, setError] = useState('');
  const [previewKey, setPreviewKey] = useState(0); // 用于刷新 iframe
  const [bannerDismissed, setBannerDismissed] = useState(false); // 引导横幅已关闭
  const [showMoveFolder, setShowMoveFolder] = useState(false); // 移动到文件夹弹层
  const [moveTarget, setMoveTarget] = useState('');

  const loadFiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await request<FileListResponse>('/files/list');
      setList(data);
      setSelectedForDelete(new Set());
      setError('');
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  // 解析文件归属（根目录或某文件夹）
  const rootFiles = list.files;
  const allFolders = list.folders;

  const toggleExpand = (folder: string) => {
    (setExpandedFolders as any)((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(folder)) next.delete(folder);
      else next.add(folder);
      return next;
    });
  };

  const toggleSelect = (filename: string) => {
    (setSelectedForDelete as any)((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  const handlePreview = (filename: string) => {
    setSelected(filename);
    (setPreviewKey as any)((k: number) => k + 1);
  };

  const handleCreateFolder = async () => {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await request('/files/create-folder', {
        method: 'POST',
        body: JSON.stringify({ folder: name }),
      });
      setNewFolderName('');
      setShowNewFolder(false);
      (setExpandedFolders as any)((prev: Set<string>) => new Set(prev).add(name));
      await loadFiles();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedForDelete.size === 0) return;
    if (!window.confirm(`确认删除选中的 ${selectedForDelete.size} 个文件？`)) return;
    try {
      await request('/files/delete', {
        method: 'POST',
        body: JSON.stringify({ files: Array.from(selectedForDelete) }),
      });
      if (selected && selectedForDelete.has(selected)) setSelected(null);
      await loadFiles();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleMoveSelected = async () => {
    if (selectedForDelete.size === 0 || !moveTarget) return;
    try {
      await request('/files/move', {
        method: 'POST',
        body: JSON.stringify({ files: Array.from(selectedForDelete), target_folder: moveTarget }),
      });
      if (selected && selectedForDelete.has(selected)) setSelected(null);
      setShowMoveFolder(false);
      setMoveTarget('');
      await loadFiles();
    } catch (err: any) {
      setError(err.message);
    }
  };

  // 文件总数（用于判断是否显示引导）
  const totalFiles = rootFiles.length + allFolders.reduce((s, f) => s + f.files.length, 0);
  const showBanner = !bannerDismissed && totalFiles === 0;

  const handleDeleteFolder = async (folder: string) => {
    if (!window.confirm(`确认删除文件夹「${folder}」及其中所有文件？`)) return;
    try {
      await request('/files/delete-folder', {
        method: 'POST',
        body: JSON.stringify({ folder }),
      });
      await loadFiles();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const renderFileItem = (file: ReportFile, indent = 0) => {
    const isPdf = file.filename.toLowerCase().endsWith('.pdf');
    return (
      <div
        key={file.filename}
        onClick={() => isPdf && handlePreview(file.filename)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '7px 12px 7px',
          marginLeft: indent,
          cursor: isPdf ? 'pointer' : 'default',
          background: selected === file.filename ? '#eef2ff' : 'transparent',
          borderRadius: 8,
          transition: 'background 0.15s',
        }}
      >
        <input
          type="checkbox"
          checked={selectedForDelete.has(file.filename)}
          onChange={(e) => {
            e.stopPropagation();
            toggleSelect(file.filename);
          }}
          style={{ accentColor: '#6366f1', flexShrink: 0 }}
        />
        {isPdf ? (
          <FileText style={{ width: 15, height: 15, color: '#ef4444', flexShrink: 0 }} />
        ) : (
          <FileIcon style={{ width: 15, height: 15, color: '#94a3b8', flexShrink: 0 }} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {file.ticker || file.name.split('_')[0] || file.filename}
          </div>
          <div style={{ fontSize: 10, color: '#94a3b8' }}>
            {file.date || ''} {formatTime(file.modified)}
          </div>
        </div>
        {file.signal && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: 4,
              color: '#fff',
              background: SIGNAL_COLORS[file.signal] || '#6366f1',
              flexShrink: 0,
            }}
          >
            {file.signal}
          </span>
        )}
        <span style={{ fontSize: 10, color: '#cbd5e1', flexShrink: 0 }}>{formatSize(file.size)}</span>
      </div>
    );
  };

  return (
    <div style={{
      minHeight: '100%',
      background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
      color: '#1e293b',
      fontFamily: "'Inter', -apple-system, sans-serif",
    }}>
      <div style={{
        maxWidth: 1500,
        margin: '0 auto',
        padding: '16px 20px 28px',
      }}>
        {/* ── 顶部引导横幅（仅无文件时显示，可关闭）── */}
        {showBanner && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            marginBottom: 14,
            background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
            borderRadius: 8,
            color: '#fff',
          }}>
            <Info style={{ width: 14, height: 14, flexShrink: 0 }} />
            <div style={{ fontSize: 12, lineHeight: 1.5, flex: 1 }}>
              在 <b>QuantBot</b> 输入「深度分析某只股票」（如：深度分析 002594 比亚迪），
              分析完成后自动导出 md + PDF 报告，即显示在左侧。
            </div>
            <button
              onClick={() => setBannerDismissed(true)}
              style={{
                border: 'none',
                background: 'rgba(255,255,255,0.25)',
                color: '#fff',
                borderRadius: 6,
                width: 20,
                height: 20,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontSize: 12,
                flexShrink: 0,
              }}
              title="关闭提示"
            >
              ✕
            </button>
          </div>
        )}

        <div style={{ display: 'flex', gap: 18, alignItems: 'stretch' }}>
          {/* ── 左栏：文件管理 ── */}
          <div style={{
            width: 340,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            background: 'rgba(255,255,255,0.9)',
            borderRadius: 14,
            border: '1px solid rgba(199,210,254,0.6)',
            backdropFilter: 'blur(8px)',
            overflow: 'hidden',
          }}>
            {/* 左栏标题 + 工具栏 */}
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #e0e7ff' }}>
              <div style={{ fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileText style={{ width: 18, height: 18, color: '#6366f1' }} />
                分析报告
                <button
                  onClick={loadFiles}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    marginLeft: 'auto',
                    border: 'none',
                    background: 'transparent',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    padding: 2,
                  }}
                  title="刷新列表"
                >
                  <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
                <span style={{
                  fontSize: 11,
                  background: '#eef2ff',
                  color: '#6366f1',
                  padding: '2px 8px',
                  borderRadius: 6,
                }}>
                  {rootFiles.length + allFolders.reduce((s, f) => s + f.files.length, 0)} 份
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                <button
                  onClick={() => setShowNewFolder(!showNewFolder)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 10px',
                    background: '#eef2ff',
                    border: 'none',
                    borderRadius: 7,
                    color: '#6366f1',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <FolderPlus style={{ width: 13, height: 13 }} /> 新建文件夹
                </button>
                <button
                  onClick={handleDeleteSelected}
                  disabled={selectedForDelete.size === 0}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 10px',
                    background: selectedForDelete.size ? '#fee2e2' : '#f1f5f9',
                    border: 'none',
                    borderRadius: 7,
                    color: selectedForDelete.size ? '#dc2626' : '#94a3b8',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: selectedForDelete.size ? 'pointer' : 'not-allowed',
                  }}
                >
                  <Trash2 style={{ width: 13, height: 13 }} /> 删除({selectedForDelete.size})
                </button>
                <button
                  onClick={() => setShowMoveFolder(!showMoveFolder)}
                  disabled={selectedForDelete.size === 0}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 10px',
                    background: selectedForDelete.size ? '#eef2ff' : '#f1f5f9',
                    border: 'none',
                    borderRadius: 7,
                    color: selectedForDelete.size ? '#6366f1' : '#94a3b8',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: selectedForDelete.size ? 'pointer' : 'not-allowed',
                  }}
                >
                  <Folder style={{ width: 13, height: 13 }} /> 移动
                </button>
              </div>
              {showMoveFolder && (
                <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center' }}>
                  <select
                    value={moveTarget}
                    onChange={(e) => setMoveTarget(e.target.value)}
                    style={{
                      flex: 1,
                      padding: '5px 10px',
                      border: '1px solid #c7d2fe',
                      borderRadius: 7,
                      fontSize: 12,
                      outline: 'none',
                      background: '#fff',
                    }}
                  >
                    <option value="">选择目标文件夹...</option>
                    {allFolders.map((f) => (
                      <option key={f.name} value={f.name}>{f.name}</option>
                    ))}
                  </select>
                  <button
                    onClick={handleMoveSelected}
                    disabled={!moveTarget}
                    style={{
                      padding: '5px 12px',
                      background: moveTarget ? '#6366f1' : '#cbd5e1',
                      border: 'none',
                      borderRadius: 7,
                      color: '#fff',
                      fontSize: 11,
                      cursor: moveTarget ? 'pointer' : 'not-allowed',
                    }}
                  >
                    移动
                  </button>
                </div>
              )}
              {showNewFolder && (
                <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                  <input
                    value={newFolderName}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
                    placeholder="文件夹名"
                    style={{
                      flex: 1,
                      padding: '5px 10px',
                      border: '1px solid #c7d2fe',
                      borderRadius: 7,
                      fontSize: 12,
                      outline: 'none',
                    }}
                  />
                  <button
                    onClick={handleCreateFolder}
                    style={{
                      padding: '5px 12px',
                      background: '#6366f1',
                      border: 'none',
                      borderRadius: 7,
                      color: '#fff',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    创建
                  </button>
                </div>
              )}
            </div>

            {/* 文件列表 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '10px 8px' }}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 13 }}>
                  加载中...
                </div>
              ) : (
                <>
                  {/* 根目录文件（未分类） */}
                  {rootFiles.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: '#6366f1', padding: '4px 12px', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        全部报告
                      </div>
                      {rootFiles.map((f) => renderFileItem(f))}
                    </div>
                  )}

                  {/* 文件夹 */}
                  {allFolders.map((folder) => (
                    <div key={folder.name} style={{ marginBottom: 8 }}>
                      <div
                        onClick={() => toggleExpand(folder.name)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '6px 12px',
                          cursor: 'pointer',
                          borderRadius: 8,
                          fontSize: 13,
                          fontWeight: 600,
                          color: '#334155',
                        }}
                      >
                        {expandedFolders.has(folder.name) ? (
                          <ChevronDown style={{ width: 14, height: 14, color: '#94a3b8' }} />
                        ) : (
                          <ChevronRight style={{ width: 14, height: 14, color: '#94a3b8' }} />
                        )}
                        <Folder style={{ width: 15, height: 15, color: '#f59e0b' }} />
                        <span style={{ flex: 1 }}>{folder.name}</span>
                        <span style={{ fontSize: 10, color: '#94a3b8' }}>{folder.files.length}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteFolder(folder.name);
                          }}
                          style={{
                            border: 'none',
                            background: 'transparent',
                            color: '#cbd5e1',
                            cursor: 'pointer',
                            padding: 2,
                          }}
                          title={`删除 ${folder.name}`}
                        >
                          <Trash2 style={{ width: 12, height: 12 }} />
                        </button>
                      </div>
                      {expandedFolders.has(folder.name) && (
                        <div style={{ marginTop: 2 }}>
                          {folder.files.map((f) => renderFileItem(f, 12))}
                        </div>
                      )}
                    </div>
                  ))}

                  {rootFiles.length === 0 && allFolders.length === 0 && (
                    <div style={{ textAlign: 'center', padding: 40 }}>
                      <FileText style={{ width: 40, height: 40, color: '#c7d2fe', margin: '0 auto 12px' }} />
                      <div style={{ fontSize: 13, color: '#64748b', lineHeight: 1.6 }}>
                        暂无分析报告<br />
                        <span style={{ fontSize: 11, color: '#94a3b8' }}>
                          去 QuantBot 深度分析股票，分析完成后自动导出 PDF 显示在这里
                        </span>
                      </div>
                    </div>
                  )}
                </>
              )}
              {error && (
                <div style={{ padding: 12, color: '#dc2626', fontSize: 12 }}>
                  ⚠️ {error}
                </div>
              )}
            </div>

            {/* 底部提示 */}
            <div style={{
              padding: '10px 16px',
              borderTop: '1px solid #e0e7ff',
              fontSize: 10,
              color: '#94a3b8',
              lineHeight: 1.5,
            }}>
              提示：勾选文件可多选删除；分析完成后 md + PDF 自动归档到对应市场文件夹。
            </div>
          </div>

          {/* ── 右栏：PDF 预览 ── */}
          <div style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            background: 'rgba(255,255,255,0.85)',
            borderRadius: 14,
            border: '1px solid rgba(199,210,254,0.6)',
            backdropFilter: 'blur(8px)',
            overflow: 'hidden',
            minHeight: '88vh',
          }}>
            {selected ? (
              <>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 14px',
                  borderBottom: '1px solid #e5e7eb',
                  background: '#ffffff',
                }}>
                  <FileText style={{ width: 15, height: 15, color: '#6366f1' }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: '#1e293b' }}>{selected}</span>
                  <a
                    href={`${ENGINE_BASE}/files/pdf/${encodeURIComponent(selected)}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      marginLeft: 'auto',
                      padding: '4px 10px',
                      background: '#6366f1',
                      color: '#fff',
                      borderRadius: 6,
                      fontSize: 11,
                      textDecoration: 'none',
                    }}
                  >
                    新窗口打开
                  </a>
                </div>
                <PdfErrorBoundary>
                  <PdfPreview
                    key={previewKey}
                    url={`${ENGINE_BASE}/files/pdf/${encodeURIComponent(selected)}`}
                    filename={selected}
                  />
                </PdfErrorBoundary>
              </>
            ) : (
              <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                textAlign: 'center',
                padding: 40,
              }}>
                <div style={{
                  width: 72,
                  height: 72,
                  borderRadius: 20,
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: 16,
                  boxShadow: '0 8px 24px rgba(99,102,241,0.3)',
                }}>
                  <FileText style={{ width: 32, height: 32, color: '#fff' }} />
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>
                  选择左侧报告查看 PDF 预览
                </div>
                <div style={{ fontSize: 13, color: '#64748b', maxWidth: 360, lineHeight: 1.7 }}>
                  在 QuantBot 中输入「深度分析某只股票」，分析完成后自动导出 md + PDF，
                  这里就能预览完整分析内容（7 分析师 → 多空辩论 → 风控评估 → 最终决策）。
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportManagerPage;
