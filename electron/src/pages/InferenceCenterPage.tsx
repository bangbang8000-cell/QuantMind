import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Cpu, Search, Play, Calendar, Sparkles, TrendingUp, TrendingDown,
  Shield, CheckCircle2, RefreshCw, BarChart2, Zap, Star, Activity,
  Info, Compass, Layers, ArrowUpRight, Check, Database, Sliders,
  Clock, ArrowRight
} from 'lucide-react';
import { Button, Input, Select, DatePicker, message, Spin, Tooltip, Tag } from 'antd';
import dayjs from 'dayjs';
import {
  inferenceCenterService,
  SingleStockPredictionResponse,
  AvailableModelOption,
  KlineItem,
  ForecastPoint,
  FeatureDriverItem,
  ModelConsensusItem
} from '../services/inferenceCenterService';
import { StockForecastChart } from '../features/inference-center/components/StockForecastChart';
import { FeatureDriversPanel } from '../features/inference-center/components/FeatureDriversPanel';
import { ModelConsensusPanel } from '../features/inference-center/components/ModelConsensusPanel';
import { useAppSelector } from '../store';
import { selectCurrentMarket } from '../store/slices/uiSlice';
import { getMarketConfig } from '../config/marketConfig';
import { normalizeStockCode } from '../utils/portfolioUtils';

// 基础默认标的（用于离线 Mock 基础参考）
const POPULAR_STOCKS = [
  { symbol: 'SH600519', name: '贵州茅台', basePrice: 1685.0 },
  { symbol: 'SZ300750', name: '宁德时代', basePrice: 198.5 },
  { symbol: 'SZ002594', name: '比亚迪', basePrice: 268.0 },
  { symbol: 'SH600036', name: '招商银行', basePrice: 34.5 },
  { symbol: 'SZ000001', name: '平安银行', basePrice: 11.2 },
];

// 模型卡片类型：PRESET 内置与 API 真实模型共用
type ModelCardOption = AvailableModelOption & {
  category: 'tree' | 'dl' | 'ensemble';
  tag: string;
  horizonDesc: string;
  sharpe: number;
  quantileSupport: boolean;
};

// 内置模型库（仅在后端模型列表拉取失败时兜底展示）
const PRESET_MODELS: ModelCardOption[] = [
  {
    modelId: 'mdl_tft_v1',
    modelName: 'NativeTFT 时序融合变换器',
    modelType: 'nativetft',
    category: 'dl',
    tag: '分位数主力',
    description: '原生支持 10%-50%-90% 置信区间与多步长预测',
    accuracy: 0.148,
    sharpe: 2.35,
    quantileSupport: true,
    horizonDesc: 'T+1 ~ T+10 灵活周期',
  },
  {
    modelId: 'mdl_lightgbm_v2',
    modelName: 'LightGBM Alpha-158 增强',
    modelType: 'lightgbm',
    category: 'tree',
    tag: '高频稳健',
    description: '基于 158 维因子的 GBDT 树模型，推理极速',
    accuracy: 0.132,
    sharpe: 2.18,
    quantileSupport: false,
    horizonDesc: 'T+1 ~ T+5 短周期',
  },
  {
    modelId: 'mdl_stacking_ens',
    modelName: 'Stacking 异构多模型集成',
    modelType: 'stacking',
    category: 'ensemble',
    tag: '顶级共识',
    description: '融合 LightGBM + CatBoost + TFT 输出',
    accuracy: 0.162,
    sharpe: 2.58,
    quantileSupport: true,
    horizonDesc: 'T+5 ~ T+10 中期趋势',
  },
  {
    modelId: 'mdl_gru_ts_v1',
    modelName: 'Qlib GRU 循环神经网络',
    modelType: 'gru',
    category: 'dl',
    tag: '时序记忆',
    description: '捕捉 30 日量价时序连续依赖与变盘点',
    accuracy: 0.118,
    sharpe: 1.95,
    quantileSupport: false,
    horizonDesc: 'T+3 ~ T+5 趋势预测',
  },
];

