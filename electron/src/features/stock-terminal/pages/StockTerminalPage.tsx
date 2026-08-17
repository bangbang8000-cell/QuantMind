/** 个股终端主页：左栏检索列表 + 右侧推理研究看板 + 信息 Tab；点股票名弹整合 K 线窗 */

import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CandlestickChart, Star, Layers, AlertCircle, Database, FlaskConical } from 'lucide-react';
import { Modal, Spin, Tooltip, Tag, Button, message } from 'antd';
import { StockListItem, StockProfile } from '../types';
import { stockTerminalService } from '../services/stockTerminalService';
import { StockSidebar } from '../components/StockSidebar';
import { TagStrip } from '../components/TagStrip';
import { KlineWorkspace } from '../components/kline/KlineWorkspace';
import { OverviewTab } from '../components/OverviewTab';
import { FinancialsTab, ValuationTab, ChipFlowTab, MarginTab, SentimentTab, HoldersTab } from '../components/tabs/P2Tabs';
import { NewsTab } from '../components/tabs/NewsTab';
import { inferenceCenterService, SingleStockPredictionResponse, KlineItem, ForecastPoint } from '../../../services/inferenceCenterService';
import { StockForecastChart } from '../../inference-center/components/StockForecastChart';
import { FeatureDriversPanel } from '../../inference-center/components/FeatureDriversPanel';
import { ModelConsensusPanel } from '../../inference-center/components/ModelConsensusPanel';

type InfoTab = 'overview' | 'financials' | 'valuation' | 'chipflow' | 'margin' | 'sentiment' | 'holders' | 'news';

const TAB_META: { id: InfoTab; label: string }[] = [
  { id: 'overview', label: '概况' },
  { id: 'financials', label: '财务报表' },
  { id: 'valuation', label: '估值' },
  { id: 'chipflow', label: '筹码资金' },
  { id: 'margin', label: '融资融券' },
  { id: 'sentiment', label: '技术形态' },
  { id: 'holders', label: '股东分红' },
  { id: 'news', label: '个股资讯' },
];

function getRatingBadge(rating: string) {
  const map: Record<string, { color: string; bg: string; label: string }> = {
    STRONG_BUY: { color: '#e11d48', bg: '#ffe4e6', label: '强烈买入' },
    BUY: { color: '#f43f5e', bg: '#fff1f2', label: '买入' },
    HOLD: { color: '#64748b', bg: '#f1f5f9', label: '持有' },
    SELL: { color: '#059669', bg: '#d1fae5', label: '卖出' },
  };
  const m = map[rating] || map.HOLD;
  return <span className="text-[10px] font-black px-2 py-1 rounded-lg" style={{ color: m.color, background: m.bg }}>{m.label}</span>;
}

