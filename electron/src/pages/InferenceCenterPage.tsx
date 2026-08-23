import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Search, Play, Calendar, Sparkles, RefreshCw, Layers, Database, Sliders, Clock
} from 'lucide-react';
import { Button, Input, Select, DatePicker, message, Spin, Tooltip, Tag } from 'antd';
import dayjs from 'dayjs';
import {
  inferenceCenterService,
  SingleStockPredictionResponse,
  AvailableModelOption,
  KlineItem,
} from '../services/inferenceCenterService';
import { StockForecastChart } from '../features/inference-center/components/StockForecastChart';
import { FeatureDriversPanel } from '../features/inference-center/components/FeatureDriversPanel';
import { ModelConsensusPanel } from '../features/inference-center/components/ModelConsensusPanel';
import { useAppSelector } from '../store';
import { selectCurrentMarket } from '../store/slices/uiSlice';
import { normalizeStockCode } from '../utils/portfolioUtils';

// 模型卡片类型
type ModelCardOption = AvailableModelOption & {
  category: 'tree' | 'dl' | 'ensemble';
  tag: string;
  horizonDesc: string;
  sharpe: number;
  quantileSupport: boolean;
};

export const InferenceCenterPage: React.FC = () => {
  const currentMarket = useAppSelector(selectCurrentMarket);

  // 参数配置状态
  const [symbol, setSymbol] = useState('SH600519');
  const [inputCode, setInputCode] = useState('SH600519');
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [modelCategoryFilter, setModelCategoryFilter] = useState<'all' | 'dl' | 'tree' | 'ensemble'>('all');
  const [horizon, setHorizon] = useState<number>(5);
  const [inferenceDate, setInferenceDate] = useState<dayjs.Dayjs | null>(dayjs());
  const [consensusModelIds, setConsensusModelIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // 数据展示状态（仅真实数据）
  const [models, setModels] = useState<ModelCardOption[]>([]);
  const [kline, setKline] = useState<KlineItem[]>([]);
  const [prediction, setPrediction] = useState<SingleStockPredictionResponse | null>(null);

  // 执行真实推理
  const handleRunInference = useCallback(async (
    targetSymbol?: string,
    targetModelId?: string,
    targetHorizon?: number
  ) => {
    const sym = (targetSymbol || symbol || 'SH600519').trim();
    const mId = targetModelId || selectedModelId;
    const hor = targetHorizon || horizon;

    if (!sym) {
      message.warning('请输入有效的股票代码');
      return;
    }

    // 新的真实推理尚未完成前，不保留上一次标的或模型的结果。
    setPrediction(null);
    setLoading(true);
    try {
      // 1. 获取真实 K 线
      const klineData = await inferenceCenterService.getStockKline(sym, 60);
      if (klineData && klineData.length > 0) {
        setKline(klineData);
      }

      // 2. 仅按钮操作会执行真实模型；输入切换只读取已有真实结果。
      const dateStr = inferenceDate ? inferenceDate.format('YYYY-MM-DD') : undefined;
      const res = await inferenceCenterService.predictSingleStock({
        symbol: sym,
        model_id: mId || undefined,
        date: dateStr,
        horizon: hor,
        market: currentMarket,
        consensus_model_ids: consensusModelIds.length ? consensusModelIds : undefined,
        execute: Boolean(targetSymbol === undefined && targetModelId === undefined),
      });

      if (res && res.status === 'success') {
        setPrediction(res);
        if (!selectedModelId && res.model_id) {
          setSelectedModelId(res.model_id);
        }
      }
    } catch (e: any) {
      console.error('获取真实推理数据失败:', e);
      message.error(`推理接口异常: ${e?.message || '未知错误'}`);
    } finally {
      setLoading(false);
    }
  }, [symbol, selectedModelId, horizon, inferenceDate, currentMarket, consensusModelIds]);

  // 拉取真实模型列表（后端 /api/v1/research/models）
  useEffect(() => {
    let cancelled = false;
    inferenceCenterService
      .getAvailableModels(currentMarket)
      .then((list) => {
        if (cancelled) return;
        const liveModels: ModelCardOption[] = (list || []).map((m) => {
          const kind = String(m.modelType || m.modelId || '').toLowerCase();
          const isDL =
            kind.includes('ensemble') || kind.includes('stacking') ? false :
            kind.includes('tft') || kind.includes('gru') || kind.includes('lstm') ||
            kind.includes('transformer') || kind.includes('pytorch') || kind.includes('tensorflow') ||
            kind.includes('dl');
          const isEns = kind.includes('ensemble') || kind.includes('stacking');
          return {
            ...m,
            category: isEns ? 'ensemble' : isDL ? 'dl' : 'tree',
            tag: m.hasInference ? '已训练' : '生产可用',
            horizonDesc: 'T+1 ~ T+10 灵活周期',
            sharpe: 0,
            quantileSupport: false,
          };
        });
        setModels(liveModels);
        if (liveModels.length > 0 && !selectedModelId) {
          setSelectedModelId(liveModels[0].modelId);
        }
      })
      .catch((err) => {
        console.warn('获取真实模型列表失败:', err);
      });
    return () => {
      cancelled = true;
    };
  }, [currentMarket]);

  const filteredModels = useMemo(() => {
    if (modelCategoryFilter === 'all') return models;
    return models.filter(m => m.category === modelCategoryFilter);
  }, [models, modelCategoryFilter]);

  const currentSelectedModel = useMemo(() => {
    return models.find(m => m.modelId === selectedModelId) || models[0];
  }, [models, selectedModelId]);

  // 提交并格式化代码
  const handleCommitCode = (raw: string) => {
    if (!raw.trim()) return;
    const normalized = normalizeStockCode(raw.trim());
    setSymbol(normalized);
    setInputCode(normalized);
    handleRunInference(normalized);
  };

  const getRatingBadge = (rating: string) => {
    switch (rating) {
      case 'STRONG_BUY':
        return (
          <div className="flex items-center gap-1.5 text-rose-700 bg-rose-50/90 border border-rose-200/90 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
            强烈看多 (STRONG BUY)
          </div>
        );
      case 'BUY':
        return (
          <div className="flex items-center gap-1.5 text-red-600 bg-red-50/90 border border-red-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            偏多研判 (BUY)
          </div>
        );
      case 'HOLD':
        return (
          <div className="flex items-center gap-1.5 text-slate-700 bg-slate-100 border border-slate-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            中性观望 (HOLD)
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1.5 text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            看空警示 (SELL)
          </div>
        );
    }
  };

  return (
    <div className="w-full h-full bg-[#f8fafc] p-6 flex flex-col overflow-hidden font-sans box-border select-none">
      {/* ================= 主一体化框架 (32px 大圆角) ================= */}
      <div className="bg-white border border-gray-200 shadow-sm w-full h-full rounded-[32px] flex overflow-hidden">
        {/* ================= 左侧：推理配置中心 ================= */}
        <div className="w-80 shrink-0 flex flex-col border-r border-gray-200 bg-white p-5 overflow-y-auto custom-scrollbar">
          {/* 顶部标题 */}
          <div className="flex items-center justify-between pb-3.5 border-b border-slate-100 mb-4 px-1">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
                <Sliders className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-800 m-0">推理参数配置</h3>
                <p className="text-[10px] text-slate-400 m-0">真实标的 · 预测周期 · 模型选型</p>
              </div>
            </div>
            <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]" />
          </div>

          {/* 控件区 */}
          <div className="flex flex-col gap-3.5 mb-4">
            {/* 1. 标的选择 */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
                <Search className="w-3.5 h-3.5 text-blue-500" /> 目标个股
              </span>
              <div className="flex items-center bg-slate-50/70 border border-slate-200 hover:border-blue-400 focus-within:border-blue-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100 rounded-xl px-3 py-1.5 transition-all shadow-2xs">
                <Input
                  variant="borderless"
                  placeholder="输入代码 (如 600036)"
                  value={inputCode}
                  onChange={e => setInputCode(e.target.value.toUpperCase())}
                  onBlur={() => handleCommitCode(inputCode)}
                  onPressEnter={() => handleCommitCode(inputCode)}
                  className="p-0 font-mono font-bold text-sm text-blue-600 focus:outline-none"
                  style={{ flex: 1, minWidth: 100, padding: 0 }}
                />
                <div className="flex items-center gap-1 pl-2 border-l border-slate-200 shrink-0">
                  <span className="text-xs font-bold text-slate-700 select-none">
                    {prediction?.stock_name || '标的资产'}
                  </span>
                </div>
              </div>
            </div>

            {/* 2. 预测周期 */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-indigo-500" /> 预测周期 (Horizon)
              </span>
              <Select
                value={horizon}
                onChange={val => setHorizon(val)}
                style={{ width: '100%', height: 34 }}
                options={[
                  { label: 'T+1 次日预期', value: 1 },
                  { label: 'T+3 短线周期', value: 3 },
                  { label: 'T+5 一周趋势 (推荐)', value: 5 },
                  { label: 'T+10 双周展望', value: 10 },
                ]}
              />
            </div>

            {/* 3. 基准日期 */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5 text-amber-500" /> 基准日期 (支持历史盲测)
              </span>
              <DatePicker
                value={inferenceDate}
                onChange={d => setInferenceDate(d)}
                style={{ width: '100%', height: 34, borderRadius: 10 }}
                allowClear={false}
              />
            </div>

            {/* 4. 模型筛选与选择 */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
                  <Database className="w-3.5 h-3.5 text-purple-500" /> 模型选型
                </span>
                <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg text-[10px]">
                  {(['all', 'dl', 'tree'] as const).map(cat => (
                    <button
                      key={cat}
                      onClick={() => setModelCategoryFilter(cat)}
                      className={`px-1.5 py-0.5 rounded-md font-bold transition-all ${
                        modelCategoryFilter === cat
                          ? 'bg-white text-blue-600 shadow-2xs'
                          : 'text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      {cat === 'all' ? '全部' : cat === 'dl' ? '深度' : '树模'}
                    </button>
                  ))}
                </div>
              </div>

              {/* 模型列表 */}
              <div className="flex flex-col gap-2 max-h-48 overflow-y-auto custom-scrollbar pr-0.5">
                {filteredModels.map(m => {
                  const isSelected = selectedModelId === m.modelId;
                  return (
                    <div
                      key={m.modelId}
                      onClick={() => setSelectedModelId(m.modelId)}
                      className={`p-2.5 rounded-xl border transition-all cursor-pointer flex flex-col gap-1 ${
                        isSelected
                          ? 'bg-blue-50/80 border-blue-300 ring-2 ring-blue-100 shadow-xs'
                          : 'bg-slate-50/60 border-slate-200/80 hover:bg-slate-100/80 hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-xs font-bold truncate ${isSelected ? 'text-blue-700' : 'text-slate-800'}`}>
                          {m.modelName}
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-white/90 border border-slate-200 text-slate-500">
                          {m.tag}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400">
                        <span>{m.horizonDesc}</span>
                        <span>Sharpe: <strong className="text-slate-600">{m.sharpe.toFixed(2)}</strong></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 底部触发按钮 */}
          <div className="mt-auto pt-3 border-t border-slate-100">
            <Button
              type="primary"
              block
              icon={<Play size={15} fill="currentColor" />}
              loading={loading}
              onClick={() => handleRunInference()}
              style={{
                height: 40,
                borderRadius: 12,
                fontWeight: 800,
                fontSize: 13,
                background: 'linear-gradient(135deg, #2563eb, #3b82f6)',
                boxShadow: '0 4px 14px rgba(37, 99, 235, 0.28)',
              }}
            >
              开始预测推理
            </Button>
          </div>
        </div>

        {/* ================= 右侧：量化研判看板与预测走势 ================= */}
        <div className="flex-1 min-w-0 flex flex-col bg-gray-50/50 overflow-hidden">
          {/* 顶部：当前标的综合指标概览 Bar */}
          {prediction ? (
            <div className="bg-white px-6 py-3.5 border-b border-gray-200 flex items-center justify-between shrink-0 z-10">
              {/* 左侧：标的资产与当前实时价格 */}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-black text-slate-800 tracking-tight">
                    {prediction.stock_name}
                  </span>
                  <span className="text-xs font-mono font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-lg border border-blue-100/80">
                    {prediction.symbol}
                  </span>
                </div>
                <div className="h-5 w-[1px] bg-slate-200" />
                <div className="flex items-baseline gap-1.5 font-mono">
                  <span className="text-xs text-slate-400 font-sans font-medium">基准价格</span>
                  <span className="text-base font-black text-slate-900">
                    ¥{prediction.current_price ? prediction.current_price.toFixed(2) : '—'}
                  </span>
                </div>
              </div>

              {/* 右侧：多空研判评级与上涨概率 */}
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 text-xs text-slate-500 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200">
                  <span>模型信号分数:</span>
                  <strong className={`font-mono font-black ${prediction.expected_return >= 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                    {prediction.predicted_score.toFixed(4)}
                  </strong>
                </div>
                {getRatingBadge(prediction.rating)}
                <div className="flex items-center gap-1.5 bg-rose-50/70 border border-rose-100 px-3 py-1 rounded-xl">
                  <span className="text-[11px] text-slate-500 font-semibold">数据来源:</span>
                  <span className="text-xs font-black font-mono text-rose-600">真实模型推理</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white px-6 py-4 border-b border-gray-200 flex items-center justify-between shrink-0 z-10">
              <span className="text-sm text-slate-400 font-semibold">请在左侧选择标的并点击「开始预测推理」</span>
            </div>
          )}

          {/* 主内容区 */}
          <div className="flex-1 min-h-0 p-5 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
            {loading && !prediction ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-white rounded-2xl border border-gray-200 shadow-xs min-h-[300px]">
                <Spin size="large" />
                <span className="text-xs font-semibold text-slate-500">正在接入真实推理引擎与行情...</span>
              </div>
            ) : prediction ? (
              <div className="flex-1 min-h-0 flex flex-col gap-4">
                {/* 上半部：核心图表 + 分位数指标看板 */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ height: '420px', minHeight: '420px' }}>
                  {/* 左侧 2/3：走势扇形图 */}
                  <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 shadow-xs flex flex-col overflow-hidden">
                    <StockForecastChart
                      kline={kline}
                      forecast={prediction.forecast_curve}
                      symbol={prediction.symbol}
                      stockName={prediction.stock_name}
                      currentPrice={prediction.current_price}
                      modelName={prediction.model_name || currentSelectedModel?.modelName}
                      asOfDate={prediction.as_of_date}
                    />
                  </div>

                  {/* 右侧 1/3：分位数收益与置信指标 */}
                  <div className="bg-white rounded-2xl p-5 border border-gray-200 shadow-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between pb-2.5 border-b border-slate-100 mb-3">
                        <span className="text-xs font-bold text-slate-500">模型推理指标</span>
                        <Tag color="blue" className="rounded font-mono text-[10px] m-0">Persisted Model Score</Tag>
                      </div>

                      {/* 预期回报 */}
                      <div className="p-3.5 bg-slate-50/80 rounded-2xl border border-slate-200/80 mb-3 text-center">
                        <span className="text-[11px] text-slate-400 font-semibold block mb-0.5">模型信号分数</span>
                        <span className={`text-2xl font-black font-mono ${prediction.expected_return >= 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                          {prediction.predicted_score.toFixed(4)}
                        </span>
                      </div>

                      {/* 分位数模型提示 */}
                      <div className="p-3.5 bg-gradient-to-br from-slate-50 to-blue-50/30 rounded-2xl border border-slate-200/80">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-bold text-slate-700">分位数区间</span>
                          <Tooltip title="当前注册模型未输出分位数回归结果，因此不展示估算区间。">
                            <Sparkles className="w-3.5 h-3.5 text-slate-400 cursor-pointer" />
                          </Tooltip>
                        </div>
                        <p className="text-[11px] leading-relaxed text-slate-400 m-0">
                          当前生产模型只输出真实信号分数；待接入原生分位数模型后再显示 P10 / P50 / P90。
                        </p>
                      </div>
                    </div>

                    <div className="pt-2.5 border-t border-slate-100 text-[11px] text-slate-400 flex items-center justify-between">
                      <span>模型准确率 (IC): <strong className="text-slate-700 font-mono">{currentSelectedModel?.accuracy != null && currentSelectedModel.accuracy !== 0 ? (typeof currentSelectedModel.accuracy === 'number' ? currentSelectedModel.accuracy.toFixed(3) : currentSelectedModel.accuracy) : '—'}</strong></span>
                      <span>绩效指标: <strong className="text-slate-700 font-mono">以模型注册信息为准</strong></span>
                    </div>
                  </div>
                </div>

                {/* 下半部：单股因子归因 (左) + 多模型共识 (右) */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ minHeight: '250px' }}>
                  <div className="bg-white rounded-2xl border border-gray-200 shadow-xs overflow-hidden">
                    <FeatureDriversPanel drivers={prediction.drivers} source={prediction.drivers_source} />
                  </div>
                  <div className="bg-white rounded-2xl border border-gray-200 shadow-xs overflow-hidden">
                    <ModelConsensusPanel
                      consensus={prediction.consensus}
                      consensusScore={prediction.consensus_score}
                      selectedCount={consensusModelIds.length}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-white rounded-2xl border border-dashed border-gray-200 text-slate-400 min-h-[300px]">
                <Database size={28} className="opacity-30" />
                <span className="text-xs font-semibold">请在左侧配置参数并点击「开始预测推理」查看多维量化分析</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InferenceCenterPage;
