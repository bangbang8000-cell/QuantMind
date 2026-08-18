/** 个股终端主页：左栏检索列表(推理分数/筛选) + 右侧信息 Tab；点股票名弹整合 K 线窗 */

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { CandlestickChart, Layers } from 'lucide-react';
import { Modal } from 'antd';
import { StockListItem, StockProfile } from '../types';
import { stockTerminalService } from '../services/stockTerminalService';
import { StockSidebar } from '../components/StockSidebar';
import { TagStrip } from '../components/TagStrip';
import { KlineWorkspace } from '../components/kline/KlineWorkspace';
import { RankingPanel } from '../components/RankingPanel';
import { OverviewTab } from '../components/OverviewTab';
import { FinancialsTab, ValuationTab, ChipFlowTab, MarginTab, SentimentTab, HoldersTab } from '../components/tabs/P2Tabs';
import { NewsTab } from '../components/tabs/NewsTab';

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

export default function StockTerminalPage() {
  const [selected, setSelected] = useState<StockListItem | null>(null);
  const [profile, setProfile] = useState<StockProfile | null>(null);
  const [klineOpen, setKlineOpen] = useState(false);
  const [infoTab, setInfoTab] = useState<InfoTab>('overview');
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const [onlyWatchlist, setOnlyWatchlist] = useState(false);

  useEffect(() => {
    if (!selected) { setProfile(null); return; }
    let cancelled = false;
    stockTerminalService.getProfile(selected.symbol).then(p => { if (!cancelled) setProfile(p); });
    return () => { cancelled = true; };
  }, [selected]);

  useEffect(() => {
    let cancelled = false;
    import('../../../services/researchService').then(({ researchService }) => {
      return researchService.getWatchlist(200).then(resp => {
        if (!cancelled) setWatchlist(new Set(resp.items.map(i => i.symbol)));
      });
    }).catch(() => { if (!cancelled) setWatchlist(new Set()); });
    return () => { cancelled = true; };
  }, []);

  const up = (profile?.pct_change ?? 0) >= 0;

  return (
    <div className="w-full h-full relative overflow-hidden flex gap-4 p-5 pt-3 pb-5 select-none"
      style={{ background: 'linear-gradient(135deg, #f8fafc 0%, #eff6ff 50%, #f8fafc 100%)' }}>

      {/* 左栏：检索 + 筛选 + 分数列表 */}
      <StockSidebar
        selected={selected?.symbol ?? null}
        onSelect={setSelected}
        watchlistSymbols={watchlist}
        onlyWatchlist={onlyWatchlist}
        onOnlyWatchlist={setOnlyWatchlist}
      />

      {/* 右侧：推理排名 + 信息 Tabs（默认不显示 K 线，点股票弹整合 K 线窗） */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">

        {/* 顶部标头：股票名（点击弹整合 K 线） */}
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
        </motion.div>

        {/* 推理排名（推理研究内容，右侧上方） */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.04 }}
          className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs flex flex-col overflow-hidden shrink-0"
          style={{ height: 300 }}
        >
          <RankingPanel signalDate={profile?.trade_date} onSelectStock={setSelected} onOpenKline={() => setKlineOpen(true)} />
        </motion.div>

        {/* 信息 Tab 区 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.06 }}
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

      {/* 整合 K 线弹窗：左侧 K 线主体（融合全部功能），右侧竖排智能标签 */}
      <Modal
        open={klineOpen}
        onCancel={() => setKlineOpen(false)}
        footer={null}
        width={1160}
        destroyOnClose
        title={null}
        style={{ top: 16 }}
        styles={{ body: { height: 560, padding: 0 } }}
      >
        {selected && klineOpen && (
          <div className="h-full flex">
            {/* 左：K 线主体（周期/指标/指数/回放/信号/回测/多模型分数/模拟交易/参考线） */}
            <div className="flex-1 min-w-0">
              <KlineWorkspace stock={selected} profile={profile} height={500} />
            </div>
            {/* 右：竖排智能标签 */}
            <div className="w-44 shrink-0 border-l border-slate-100 overflow-y-auto">
              <TagStrip symbol={selected.symbol} onSelectStock={setSelected} vertical />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