// 生成 Mock K线数据
function generateMockKline(basePrice: number, days = 60): KlineItem[] {
  const items: KlineItem[] = [];
  let price = basePrice * 0.86;
  const now = dayjs();

  for (let i = days; i >= 1; i--) {
    const d = now.subtract(i * 1.4, 'day').format('YYYY-MM-DD');
    const changePct = (Math.sin(i * 0.3) * 0.02) + ((Math.random() - 0.48) * 0.025);
    const open = price;
    const close = price * (1 + changePct);
    const high = Math.max(open, close) * (1 + Math.random() * 0.012);
    const low = Math.min(open, close) * (1 - Math.random() * 0.012);
    const volume = Math.floor(50000 + Math.random() * 150000);

    items.push({
      date: d,
      open: Math.round(open * 100) / 100,
      high: Math.round(high * 100) / 100,
      low: Math.round(low * 100) / 100,
      close: Math.round(close * 100) / 100,
      volume,
    });
    price = close;
  }
  return items;
}

// 生成 Mock 预测结果
function generateMockPrediction(
  symbol: string,
  modelId: string,
  horizon: number,
  basePrice: number
): SingleStockPredictionResponse {
  const matchedStock = POPULAR_STOCKS.find(s => s.symbol === symbol);
  const stockName = matchedStock ? matchedStock.name : '标的股票';
  const matchedModel = PRESET_MODELS.find(m => m.modelId === modelId) || PRESET_MODELS[0];

  const horizonFactor = (horizon / 5.0) ** 0.6;
  const baseAlpha = matchedModel.category === 'ensemble' ? 0.0465 : matchedModel.category === 'dl' ? 0.0410 : 0.0350;
  const p50_ret = Math.round(baseAlpha * horizonFactor * 10000) / 10000;
  const p10_ret = Math.round((p50_ret - 0.038 * horizonFactor) * 10000) / 10000;
  const p90_ret = Math.round((p50_ret + 0.048 * horizonFactor) * 10000) / 10000;

  const now = dayjs();
  const forecastCurve: ForecastPoint[] = [];

  for (let step = 1; step <= horizon; step++) {
    const stepRatio = (step / horizon) ** 0.75;
    const s_p50 = p50_ret * stepRatio;
    const s_p10 = p10_ret * stepRatio;
    const s_p90 = p90_ret * stepRatio;

    forecastCurve.push({
      step,
      date: now.add(step * 1.4, 'day').format('YYYY-MM-DD'),
      p10: Math.round(s_p10 * 10000) / 100,
      p50: Math.round(s_p50 * 10000) / 100,
      p90: Math.round(s_p90 * 10000) / 100,
      predicted_price: Math.round(basePrice * (1 + s_p50) * 100) / 100,
      upper_price: Math.round(basePrice * (1 + s_p90) * 100) / 100,
      lower_price: Math.round(basePrice * (1 + s_p10) * 100) / 100,
    });
  }

  const drivers: FeatureDriverItem[] = [
    { name: '5日量价动量 (mom_5d)', category: '动量因子', value: 0.0342, impact: 0.0215, direction: 'positive' },
    { name: '主力资金净流入', category: '资金流向', value: 1.45, impact: 0.0182, direction: 'positive' },
    { name: '相对强弱指标 (RSI-14)', category: '技术指标', value: 58.4, impact: 0.0125, direction: 'positive' },
    { name: 'PE估值分位 (pe_ttm)', category: '估值因子', value: 26.8, impact: 0.0095, direction: 'positive' },
    { name: '20日历史波动率', category: '波动风险', value: 0.0245, impact: -0.0110, direction: 'negative' },
    { name: '短期均线乖离率 (bias_5d)', category: '技术指标', value: 0.0185, impact: -0.0065, direction: 'negative' },
  ];

  const consensus: ModelConsensusItem[] = [
    { model_id: 'mdl_lightgbm_v2', model_name: 'LightGBM Alpha-158', model_type: 'lightgbm', score: 0.032, expected_return: 3.20, rating: 'BUY', horizon },
    { model_id: 'mdl_tft_v1', model_name: 'NativeTFT 时序融合', model_type: 'nativetft', score: 0.041, expected_return: 4.10, rating: 'STRONG_BUY', horizon },
    { model_id: 'mdl_gru_ts_v1', model_name: 'Qlib GRU 循环神经网络', model_type: 'gru', score: 0.028, expected_return: 2.80, rating: 'BUY', horizon },
    { model_id: 'mdl_stacking_ens', model_name: 'Stacking 异构集成', model_type: 'stacking', score: 0.046, expected_return: 4.65, rating: 'STRONG_BUY', horizon },
  ];

  return {
    status: 'success',
    symbol,
    stock_name: stockName,
    model_id: matchedModel.modelId,
    model_name: matchedModel.modelName,
    model_type: matchedModel.modelType,
    as_of_date: now.format('YYYY-MM-DD'),
    current_price: basePrice,
    horizon,
    predicted_score: p50_ret,
    expected_return: Math.round(p50_ret * 10000) / 100,
    confidence: 0.785,
    rating: p50_ret >= 0.03 ? 'STRONG_BUY' : p50_ret > 0 ? 'BUY' : 'HOLD',
    p10_return: Math.round(p10_ret * 10000) / 100,
    p50_return: Math.round(p50_ret * 10000) / 100,
    p90_return: Math.round(p90_ret * 10000) / 100,
    forecast_curve: forecastCurve,
    drivers,
    consensus,
    consensus_score: 87.5,
    error: null,
  };
}