export default function StockTerminalPage() {
  const [selected, setSelected] = useState<StockListItem | null>(null);
  const [profile, setProfile] = useState<StockProfile | null>(null);
  const [klineOpen, setKlineOpen] = useState(false);
  const [infoTab, setInfoTab] = useState<InfoTab>('overview');
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const [onlyWatchlist, setOnlyWatchlist] = useState(false);

  // 推理研究状态（复制推理中心预测）
  const [prediction, setPrediction] = useState<SingleStockPredictionResponse | null>(null);
  const [predictKline, setPredictKline] = useState<KlineItem[]>([]);
  const [predictLoading, setPredictLoading] = useState(false);
  const [horizon, setHorizon] = useState(5);

  useEffect(() => {
    if (!selected) { setPrediction(null); setProfile(null); return; }
    let cancelled = false;
    stockTerminalService.getProfile(selected.symbol).then(p => { if (!cancelled) setProfile(p); });
    // 推理预测（默认模型、T+5）
    setPredictLoading(true);
    inferenceCenterService.predictSingleStock({
      symbol: selected.symbol,
      horizon,
      market: 'A',
    }).then(p => { if (!cancelled) setPrediction(p); }).catch(() => { if (!cancelled) setPrediction(null); }).finally(() => { if (!cancelled) setPredictLoading(false); });
    // 预测图需要 K 线历史（推理中心同款加载）
    stockTerminalService.getDailyKline(selected.symbol, 120).then(items => {
      if (!cancelled) setPredictKline(items.map(it => ({ date: it.date, open: it.open, high: it.high, low: it.low, close: it.close, volume: it.volume ?? 0 })));
    }).catch(() => { if (!cancelled) setPredictKline([]); });
    return () => { cancelled = true; };
  }, [selected, horizon]);

  useEffect(() => {
    researchService_getWatchlist();
  }, []);
  const researchService_getWatchlist = async () => {
    try {
      const { researchService } = await import('../../../services/researchService');
      const resp = await researchService.getWatchlist(200);
      setWatchlist(new Set(resp.items.map(i => i.symbol)));
    } catch { setWatchlist(new Set()); }
  };

  const isWatched = selected ? watchlist.has(`SH${selected.symbol.split('.')[0]}`.replace(/^SH(0)/, 'SH$1')) : false;

  const up = (profile?.pct_change ?? 0) >= 0;

  return (
    <div className="w-full h-full relative overflow-hidden flex gap-4 p-5 pt-3 pb-5 select-none"
      style={{ background: 'linear-gradient(135deg, #f8fafc 0%, #eff6ff 50%, #f8fafc 100%)' }}>

      {/* 左栏 */}
      <StockSidebar
        selected={selected?.symbol ?? null}
        onSelect={setSelected}
        watchlistSymbols={watchlist}
        onlyWatchlist={onlyWatchlist}
        onOnlyWatchlist={setOnlyWatchlist}
      />

      {/* 右侧：推理研究 + 信息 Tabs（默认不显示 K 线） */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">

        {/* 顶部标头：股票名（点击弹整合 K 线） + 推理研究概览 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs px-4 py-3 flex items-center justify-between shrink-0"
        >
          <button
            onClick={() => selected && setKlineOpen(true)}
            disabled={!selected}
            className="flex items-center gap-2.5 min-w-0 hover:opacity-80 disabled:opacity-40 transition-opacity text-left"
            title="点击查看完整 K 线"
          >
            <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
              <CandlestickChart className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-base font-black text-slate-800 truncate">{selected ? selected.name : '选择股票'}</span>
                {selected && <span className="text-[11px] font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-lg">{selected.symbol}</span>}
              </div>
              {selected && (
                <div className="flex items-center gap-2">
                  <span className={`text-[11px] font-mono font-bold ${up ? 'text-rose-500' : 'text-emerald-500'}`}>
                    {profile?.close?.toFixed(2) ?? '--'} {up ? '+' : ''}{(profile?.pct_change ?? 0).toFixed(2)}%
                  </span>
                  <span className="text-[10px] text-slate-400">{profile?.board} · {profile?.industry ?? '--'}</span>
                  <span className="text-[10px] text-slate-300 flex items-center gap-0.5">
                    <CandlestickChart className="w-2.5 h-2.5" /> 点击查看 K 线
                  </span>
                </div>
              )}
            </div>
          </button>

          <div className="flex items-center gap-2">
            {/* 预测评级 */}
            {prediction && getRatingBadge(prediction.rating)}
            {prediction && (
              <div className="flex items-center gap-1.5 bg-blue-50/80 border border-blue-100 px-2.5 py-1 rounded-xl">
                <span className="text-[10px] text-slate-500 font-semibold">T+{prediction.horizon} 预期</span>
                <span className={`text-xs font-black font-mono ${(prediction.expected_return ?? 0) >= 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {(prediction.expected_return ?? 0) >= 0 ? '+' : ''}{(prediction.expected_return ?? 0).toFixed(2)}%
                </span>
              </div>
            )}
            {prediction?.data_source === 'persisted' ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-md border border-emerald-100">
                <Database className="w-2.5 h-2.5" /> 真实推理分数
              </span>
            ) : prediction?.data_source === 'mock' ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded-md border border-slate-200">
                <FlaskConical className="w-2.5 h-2.5" /> 离线模拟
              </span>
            ) : prediction ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded-md border border-amber-100">
                <AlertCircle className="w-2.5 h-2.5" /> 无持久化分数
              </span>
            ) : null}
          </div>
        </motion.div>

        {/* 推理研究内容（复制推理中心的扇形图/分位数/因子归因/共识） */}
        {selected && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.04 }}
            className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs p-3 shrink-0"
          >
            {predictLoading ? (
              <div className="h-56 flex items-center justify-center text-[11px] text-slate-400 gap-2">
                <Spin size="small" /> 推理分析中…
              </div>
            ) : prediction ? (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                {/* 扇形预测图（左 2/3，复用推理中心组件） */}
                <div className="lg:col-span-2 bg-white/70 rounded-2xl border border-slate-100 overflow-hidden">
                  <StockForecastChart
                    kline={predictKline}
                    forecast={prediction.forecast_curve ?? []}
                    symbol={prediction.symbol}
                    stockName={prediction.stock_name}
                    currentPrice={prediction.current_price ?? 0}
                  />
                </div>
                {/* 分位数收益（右 1/3） */}
                <div className="bg-white/70 rounded-2xl border border-slate-100 p-3 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-2 border-b border-slate-100 mb-2">
                      <span className="text-[11px] font-bold text-slate-500">分位数收益预测</span>
                      <Tag color="cyan" className="rounded font-mono text-[10px] m-0">Pinball</Tag>
                    </div>
                    <div className="p-3 bg-slate-50/80 rounded-2xl border border-slate-100 mb-2 text-center">
                      <span className="text-[10px] text-slate-400 font-semibold block mb-0.5">T+{prediction.horizon} 基准收益率 (P50)</span>
                      <span className={`text-xl font-black font-mono ${(prediction.expected_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {(prediction.expected_return ?? 0) >= 0 ? '+' : ''}{(prediction.expected_return ?? 0).toFixed(2)}%
                      </span>
                    </div>
                    <div className="p-3 bg-gradient-to-br from-blue-50/60 to-indigo-50/40 rounded-2xl border border-blue-100/60">
                      <div className="flex items-center justify-between text-center">
                        <div>
                          <span className="text-[10px] text-amber-600 font-bold block">10% 下界</span>
                          <span className="text-xs font-black font-mono text-amber-600">{(prediction.p10_return ?? 0) > 0 ? '+' : ''}{prediction.p10_return}%</span>
                        </div>
                        <div className="h-6 w-[1px] bg-slate-200" />
                        <div>
                          <span className="text-[10px] text-blue-600 font-bold block">50% 中枢</span>
                          <span className="text-sm font-black font-mono text-blue-700">{(prediction.p50_return ?? 0) > 0 ? '+' : ''}{prediction.p50_return}%</span>
                        </div>
                        <div className="h-6 w-[1px] bg-slate-200" />
                        <div>
                          <span className="text-[10px] text-emerald-600 font-bold block">90% 上界</span>
                          <span className="text-xs font-black font-mono text-emerald-600">{(prediction.p90_return ?? 0) > 0 ? '+' : ''}{prediction.p90_return}%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex items-center justify-between">
                    <span>基准价: <strong className="text-slate-700 font-mono">¥{(prediction.current_price ?? 0).toFixed(2)}</strong></span>
                    <span>模型: <strong className="text-slate-700">{prediction.model_name || prediction.model_id}</strong></span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-40 flex flex-col items-center justify-center gap-2 text-slate-400">
                <AlertCircle className="w-6 h-6 opacity-40" />
                <span className="text-[11px]">当前股票暂无推理分数</span>
              </div>
            )}
            {/* 因子归因 + 多模型共识 */}
            {prediction && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
                <FeatureDriversPanel drivers={prediction.drivers ?? []} source={(prediction as any).drivers_source} />
                <ModelConsensusPanel consensus={prediction.consensus ?? []} consensusScore={(prediction as any).consensus_score ?? 0} />
              </div>
            )}
          </motion.div>
        )}

        {/* 信息 Tab 区 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.08 }}
          className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs flex flex-col overflow-hidden flex-1 min-h-0"
        >
          <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
            <div className="flex items-center gap-1 flex-wrap">
              {TAB_META.map(t => (
                <button key={t.id} onClick={() => setInfoTab(t.id)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-colors ${infoTab === t.id ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}>
                  {t.label}
                </button>
              ))}
            </div>
            {profile && (
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400 shrink-0">
                <Layers className="w-3 h-3 text-slate-300" />
                本地 QuantDB · {profile.trade_date || '--'}
              </div>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-3">
            {infoTab === 'overview' && <OverviewTab profile={profile} />}
            {infoTab === 'financials' && selected && <FinancialsTab symbol={selected.symbol} />}
            {infoTab === 'valuation' && selected && <ValuationTab symbol={selected.symbol} />}
            {infoTab === 'chipflow' && selected && <ChipFlowTab symbol={selected.symbol} />}
            {infoTab === 'margin' && selected && <MarginTab symbol={selected.symbol} />}
            {infoTab === 'sentiment' && selected && <SentimentTab symbol={selected.symbol} />}
            {infoTab === 'holders' && selected && <HoldersTab symbol={selected.symbol} />}
            {infoTab === 'news' && selected && <NewsTab symbol={selected.symbol} />}
          </div>
        </motion.div>
      </div>

      {/* 整合 K 线弹窗 */}
      <Modal
        open={klineOpen}
        onCancel={() => setKlineOpen(false)}
        footer={null}
        width={1080}
        destroyOnClose
        title={
          <span className="text-sm font-black text-slate-800 flex items-center gap-2">
            <CandlestickChart className="w-4 h-4 text-blue-600" />
            {selected?.name} · {selected?.symbol} 完整 K 线
          </span>
        }
        styles={{ body: { height: 560, padding: 0 } }}
      >
        {selected && klineOpen && (
          <div className="h-full">
            <TagStrip symbol={selected.symbol} onSelectStock={setSelected} />
            <div className="h-[calc(100%-36px)]">
              <KlineWorkspace stock={selected} profile={profile} height={520} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
