import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Cpu, Search, Play, Calendar, Sparkles, TrendingUp, TrendingDown,
  Shield, CheckCircle2, RefreshCw, BarChart2, Zap, Star, Activity,
  Info, Compass, Layers, ArrowUpRight
} from 'lucide-react';
import { Button, Input, Select, DatePicker, message, Spin, Tooltip, Tag } from 'antd';
import dayjs from 'dayjs';
import {
  inferenceCenterService,
  SingleStockPredictionResponse,
  AvailableModelOption,
  KlineItem
} from '../services/inferenceCenterService';
import { StockForecastChart } from '../features/inference-center/components/StockForecastChart';
import { FeatureDriversPanel } from '../features/inference-center/components/FeatureDriversPanel';
import { ModelConsensusPanel } from '../features/inference-center/components/ModelConsensusPanel';
import { useAppSelector } from '../store';
import { selectCurrentMarket } from '../store/slices/uiSlice';
import { getMarketConfig } from '../config/marketConfig';

const POPULAR_STOCKS = [
  { symbol: 'SH600519', name: '贵州茅台' },
  { symbol: 'SZ300750', name: '宁德时代' },
  { symbol: 'SZ002594', name: '比亚迪' },
  { symbol: 'SH601318', name: '中国平安' },
  { symbol: 'SH600036', name: '招商银行' },
  { symbol: 'SZ000001', name: '平安银行' },
];