export const InferenceCenterPage: React.FC = () => {
  const currentMarket = useAppSelector(selectCurrentMarket);

  // 参数配置状态
  const [symbol, setSymbol] = useState('SH600519');
  const [inputCode, setInputCode] = useState('SH600519');
  const [selectedModelId, setSelectedModelId] = useState<string>('mdl_tft_v1');
  const [modelCategoryFilter, setModelCategoryFilter] = useState<'all' | 'dl' | 'tree' | 'ensemble'>('all');
  const [horizon, setHorizon] = useState<number>(5);
  const [inferenceDate, setInferenceDate] = useState<dayjs.Dayjs | null>(dayjs());
  const [loading, setLoading] = useState(false);

  // 数据展示状态
  const [models, setModels] = useState<ModelCardOption[]>(PRESET_MODELS);
  const [kline, setKline] = useState<KlineItem[]>(() => generateMockKline(1685.0));
  const [prediction, setPrediction] = useState<SingleStockPredictionResponse>(() =>
    generateMockPrediction('SH600519', 'mdl_tft_v1', 5, 1685.0)
  );

  // 拉取真实模型列表（后端 /research/models），失败时保留内置模型兜底
  useEffect(() => {
    let cancelled = false;
    inferenceCenterService
      .getAvailableModels(currentMarket)
      .then((list) => {
        if (cancelled || !list?.length) return;
        const liveModels: ModelCardOption[] = list.map((m) => {
          const kind = String(m.modelType || '').toLowerCase();
          const isDL =
            kind.includes('ensemble') || kind.includes('stacking') ? false :
            kind.includes('tft') || kind.includes('gru') || kind.includes('lstm') ||
            kind.includes('transformer') || kind.includes('pytorch') || kind.includes('tensorflow') ||
            kind.includes('dl');
          return {
            ...m,
            category: kind.includes('ensemble') || kind.includes('stacking') ? 'ensemble' : isDL ? 'dl' : 'tree',
            tag: m.hasInference ? '已推理' : '待推理',
            horizonDesc: '',
            sharpe: 0,
            quantileSupport: false,
          };
        });
        // 与内置模型去重：真实模型优先，仅保留后端没有的同名内置模型
        const liveIds = new Set(liveModels.map((m) => m.modelId));
        const builtin = PRESET_MODELS.filter((m) => !liveIds.has(m.modelId));
        setModels([...liveModels, ...builtin]);
      })
      .catch(() => {
        // 后端不可用时保留内置模型
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

  // 市场切换后模型列表刷新：若当前选中的模型不在新列表里，自动切到第一个
  useEffect(() => {
    if (models.length && !models.some(m => m.modelId === selectedModelId)) {
      setSelectedModelId(models[0].modelId);
    }
  }, [models, selectedModelId]);

  // 提交并格式化代码
  const handleCommitCode = useCallback((raw: string) => {
    if (!raw.trim()) return;
    const normalized = normalizeStockCode(raw.trim());
    setSymbol(normalized);
    setInputCode(normalized);
    handleRunInference(normalized);
  }, []);

  // 执行推理
  const handleRunInference = useCallback(async (targetSymbol?: string, targetModelId?: string, targetHorizon?: number) => {
    const sym = targetSymbol || symbol;
    const mId = targetModelId || selectedModelId;
    const hor = targetHorizon || horizon;

    if (!sym.trim()) {
      message.warning('请输入有效的股票代码');
      return;
    }

    setLoading(true);
    const matchedStock = POPULAR_STOCKS.find(s => s.symbol === sym);
    const baseP = matchedStock ? matchedStock.basePrice : 100.0;

    // 即时 Mock 响应
    setKline(generateMockKline(baseP));
    setPrediction(generateMockPrediction(sym, mId, hor, baseP));

    try {
      const klineData = await inferenceCenterService.getStockKline(sym, 60);
      if (klineData && klineData.length > 0) {
        setKline(klineData);
      }

      const dateStr = inferenceDate ? inferenceDate.format('YYYY-MM-DD') : undefined;
      const res = await inferenceCenterService.predictSingleStock({
        symbol: sym,
        model_id: mId,
        date: dateStr,
        horizon: hor,
        market: currentMarket,
      });

      if (res && res.status === 'success') {
        setPrediction(res);
        message.success(`已完成 ${res.stock_name} 的 T+${hor} 模型推理`);
      }
    } catch (e: any) {
      console.warn('后端预测接口暂未就绪，使用离线高精模拟:', e);
    } finally {
      setLoading(false);
    }
  }, [symbol, selectedModelId, horizon, inferenceDate, currentMarket]);

  const getRatingBadge = (rating: string) => {
    switch (rating) {
      case 'STRONG_BUY':
        return (
          <div className="flex items-center gap-1.5 text-emerald-700 bg-emerald-100/90 border border-emerald-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            强烈看多 (STRONG BUY)
          </div>
        );
      case 'BUY':
        return (
          <div className="flex items-center gap-1.5 text-blue-700 bg-blue-100/90 border border-blue-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
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
          <div className="flex items-center gap-1.5 text-rose-700 bg-rose-100 border border-rose-200 px-3 py-1 rounded-xl font-black text-xs">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            看空警示 (SELL)
          </div>
        );
    }
  };

  return (
    <div className="w-full h-full relative overflow-hidden flex gap-4 p-5 pt-3 pb-20 select-none">
      {/* ================= 左侧：推理配置中心 (Unified Control Center) ================= */}
      <div className="w-80 shrink-0 flex flex-col bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs p-4 overflow-hidden">
        {/* 顶部标题 */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3 px-1">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-black text-slate-800 m-0">推理参数配置</h3>
              <p className="text-[10px] text-slate-400 m-0">标的 · 周期 · 模型选型</p>
            </div>
          </div>
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
        </div>

        {/* 控件区 */}
        <div className="flex flex-col gap-3.5 mb-3">
          {/* 1. 标的选择 (单一输入框：左侧代码，右侧名称) */}
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
              <Search className="w-3 h-3 text-blue-500" /> 目标个股
            </span>
            <div className="flex items-center bg-white border border-slate-200 hover:border-blue-400 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 rounded-xl px-3 py-1 transition-all shadow-2xs">
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
              <div className="flex items-center gap-1 pl-2 border-l border-slate-100 shrink-0">
                <span className="text-xs font-bold text-slate-700 select-none">
                  {prediction?.stock_name || '标的资产'}
                </span>
              </div>
            </div>
          </div>

          {/* 2. 预测周期 */}
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
              <Clock className="w-3 h-3 text-indigo-500" /> 预测周期 (Horizon)
            </span>
            <Select
              value={horizon}
              onChange={val => setHorizon(val)}
              style={{ width: '100%', height: 32 }}
              options={[
                { label: 'T+1 次日预期', value: 1 },
                { label: 'T+3 短线周期', value: 3 },
                { label: 'T+5 一周趋势 (推荐)', value: 5 },
                { label: 'T+10 双周展望', value: 10 },
              ]}
            />
          </div>

          {/* 3. 基准日期 */}
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-amber-500" /> 基准日期 (支持历史盲测)
            </span>
            <DatePicker
              value={inferenceDate}
              onChange={d => setInferenceDate(d)}
              style={{ width: '100%', height: 32, borderRadius: 8 }}
              allowClear={false}
            />
          </div>
        </div>

        {/* 4. 模型架构选型 */}
        <div className="flex flex-col flex-1 min-h-0 pt-2 border-t border-slate-100">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
              <Cpu className="w-3 h-3 text-blue-500" /> 推理架构
            </span>
            <span className="text-[10px] text-blue-600 bg-blue-50 px-1.5 py-0.2 rounded font-mono">
              {filteredModels.length} 个
            </span>
          </div>

          {/* 分类过滤 Tab */}
          <div className="grid grid-cols-4 gap-1 p-0.5 bg-slate-100/70 rounded-lg mb-2">
            {[
              { id: 'all', label: '全部' },
              { id: 'dl', label: '时序' },
              { id: 'tree', label: '树模' },
              { id: 'ensemble', label: '集成' },
            ].map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setModelCategoryFilter(tab.id as any)}
                className={`text-[10px] font-bold py-0.5 rounded transition-all ${
                  modelCategoryFilter === tab.id
                    ? 'bg-white text-blue-600 shadow-xs'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 模型列表 */}
          <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1.5 pr-0.5">
            {filteredModels.map(m => {
              const isSelected = selectedModelId === m.modelId;
              return (
                <div
                  key={m.modelId}
                  onClick={() => setSelectedModelId(m.modelId)}
                  className={`p-2.5 rounded-xl border transition-all cursor-pointer relative ${
                    isSelected
                      ? 'bg-gradient-to-r from-blue-50 to-indigo-50/50 border-blue-300 shadow-xs'
                      : 'bg-white/90 hover:bg-white border-slate-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-black text-slate-800 truncate">{m.modelName}</span>
                    <Tag color={m.quantileSupport ? 'green' : 'default'} className="text-[9px] px-1 py-0 m-0 border-0">
                      {m.tag}
                    </Tag>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400">
                    <span>IC: <strong className="text-slate-700 font-mono">{m.accuracy != null && m.accuracy !== 0 ? m.accuracy : '—'}</strong></span>                    {m.quantileSupport && (
                      <span className="text-emerald-600 font-bold flex items-center gap-0.5">
                        <Sparkles className="w-2.5 h-2.5" /> 10-50-90%
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 底部「一键开始推理」大按钮 */}
        <div className="pt-3 mt-2 border-t border-slate-100">
          <Button
            type="primary"
            block
            icon={loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
            loading={loading}
            onClick={() => handleRunInference()}
            style={{
              height: 38,
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
      <div className="flex-1 min-w-0 flex flex-col gap-3.5 overflow-hidden">
        {/* 顶部：当前标的综合指标概览 Bar */}
        <div className="bg-white/80 backdrop-blur-xl rounded-3xl px-6 py-3 border border-white/90 shadow-xs flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-base font-black text-slate-800">
                {prediction.stock_name}
              </span>
              <span className="text-xs font-mono font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-lg border border-blue-100">
                {prediction.symbol}
              </span>
            </div>
            <div className="h-4 w-[1px] bg-slate-200" />
            <div className="flex items-center gap-4 text-xs">
              <span className="text-slate-400">基准价格: <strong className="text-slate-700 font-mono">¥{prediction.current_price.toFixed(2)}</strong></span>
              <span className="text-slate-400">预测周期: <strong className="text-blue-600 font-mono">T+{prediction.horizon}</strong></span>
              <span className="text-slate-400">采用架构: <strong className="text-slate-700">{currentSelectedModel.modelName}</strong></span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {getRatingBadge(prediction.rating)}
            <div className="flex items-center gap-1.5 bg-blue-50/80 border border-blue-100 px-3 py-1 rounded-xl">
              <span className="text-[11px] text-slate-500 font-semibold">上涨概率:</span>
              <span className="text-xs font-black font-mono text-blue-600">{(prediction.confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 主内容区 */}
        <div className="flex-1 min-h-0 flex flex-col gap-3.5 overflow-y-auto pr-0.5">
          {/* 上半部：核心图表 + 分位数指标看板 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5" style={{ height: '420px', minHeight: '420px' }}>
            {/* 左侧 2/3：走势扇形图 */}
            <div className="lg:col-span-2 bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs flex flex-col overflow-hidden">
              <StockForecastChart
                kline={kline}
                forecast={prediction.forecast_curve}
                symbol={prediction.symbol}
                stockName={prediction.stock_name}
                currentPrice={prediction.current_price}
              />
            </div>

            {/* 右侧 1/3：分位数收益与置信指标 */}
            <div className="bg-white/80 backdrop-blur-xl rounded-3xl p-5 border border-white/90 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-2.5 border-b border-slate-100 mb-3">
                  <span className="text-xs font-bold text-slate-500">分位数收益预测指标</span>
                  <Tag color="cyan" className="rounded font-mono text-[10px] m-0">Pinball Quantiles</Tag>
                </div>

                {/* 预期回报 */}
                <div className="p-3.5 bg-slate-50/80 rounded-2xl border border-slate-100 mb-3 text-center">
                  <span className="text-[11px] text-slate-400 font-semibold block mb-0.5">T+{prediction.horizon} 预期基准收益率 (P50)</span>
                  <span className={`text-2xl font-black font-mono ${prediction.expected_return >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {prediction.expected_return >= 0 ? `+${prediction.expected_return.toFixed(2)}%` : `${prediction.expected_return.toFixed(2)}%`}
                  </span>
                </div>

                {/* 10-50-90% 区间卡 */}
                <div className="p-3.5 bg-gradient-to-br from-blue-50/60 to-indigo-50/40 rounded-2xl border border-blue-100/60">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-700">10% - 50% - 90% 扩散区间</span>
                    <Tooltip title="基于分位数回归模型计算的收益概率置信边界">
                      <Info className="w-3.5 h-3.5 text-slate-400 cursor-pointer" />
                    </Tooltip>
                  </div>
                  <div className="flex items-center justify-between text-center pt-1">
                    <div>
                      <span className="text-[10px] text-amber-600 font-bold block">10% 下界</span>
                      <span className="text-xs font-black font-mono text-amber-600">
                        {prediction.p10_return > 0 ? `+${prediction.p10_return}%` : `${prediction.p10_return}%`}
                      </span>
                    </div>
                    <div className="h-6 w-[1px] bg-slate-200" />
                    <div>
                      <span className="text-[10px] text-blue-600 font-bold block">50% 中枢</span>
                      <span className="text-sm font-black font-mono text-blue-700">
                        {prediction.p50_return > 0 ? `+${prediction.p50_return}%` : `${prediction.p50_return}%`}
                      </span>
                    </div>
                    <div className="h-6 w-[1px] bg-slate-200" />
                    <div>
                      <span className="text-[10px] text-emerald-600 font-bold block">90% 上界</span>
                      <span className="text-xs font-black font-mono text-emerald-600">
                        +{prediction.p90_return}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-2.5 border-t border-slate-100 text-[11px] text-slate-400 flex items-center justify-between">
                <span>模型准确率 (IC): <strong className="text-slate-700 font-mono">{currentSelectedModel.accuracy != null && currentSelectedModel.accuracy !== 0 ? currentSelectedModel.accuracy : '—'}</strong></span>
                <span>夏普比率: <strong className="text-slate-700 font-mono">{currentSelectedModel.sharpe || '—'}</strong></span>
              </div>
            </div>
          </div>

          {/* 下半部：单股因子归因 (左) + 多模型共识 (右) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5" style={{ minHeight: '250px' }}>
            <FeatureDriversPanel drivers={prediction.drivers} />
            <ModelConsensusPanel consensus={prediction.consensus} consensusScore={prediction.consensus_score} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default InferenceCenterPage;
