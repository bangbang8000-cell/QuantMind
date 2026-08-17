/** 个股终端主页：左栏检索 + K线区 + 信息 Tab 区（推理中心玻璃卡风格） */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  CandlestickChart, Star, LineChart as LineIcon, Activity, ArrowLeftRight,
  TrendingUp, Layers, BarChart3,
} from 'lucide-react';
import { Button, Select, Tooltip, message } from 'antd';
import { StockListItem, StockProfile, KlineBar } from '../types';
import { stockTerminalService } from '../services/stockTerminalService';
import { StockSidebar, toPrefix } from '../components/StockSidebar';
import { KlineChart, IndicatorConfig, IndexOverlay, OVERLAY_COLORS, SubplotType } from '../components/kline/KlineChart';
import { KlineReplay } from '../components/kline/KlineReplay';
import { OverviewTab } from '../components/OverviewTab';
import { researchService } from '../../../services/researchService';

const INDEX_OPTIONS = [
  { label: '上证指数', value: '000001.SH' },
  { label: '深证成指', value: '399001.SZ' },
  { label: '沪深300', value: '000300.SH' },
  { label: '中证500', value: '000905.SZ' },
];

const SUBPLOT_META: Record<SubplotType, string> = { vol: 'VOL', macd: 'MACD', kdj: 'KDJ', rsi: 'RSI' };

type InfoTab = 'overview' | 'financials' | 'valuation' | 'chipflow' | 'margin' | 'sentiment' | 'holders';

const TAB_META: { id: InfoTab; label: string; soon?: boolean }[] = [
  { id: 'overview', label: '概况' },
  { id: 'financials', label: '财务报表', soon: true },
  { id: 'valuation', label: '估值', soon: true },
  { id: 'chipflow', label: '筹码资金', soon: true },
  { id: 'margin', label: '融资融券', soon: true },
  { id: 'sentiment', label: '技术形态', soon: true },
  { id: 'holders', label: '股东分红', soon: true },
];

