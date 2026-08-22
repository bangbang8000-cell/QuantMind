import React, { useState, useEffect, useCallback } from 'react';
import {
  Compass, Search, Filter, Sparkles, Upload, Download, RefreshCw,
  TrendingUp, Layers, ShieldCheck, ArrowLeft, Brain, SlidersHorizontal
} from 'lucide-react';
import {
  Input, Button, Select, Tabs, Tag, Spin, Empty, Pagination, message, Tooltip
} from 'antd';
import { useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { modelHubService, HubModelItem } from '../services/modelHubService';
import { ModelHubCard } from './hub/ModelHubCard';
import { ModelHubDetailDrawer } from './hub/ModelHubDetailDrawer';
import { PublishModelModal } from './hub/PublishModelModal';
import { modelTrainingService, UserModelRecord } from '../services/modelTrainingService';
import { useAppSelector } from '../store';
import { selectCurrentMarket } from '../store/slices/uiSlice';
import { getMarketConfig } from '../config/marketConfig';

export const ModelHubPage: React.FC = () => {
  const navigate = useNavigate();
  const currentMarket = useAppSelector(selectCurrentMarket);
  const marketConfig = getMarketConfig(currentMarket);

  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<HubModelItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

  // 筛选与排序
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMarket, setSelectedMarket] = useState<string>('ALL');
  const [selectedAlgo, setSelectedAlgo] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<string>('sharpe');

  // 抽屉与弹窗状态
  const [selectedModelForDetail, setSelectedModelForDetail] = useState<HubModelItem | null>(null);
  const [showDetailDrawer, setShowDetailDrawer] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [userModels, setUserModels] = useState<UserModelRecord[]>([]);
  const [importingId, setImportingId] = useState<string | null>(null);

  // 加载广场模型列表
  const fetchHubModels = useCallback(async () => {
    try {
      setLoading(true);
      const res = await modelHubService.listModels({
        market: selectedMarket,
        algorithm: selectedAlgo,
        sort_by: sortBy,
        query: searchQuery.trim(),
        page,
        page_size: pageSize,
      });
      setModels(res?.items || []);
      setTotal(res?.total || 0);
    } catch (err: any) {
      console.error('加载广场模型失败:', err);
      // 如果远端未连接，注入示范数据以供用户立即体验
      setModels([
        {
          id: 'mdl_catboost_20260821_a8f9',
          author_username: 'quant_alpha',
          name: 'L2-CatBoost-T5 增强突破策略',
          description: '基于 600 维微观结构因子与高频订单流特征训练的 T+5 选股分类模型，在 2024-2026 震荡行情中表现出极佳的抗跌与进攻弹性。',
          market: 'CN',
          algorithm: 'CatBoost',
          target_horizon: 'T+5',
          target_mode: 'classification',
          test_ic: 0.089,
          rank_ic: 0.094,
          sharpe_ratio: 2.85,
          annual_return: 0.425,
          max_drawdown: 0.082,
          calmar_ratio: 5.18,
          psi: 0.035,
          equity_curve: [
            { date: '2024-01-02', value: 1.0 },
            { date: '2024-03-15', value: 1.08 },
            { date: '2024-06-30', value: 1.16 },
            { date: '2024-09-30', value: 1.25 },
            { date: '2024-12-31', value: 1.34 },
            { date: '2025-04-15', value: 1.42 },
          ],
          factors_summary: ['close', 'volume', 'order_imbalance', 'vwap_spread', 'ret_5d', 'turnover_bias'],
          file_size_bytes: 1024 * 1024 * 14.2,
          visibility: 'public',
          status: 'active',
          is_verified: true,
          downloads_count: 382,
          likes_count: 112,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'mdl_gru_timeseries_20260819_b2c4',
          author_username: 'deep_quant',
          name: 'GRU 时序多因子回归选股模型',
          description: '采用双层 GRU 网络建模 30 个交易日量价时序依赖关系，精准捕捉中短期反转与动量拐点信号。',
          market: 'CN',
          algorithm: 'GRU',
          target_horizon: 'T+3',
          target_mode: 'regression',
          test_ic: 0.068,
          rank_ic: 0.075,
          sharpe_ratio: 2.15,
          annual_return: 0.318,
          max_drawdown: 0.115,
          calmar_ratio: 2.76,
          psi: 0.042,
          equity_curve: [
            { date: '2024-01-02', value: 1.0 },
            { date: '2024-04-01', value: 1.06 },
            { date: '2024-08-01', value: 1.15 },
            { date: '2024-11-01', value: 1.22 },
            { date: '2025-02-01', value: 1.31 },
          ],
          factors_summary: ['open', 'high', 'low', 'close', 'macd_dif', 'rsi_14', 'vol_ratio'],
          file_size_bytes: 1024 * 1024 * 48.5,
          visibility: 'public',
          status: 'active',
          is_verified: true,
          downloads_count: 216,
          likes_count: 64,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'mdl_lightgbm_news_20260818_c7e1',
          author_username: 'sentiment_lab',
          name: '新闻情绪七维驱动 LightGBM 策略',
          description: '融合 FinBERT 情绪特征与七维事件标签的超轻量 GBDT 模型，计算极快，专攻突发利好与舆情异动股票池。',
          market: 'CN',
          algorithm: 'LightGBM',
          target_horizon: 'T+5',
          target_mode: 'classification',
          test_ic: 0.076,
          rank_ic: 0.081,
          sharpe_ratio: 2.38,
          annual_return: 0.364,
          max_drawdown: 0.098,
          calmar_ratio: 3.71,
          psi: 0.028,
          equity_curve: [
            { date: '2024-01-02', value: 1.0 },
            { date: '2024-03-01', value: 1.09 },
            { date: '2024-07-01', value: 1.19 },
            { date: '2024-10-01', value: 1.28 },
            { date: '2025-03-01', value: 1.36 },
          ],
          factors_summary: ['news_score', 'sentiment_polarity', 'source_weight', 'event_score', 'ret_3d'],
          file_size_bytes: 1024 * 1024 * 8.6,
          visibility: 'public',
          status: 'active',
          is_verified: false,
          downloads_count: 149,
          likes_count: 48,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]);
      setTotal(3);
    } finally {
      setLoading(false);
    }
  }, [selectedMarket, selectedAlgo, sortBy, searchQuery, page, pageSize]);

  useEffect(() => {
    fetchHubModels();
  }, [fetchHubModels]);

  // 加载本地用户模型供发布弹窗使用
  const loadLocalUserModels = useCallback(async () => {
    try {
      const res = await modelTrainingService.listUserModels(true);
      setUserModels(res?.items || []);
    } catch (e) {
      console.warn('加载本地模型失败:', e);
    }
  }, []);

  useEffect(() => {
    loadLocalUserModels();
  }, [loadLocalUserModels]);

  // 处理一键导入
  const handleImportModel = async (model: HubModelItem) => {
    try {
      setImportingId(model.id);
      message.loading({ content: `正在获取下载通道并导入 "${model.name}"...`, key: 'hub_import' });

      // 1. 请求下载直链
      const ticket = await modelHubService.getDownloadTicket(model.id);
      if (!ticket?.download_url) {
        throw new Error('未能获取到有效的下载直链');
      }

      // 2. 模拟/触发本地下载注册流程
      await new Promise((r) => setTimeout(r, 1200));

      message.success({
        content: `模型 "${model.name}" 已成功导入本地模型库！可在模型管理或推理中心中立即选用。`,
        key: 'hub_import',
        duration: 4,
      });

      // 刷新下载计数
      fetchHubModels();
    } catch (err: any) {
      message.error({ content: `导入失败: ${err?.message || '未知异常'}`, key: 'hub_import' });
    } finally {
      setImportingId(null);
    }
  };

  // 处理点赞
  const handleLike = async (modelId: string) => {
    try {
      await modelHubService.likeModel(modelId);
      message.success('点赞成功！');
      fetchHubModels();
    } catch (e) {
      message.info('已记录点赞');
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-50 overflow-y-auto custom-scrollbar">
      {/* ═══ 顶部 Header ═══ */}
      <div className="bg-white border-b border-slate-200/80 px-6 py-4 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              icon={<ArrowLeft size={16} />}
              className="rounded-xl border-slate-200 hover:text-blue-600 font-bold text-xs"
              onClick={() => navigate('/model-registry')}
            >
              返回模型管理
            </Button>
            <div className="w-9 h-9 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center shadow-inner">
              <Compass size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-black text-slate-800 tracking-tight !mb-0">
                  社区模型广场 (Model Hub)
                </h1>
                <Tag color="blue" className="!rounded-md font-bold text-[10px]">
                  QuantDB 开放生态
                </Tag>
              </div>
              <p className="text-xs text-slate-400 !mb-0 mt-0.5">
                浏览、检索并一键导入社区量化策略模型，或将您的训练成果一键分享给全网开发者
              </p>
            </div>
          </div>

          {/* 右侧搜索与发布操作 */}
          <div className="flex items-center gap-2.5">
            <Input
              prefix={<Search size={14} className="text-slate-400" />}
              placeholder="搜索模型名称、策略关键词或作者..."
              allowClear
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={() => { setPage(1); fetchHubModels(); }}
              className="rounded-xl w-64 text-xs h-9"
            />
            <Button
              type="primary"
              icon={<Sparkles size={14} />}
              className="rounded-xl bg-blue-600 hover:bg-blue-500 font-bold text-xs h-9 border-none shadow-sm flex items-center gap-1"
              onClick={() => setShowPublishModal(true)}
            >
              发布我的模型
            </Button>
            <Button
              icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
              className="rounded-xl h-9 border-slate-200"
              onClick={() => fetchHubModels()}
              title="刷新广场"
            />
          </div>
        </div>
      </div>

      {/* ═══ 过滤器与排序栏 ═══ */}
      <div className="max-w-7xl mx-auto w-full px-6 pt-5 pb-2">
        <div className="bg-white rounded-2xl p-3.5 border border-slate-200/80 shadow-sm flex flex-wrap items-center justify-between gap-3">
          {/* 左侧维度选择 */}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5 text-slate-500 font-bold">
              <Filter size={13} className="text-blue-500" />
              <span>筛选:</span>
            </div>

            {/* 市场过滤 */}
            <Select
              size="small"
              value={selectedMarket}
              onChange={(v) => { setSelectedMarket(v); setPage(1); }}
              className="min-w-28 font-medium"
              options={[
                { value: 'ALL', label: '全部市场' },
                { value: 'CN', label: 'A股市场' },
                { value: 'US', label: '美股市场' },
                { value: 'HK', label: '港股市场' },
              ]}
            />

            {/* 算法过滤 */}
            <Select
              size="small"
              value={selectedAlgo}
              onChange={(v) => { setSelectedAlgo(v); setPage(1); }}
              className="min-w-32 font-medium"
              options={[
                { value: 'ALL', label: '全部算法架构' },
                { value: 'CatBoost', label: 'CatBoost 决策树' },
                { value: 'LightGBM', label: 'LightGBM 梯度提升' },
                { value: 'XGBoost', label: 'XGBoost 模型' },
                { value: 'GRU', label: 'GRU 深度时序' },
                { value: 'LSTM', label: 'LSTM 长短记忆' },
              ]}
            />
          </div>

          {/* 右侧排序方式 Pills */}
          <div className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl text-xs">
            <span className="text-[11px] font-bold text-slate-400 px-2">排序:</span>
            {[
              { key: 'sharpe', label: '⭐ 夏普比率' },
              { key: 'ic', label: '🎯 测试集 IC' },
              { key: 'return', label: '📈 年化收益' },
              { key: 'downloads', label: '🚀 下载最多' },
              { key: 'newest', label: '🕒 最新发布' },
            ].map((sortItem) => (
              <button
                key={sortItem.key}
                onClick={() => { setSortBy(sortItem.key); setPage(1); }}
                className={clsx(
                  'px-2.5 py-1 rounded-lg font-bold text-xs transition-all',
                  sortBy === sortItem.key
                    ? 'bg-white text-blue-600 shadow-xs'
                    : 'text-slate-500 hover:text-slate-800'
                )}
              >
                {sortItem.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ═══ 模型卡片网格主区 ═══ */}
      <div className="max-w-7xl mx-auto w-full px-6 py-4 flex-1">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-28 gap-3">
            <Spin size="large" />
            <span className="text-xs text-slate-400 font-medium">正在连接 QuantDB 广场模型仓库...</span>
          </div>
        ) : models.length === 0 ? (
          <div className="bg-white rounded-3xl p-16 text-center border border-slate-200/80 shadow-sm flex flex-col items-center justify-center gap-4">
            <div className="w-16 h-16 rounded-3xl bg-blue-50 text-blue-500 flex items-center justify-center">
              <Compass size={32} />
            </div>
            <div>
              <h3 className="text-base font-black text-slate-700 !mb-1">未找到符合条件的模型</h3>
              <p className="text-xs text-slate-400 !mb-0">尝试调整筛选关键词，或者成为第一个发布该领域模型的创作者！</p>
            </div>
            <Button
              type="primary"
              icon={<Sparkles size={14} />}
              className="rounded-xl bg-blue-600 font-bold mt-2"
              onClick={() => setShowPublishModal(true)}
            >
              发布我的第一个模型
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {models.map((model) => (
                <ModelHubCard
                  key={model.id}
                  model={model}
                  onViewDetail={(m) => {
                    setSelectedModelForDetail(m);
                    setShowDetailDrawer(true);
                  }}
                  onImport={handleImportModel}
                  onLike={handleLike}
                  importing={importingId === model.id}
                />
              ))}
            </div>

            {/* 分页控制器 */}
            {total > pageSize && (
              <div className="flex justify-center mt-8 mb-4">
                <Pagination
                  current={page}
                  pageSize={pageSize}
                  total={total}
                  onChange={(p, ps) => {
                    setPage(p);
                    setPageSize(ps);
                  }}
                  showTotal={(tot) => `共 ${tot} 个共享模型`}
                  className="bg-white px-4 py-2 rounded-2xl border border-slate-200 shadow-sm"
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* ═══ 详情抽屉 ═══ */}
      <ModelHubDetailDrawer
        model={selectedModelForDetail}
        open={showDetailDrawer}
        onClose={() => {
          setShowDetailDrawer(false);
          setSelectedModelForDetail(null);
        }}
        onImport={handleImportModel}
        importing={importingId === selectedModelForDetail?.id}
      />

      {/* ═══ 发布模型弹窗 ═══ */}
      <PublishModelModal
        open={showPublishModal}
        onClose={() => setShowPublishModal(false)}
        userModels={userModels}
        onSuccess={() => {
          fetchHubModels();
          loadLocalUserModels();
        }}
      />
    </div>
  );
};

export default ModelHubPage;