export const InferenceCenterPage: React.FC = () => {
  const currentMarket = useAppSelector(selectCurrentMarket);
  const marketConfig = getMarketConfig(currentMarket);

  // 状态
  const [symbol, setSymbol] = useState('SH600519');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedModelId, setSelectedModelId] = useState<string>('mdl_tft_v1');
  const [horizon, setHorizon] = useState<number>(5);
  const [inferenceDate, setInferenceDate] = useState<dayjs.Dayjs | null>(dayjs());
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<AvailableModelOption[]>([]);
  const [kline, setKline] = useState<KlineItem[]>([]);
  const [prediction, setPrediction] = useState<SingleStockPredictionResponse | null>(null);

  // 初始化加载可用模型
  useEffect(() => {
    const init = async () => {
      try {
        const availableModels = await inferenceCenterService.getAvailableModels();
        setModels(availableModels);
        if (availableModels.length > 0) {
          // 优先默认选中 TFT 或 LightGBM
          const tft = availableModels.find(m => m.modelType.includes('tft') || m.modelType.includes('nativetft'));
          setSelectedModelId(tft ? tft.modelId : availableModels[0].modelId);
        }
      } catch (e) {
        console.error('加载模型列表失败:', e);
      }
    };
    init();
  }, []);

  // 执行个股推理预测
  const handleRunInference = useCallback(async (targetSymbol?: string) => {
    const sym = targetSymbol || symbol;
    if (!sym.trim()) {
      message.warning('请输入有效的股票代码');
      return;
    }

    setLoading(true);
    try {
      // 1. 获取 K 线
      const klineData = await inferenceCenterService.getStockKline(sym, 60);
      setKline(klineData);

      // 2. 获取预测结果
      const dateStr = inferenceDate ? inferenceDate.format('YYYY-MM-DD') : undefined;
      const res = await inferenceCenterService.predictSingleStock({
        symbol: sym,
        model_id: selectedModelId,
        date: dateStr,
        horizon: horizon,
        market: currentMarket,
      });

      setPrediction(res);
      message.success(`已完成 ${res.stock_name} (${res.symbol}) 的 T+${horizon} 区间推理`);
    } catch (e: any) {
      console.error('推理失败:', e);
      message.error(e?.response?.data?.detail || '推理执行失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [symbol, selectedModelId, horizon, inferenceDate, currentMarket]);

  // 初始加载一次默认股票
  useEffect(() => {
    handleRunInference('SH600519');
  }, [handleRunInference]);

  const getRatingBadge = (rating: string) => {
    switch (rating) {
      case 'STRONG_BUY':
        return (
          <div className="flex items-center gap-1.5 text-emerald-700 bg-emerald-100/90 border border-emerald-200/80 px-3 py-1.5 rounded-xl font-black text-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            强烈看多 (STRONG BUY)
          </div>
        );
      case 'BUY':
        return (
          <div className="flex items-center gap-1.5 text-blue-700 bg-blue-100/90 border border-blue-200/80 px-3 py-1.5 rounded-xl font-black text-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
            偏多研判 (BUY)
          </div>
        );
      case 'HOLD':
        return (
          <div className="flex items-center gap-1.5 text-slate-700 bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-xl font-black text-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
            中性观望 (HOLD)
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1.5 text-rose-700 bg-rose-100 border border-rose-200 px-3 py-1.5 rounded-xl font-black text-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
            看空警示 (SELL)
          </div>
        );
    }
  };

  return (
    <div className="w-full h-full relative overflow-hidden flex flex-col p-6 pb-20 select-none">
      {/* 顶部控制台 Bar */}
      <div className="flex items-center justify-between bg-white/75 backdrop-blur-xl rounded-2xl px-6 py-3.5 border border-white/80 shadow-xs mb-4 shrink-0">
        <div className="flex items-center gap-4 flex-1">
          {/* 标的搜索框 */}
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
              <Cpu className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs font-bold text-slate-800">目标个股</span>
              <Input
                placeholder="代码/名称 (如 SH600519)"
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                onPressEnter={() => handleRunInference()}
                style={{ width: 160, height: 32, borderRadius: 8, fontWeight: 700 }}
              />
            </div>
          </div>

          {/* 热门标的快捷胶囊 */}
          <div className="hidden lg:flex items-center gap-1.5 border-l border-slate-200 pl-4">
            <span className="text-[11px] text-slate-400 font-bold">快捷:</span>
            {POPULAR_STOCKS.map(s => (
              <button
                key={s.symbol}
                type="button"
                onClick={() => {
                  setSymbol(s.symbol);
                  handleRunInference(s.symbol);
                }}
                className={`text-[11px] font-bold px-2 py-1 rounded-lg transition-all ${
                  symbol === s.symbol
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'bg-slate-100/80 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>

          {/* 模型选择器 */}
          <div className="flex flex-col border-l border-slate-200 pl-4">
            <span className="text-[11px] font-bold text-slate-400">推理模型架构</span>
            <Select
              value={selectedModelId}
              onChange={val => setSelectedModelId(val)}
              style={{ width: 220, height: 32 }}
              options={models.map(m => ({
                label: (
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs">{m.modelName}</span>
                    <span className="text-[10px] text-blue-500 bg-blue-50 px-1.5 py-0.2 rounded uppercase font-mono">{m.modelType}</span>
                  </div>
                ),
                value: m.modelId,
              }))}
            />
          </div>

          {/* 周期选择器 */}
          <div className="flex flex-col">
            <span className="text-[11px] font-bold text-slate-400">预测周期 (Horizon)</span>
            <Select
              value={horizon}
              onChange={val => setHorizon(val)}
              style={{ width: 100, height: 32 }}
              options={[
                { label: 'T+1 次日', value: 1 },
                { label: 'T+3 周期', value: 3 },
                { label: 'T+5 一周', value: 5 },
                { label: 'T+10 双周', value: 10 },
              ]}
            />
          </div>

          {/* 日期选择器 (支持盲测) */}
          <div className="flex flex-col">
            <span className="text-[11px] font-bold text-slate-400">基准日期 (支持历史盲测)</span>
            <DatePicker
              value={inferenceDate}
              onChange={d => setInferenceDate(d)}
              style={{ width: 130, height: 32, borderRadius: 8 }}
              allowClear={false}
            />
          </div>
        </div>

        {/* 触发推理按钮 */}
        <Button
          type="primary"
          icon={loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
          loading={loading}
          onClick={() => handleRunInference()}
          style={{
            height: 36,
            borderRadius: 10,
            fontWeight: 700,
            background: 'linear-gradient(135deg, #2563eb, #3b82f6)',
            boxShadow: '0 4px 12px rgba(37, 99, 235, 0.25)',
          }}
        >
          开始预测
        </Button>
      </div>

      {/* 主展示区 */}
      {loading && !prediction ? (
        <div className="flex-1 flex flex-col items-center justify-center bg-white/50 backdrop-blur-md rounded-3xl border border-white/60">
          <Spin size="large" />
          <span className="text-sm font-bold text-slate-500 mt-4">正在调用模型提取特征并计算置信区间...</span>
        </div>
      ) : prediction ? (
        <div className="flex-1 min-h-0 flex flex-col gap-4 overflow-y-auto">
          {/* 上半部：核心图表 (左) + 核心指标卡 (右) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ height: '440px', minHeight: '440px' }}>
            {/* 左侧 2/3：K线走势 + 未来走势扇形图 */}
            <div className="lg:col-span-2 bg-white/75 backdrop-blur-xl rounded-3xl border border-white/80 shadow-xs flex flex-col overflow-hidden">
              <StockForecastChart
                kline={kline}
                forecast={prediction.forecast_curve}
                symbol={prediction.symbol}
                stockName={prediction.stock_name}
                currentPrice={prediction.current_price}
              />
            </div>

            {/* 右侧 1/3：综合量化研判看板 */}
            <div className="bg-white/75 backdrop-blur-xl rounded-3xl p-6 border border-white/80 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
                  <span className="text-xs font-bold text-slate-400">AI 量化预测结论</span>
                  <Tag color="blue" className="rounded-md font-mono text-[11px] m-0">T+{prediction.horizon} 预期</Tag>
                </div>

                <div className="mb-4">
                  {getRatingBadge(prediction.rating)}
                </div>

                {/* 预期收益率与置信度 */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="p-3 bg-slate-50/80 rounded-2xl border border-slate-100">
                    <span className="text-[11px] text-slate-400 font-semibold block">预期收益率 (P50)</span>
                    <span className={`text-xl font-black font-mono ${prediction.expected_return >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {prediction.expected_return >= 0 ? `+${prediction.expected_return.toFixed(2)}%` : `${prediction.expected_return.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-50/80 rounded-2xl border border-slate-100">
                    <span className="text-[11px] text-slate-400 font-semibold block">上涨置信概率</span>
                    <span className="text-xl font-black font-mono text-blue-600">
                      {(prediction.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* 10%-50%-90% 分位数区间卡 */}
                <div className="p-4 bg-gradient-to-br from-blue-50/60 to-indigo-50/40 rounded-2xl border border-blue-100/60">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-700">10% - 50% - 90% 置信区间</span>
                    <Tooltip title="基于分位数回归/历史波动率生成的收益分布置信范围">
                      <Info className="w-3.5 h-3.5 text-slate-400 cursor-pointer" />
                    </Tooltip>
                  </div>
                  <div className="flex items-center justify-between text-center pt-1">
                    <div>
                      <span className="text-[10px] text-amber-600 font-bold block">10% 悲观下界</span>
                      <span className="text-xs font-black font-mono text-amber-600">{prediction.p10_return > 0 ? `+${prediction.p10_return}%` : `${prediction.p10_return}%`}</span>
                    </div>
                    <div className="h-6 w-[1px] bg-slate-200" />
                    <div>
                      <span className="text-[10px] text-blue-600 font-bold block">50% 基准中枢</span>
                      <span className="text-sm font-black font-mono text-blue-700">{prediction.p50_return > 0 ? `+${prediction.p50_return}%` : `${prediction.p50_return}%`}</span>
                    </div>
                    <div className="h-6 w-[1px] bg-slate-200" />
                    <div>
                      <span className="text-[10px] text-emerald-600 font-bold block">90% 乐观上界</span>
                      <span className="text-xs font-black font-mono text-emerald-600">+{prediction.p90_return}%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 底部信息条 */}
              <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>当前模型: <strong className="text-slate-600 font-semibold">{prediction.model_name}</strong></span>
                <span>基准价: ¥{prediction.current_price.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* 下半部：单股因子归因 (左) + 多模型共识 (右) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ minHeight: '260px' }}>
            <FeatureDriversPanel drivers={prediction.drivers} />
            <ModelConsensusPanel consensus={prediction.consensus} consensusScore={prediction.consensus_score} />
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default InferenceCenterPage;