export default function StockTerminalPage() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<StockListItem | null>(null);
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [profile, setProfile] = useState<StockProfile | null>(null);
  const [loadingKline, setLoadingKline] = useState(false);

  const [config, setConfig] = useState<IndicatorConfig>({ ma: true, boll: false, subplots: ['vol', 'macd'] });
  const [overlayCodes, setOverlayCodes] = useState<string[]>([]);
  const [overlayCache, setOverlayCache] = useState<Record<string, { date: string; close: number }[]>>({});

  // 回放
  const [replayActive, setReplayActive] = useState(false);
  const [replayCursor, setReplayCursor] = useState(1);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);

  // 自选
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const [onlyWatchlist, setOnlyWatchlist] = useState(false);
  const [infoTab, setInfoTab] = useState<InfoTab>('overview');

  // 加载自选
  useEffect(() => {
    researchService.getWatchlist(200).then(resp => {
      setWatchlist(new Set(resp.items.map(i => i.symbol)));
    }).catch(() => setWatchlist(new Set()));
  }, []);

  // 选股 -> 拉 K线 + 概况
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoadingKline(true);
    setReplayActive(false);
    setReplayCursor(1);
    stockTerminalService.getDailyKline(selected.symbol, 500).then(items => {
      if (!cancelled) setBars(items);
    }).finally(() => { if (!cancelled) setLoadingKline(false); });
    stockTerminalService.getProfile(selected.symbol).then(p => {
      if (!cancelled) setProfile(p);
    });
    return () => { cancelled = true; };
  }, [selected]);

  // 指数叠加懒加载
  useEffect(() => {
    overlayCodes.forEach(async code => {
      if (overlayCache[code]) return;
      const closes = await stockTerminalService.getIndexKline(code, 500);
      setOverlayCache({ ...overlayCache, [code]: closes });
    });
  }, [overlayCodes, overlayCache]);

  const overlays: IndexOverlay[] = useMemo(
    () => overlayCodes
      .filter(c => overlayCache[c]?.length)
      .map((c, i) => ({
        code: c,
        name: INDEX_OPTIONS.find(o => o.value === c)?.label ?? c,
        closes: overlayCache[c],
        color: OVERLAY_COLORS[i % OVERLAY_COLORS.length],
      })),
    [overlayCodes, overlayCache],
  );

  // 回放截断
  const visibleBars = useMemo(() => {
    if (!replayActive || bars.length === 0) return bars;
    const n = Math.max(30, Math.round(replayCursor * bars.length));
    return bars.slice(0, n);
  }, [bars, replayActive, replayCursor]);

  const isWatched = selected ? watchlist.has(toPrefix(selected.symbol)) : false;

  const toggleWatch = useCallback(async () => {
    if (!selected) return;
    const prefix = toPrefix(selected.symbol);
    try {
      if (isWatched) {
        await researchService.removeFromWatchlist(prefix);
        const n = new Set(watchlist);
        n.delete(prefix);
        setWatchlist(n);
        message.success(`已移出自选：${selected.name}`);
      } else {
        await researchService.addToWatchlist(prefix, { stockName: selected.name });
        const n = new Set(watchlist);
        n.add(prefix);
        setWatchlist(n);
        message.success(`已加入自选：${selected.name}`);
      }
    } catch {
      message.error('自选操作失败，请重试');
    }
  }, [selected, isWatched, watchlist]);

  const toggleSubplot = (sp: SubplotType) => {
    setConfig({
      ...config,
      subplots: config.subplots.includes(sp)
        ? config.subplots.filter(x => x !== sp)
        : [...config.subplots, sp],
    });
  };

  const up = (selected?.pct_change ?? profile?.pct_change ?? 0) >= 0;

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

      {/* 右侧 */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">

        {/* K 线区 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs flex flex-col overflow-hidden shrink-0"
          style={{ height: 520 }}
        >
          {/* 头部工具条 */}
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-100">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                <CandlestickChart className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-black text-slate-800 truncate">
                    {selected ? selected.name : '选择股票'}
                  </span>
                  {selected && (
                    <span className="text-[11px] font-mono text-slate-400">{selected.symbol}</span>
                  )}
                </div>
                {selected && (
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[11px] font-mono font-bold ${up ? 'text-rose-500' : 'text-emerald-500'}`}>
                      {profile?.close?.toFixed(2) ?? '--'} {up ? '+' : ''}{(profile?.pct_change ?? 0).toFixed(2)}%
                    </span>
                    <span className="text-[10px] text-slate-400">{profile?.board} · {profile?.industry ?? '--'}</span>
                  </div>
                )}
              </div>
            </div>

            {/* 指标/叠加/回放控制 */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg p-0.5">
                {([
                  ['MA', 'ma', LineIcon],
                  ['BOLL', 'boll', Activity],
                ] as const).map(([label, key, Icon]) => (
                  <button
                    key={key}
                    onClick={() => setConfig({ ...config, [key]: !config[key as 'ma' | 'boll'] })}
                    className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-bold transition-colors ${
                      config[key] ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-400 hover:text-slate-600'
                    }`}
                  >
                    <Icon className="w-2.5 h-2.5" /> {label}
                  </button>
                ))}
                {(['vol', 'macd', 'kdj', 'rsi'] as SubplotType[]).map(sp => (
                  <button
                    key={sp}
                    onClick={() => toggleSubplot(sp)}
                    className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold transition-colors ${
                      config.subplots.includes(sp) ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-400 hover:text-slate-600'
                    }`}
                  >
                    {SUBPLOT_META[sp]}
                  </button>
                ))}
              </div>

              <Select
                mode="multiple"
                allowClear
                maxCount={4}
                placeholder="叠加指数"
                value={overlayCodes}
                onChange={setOverlayCodes}
                options={INDEX_OPTIONS}
                size="small"
                style={{ minWidth: 150 }}
                maxTagTextLength={4}
                popupMatchSelectWidth={false}
              />

              <KlineReplay
                active={replayActive}
                onToggle={() => { setReplayActive(!replayActive); setReplayCursor(0.5); setReplayPlaying(false); }}
                cursor={replayCursor}
                onCursor={setReplayCursor}
                playing={replayPlaying}
                onPlaying={setReplayPlaying}
                speed={replaySpeed}
                onSpeed={setReplaySpeed}
                totalBars={bars.length}
                cursorIndex={visibleBars.length}
              />

              <Tooltip title={isWatched ? '移出自选' : '加入自选'}>
                <Button
                  size="small"
                  type="text"
                  onClick={toggleWatch}
                  disabled={!selected}
                  icon={<Star className={`w-3.5 h-3.5 ${isWatched ? 'fill-amber-400 text-amber-400' : 'text-slate-400'}`} />}
                />
              </Tooltip>
              <Tooltip title="添加到模拟盘">
                <Button
                  size="small"
                  type="text"
                  disabled={!selected}
                  onClick={() => navigate('/trading', { state: { symbol: selected?.symbol } })}
                  icon={<ArrowLeftRight className="w-3.5 h-3.5 text-slate-500" />}
                />
              </Tooltip>
            </div>
          </div>

          {/* 图表 */}
          <div className="flex-1 min-h-0">
            {loadingKline ? (
              <div className="h-full flex items-center justify-center text-[11px] text-slate-400 gap-2">
                <TrendingUp className="w-4 h-4 animate-pulse text-blue-400" /> 加载 K 线数据…
              </div>
            ) : bars.length ? (
              <KlineChart bars={visibleBars} config={config} overlays={overlays} height={452} />
            ) : (
              <div className="h-full flex flex-col items-center justify-center gap-2 text-slate-400">
                <BarChart3 className="w-8 h-8 opacity-40" />
                <span className="text-[11px]">从左侧选择股票查看 K 线</span>
              </div>
            )}
          </div>
        </motion.div>

        {/* 信息 Tab 区 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.08 }}
          className="bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs flex flex-col overflow-hidden flex-1 min-h-0"
        >
          <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
            <div className="flex items-center gap-1">
              {TAB_META.map(t => (
                <button
                  key={t.id}
                  disabled={t.soon}
                  onClick={() => setInfoTab(t.id)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-colors flex items-center gap-1 ${
                    infoTab === t.id
                      ? 'bg-blue-50 text-blue-600'
                      : t.soon
                        ? 'text-slate-300 cursor-not-allowed'
                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {t.label}
                  {t.soon && <span className="text-[9px] bg-slate-100 rounded px-0.5 text-slate-400">P2</span>}
                </button>
              ))}
            </div>
            {profile && (
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <Layers className="w-3 h-3 text-slate-300" />
                本地 QuantDB · {profile.trade_date || '--'}
              </div>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-3">
            {infoTab === 'overview' && <OverviewTab profile={profile} />}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
