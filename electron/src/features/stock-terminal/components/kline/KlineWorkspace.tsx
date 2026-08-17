/** K 线工作区：可嵌入页面或 Modal，含周期/指标/指数叠加/回放/信号/回测全部功能 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CandlestickChart, Star, Activity, TrendingUp, ArrowLeftRight,
} from 'lucide-react';
import { Button, Select, Tooltip, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { StockListItem, StockProfile, KlineBar } from '../../types';
import { stockTerminalService } from '../../services/stockTerminalService';
import { researchService } from '../../../../services/researchService';
import { KlineChart, IndicatorConfig, IndexOverlay, SignalPoint, ScoreSeries, OVERLAY_COLORS, SubplotType } from './KlineChart';
import { KlineReplay } from './KlineReplay';
import { ChartBacktestPanel, ChartBacktestData } from '../ChartBacktestPanel';
import { toPrefix } from '../StockSidebar';

/** 纯数字代码推导市场后缀：SH/SZ/BJ */
export function suffixOf(code: string): string {
  const c = code.replace(/\D/g, '').slice(-6);
  if (c.startsWith('6') || c.startsWith('9')) return `${c}.SH`;
  if (c.startsWith('4') || c.startsWith('8')) return `${c}.BJ`;
  return `${c}.SZ`;
}

const INDEX_OPTIONS = [
  { label: '上证指数', value: '000001.SH' },
  { label: '深证成指', value: '399001.SZ' },
  { label: '沪深300', value: '000300.SH' },
  { label: '中证500', value: '000905.SZ' },
];

const SUBPLOT_META: Record<SubplotType, string> = { vol: 'VOL', macd: 'MACD', kdj: 'KDJ', rsi: 'RSI' };

interface Props {
  stock: StockListItem;
  profile?: StockProfile | null;
  height?: number;
}

export function KlineWorkspace({ stock, profile, height = 460 }: Props) {
  const navigate = useNavigate();
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [loadingKline, setLoadingKline] = useState(false);
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly' | 'min5' | 'min1'>('daily');
  const [minAvail, setMinAvail] = useState<{ min5: boolean; min1: boolean }>({ min5: false, min1: false });
  const [config, setConfig] = useState<IndicatorConfig>({ ma: true, boll: false, subplots: ['vol', 'macd'] });
  const [overlayCodes, setOverlayCodes] = useState<string[]>([]);
  const [overlayCache, setOverlayCache] = useState<Record<string, { date: string; close: number }[]>>({});
  const [signals, setSignals] = useState<SignalPoint[]>([]);
  const [signalOn, setSignalOn] = useState(true);
  const [btData, setBtData] = useState<ChartBacktestData | null>(null);
  const [replayActive, setReplayActive] = useState(false);
  const [replayCursor, setReplayCursor] = useState(1);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  // 推理分数历史（多模型叠加）
  const [scoreModels, setScoreModels] = useState<{ model_id: string; display_name?: string }[]>([]);
  const [scoreSeries, setScoreSeries] = useState<ScoreSeries[]>([]);
  const [scoreLoading, setScoreLoading] = useState(false);

  // 自选状态
  useEffect(() => {
    researchService.getWatchlist(200).then(resp => {
      setWatchlist(new Set(resp.items.map(i => i.symbol)));
    }).catch(() => { /* ignore */ });
  }, []);
  const isWatched = watchlist.has(toPrefix(stock.symbol));

  const toggleWatch = useCallback(async () => {
    const prefix = toPrefix(stock.symbol);
    try {
      if (isWatched) {
        await researchService.removeFromWatchlist(prefix);
        const n = new Set(watchlist); n.delete(prefix); setWatchlist(n);
        message.success(`已移出自选：${stock.name}`);
      } else {
        await researchService.addToWatchlist(prefix, { stockName: stock.name });
        const n = new Set(watchlist); n.add(prefix); setWatchlist(n);
        message.success(`已加入自选：${stock.name}`);
      }
    } catch { message.error('自选操作失败'); }
  }, [stock, isWatched, watchlist]);

  // 加载 K 线 + 信号
  useEffect(() => {
    if (!stock) return;
    let cancelled = false;
    setLoadingKline(true);
    setReplayActive(false);
    setReplayCursor(1);
    setBtData(null);
    const sym = stock.symbol;
    const load = async () => {
      try {
        if (period === 'min5' || period === 'min1') {
          const { items, available } = await stockTerminalService.getMinuteKline(sym, period, 10);
          if (!cancelled) {
            setBars(items);
            setMinAvail(period === 'min1' ? { min5: minAvail.min5, min1: available } : { min5: available, min1: minAvail.min1 });
          }
          return;
        }
        let items = await stockTerminalService.getDailyKline(sym, 250);
        if ((period === 'weekly' || period === 'monthly') && items.length) items = resampleBars(items, period);
        if (!cancelled) setBars(items);
      } finally {
        if (!cancelled) setLoadingKline(false);
      }
    };
    load();
    stockTerminalService.getSignalOverlay(sym).then(sigMap => {
      if (cancelled) return;
      setSignals(Object.values(sigMap).flat().sort((a, b) => a.date.localeCompare(b.date)));
    });
    // 推理分数历史（多模型）：/models/inference/stock/{symbol}/history
    setScoreLoading(true);
    import('../../../../services/modelTrainingService').then(({ modelTrainingService }) => {
      const code = stock.symbol.split('.')[0];
      return modelTrainingService.getStockInferenceHistory(code, 500).then(resp => {
        if (cancelled) return;
        setScoreModels(resp?.models ?? []);
        const byModel = new Map<string, { date: string; fusion: number | null; side: string | null }[]>();
        for (const it of resp?.items ?? []) {
          const m = it.signal_model_id || 'default';
          if (!byModel.has(m)) byModel.set(m, []);
          byModel.get(m)!.push({ date: it.trade_date.slice(0, 10), fusion: it.fusion_score, side: it.signal_side });
        }
        const palette = ['#6366f1', '#f59e0b', '#10b981', '#e11d48', '#0ea5e9'];
        const out: ScoreSeries[] = [...byModel.entries()].map(([m, pts], i) => ({
          model: m, color: palette[i % palette.length],
          points: pts.sort((a, b) => a.date.localeCompare(b.date)),
        }));
        setScoreSeries(out);
      });
    }).catch(() => { if (!cancelled) setScoreSeries([]); }).finally(() => { if (!cancelled) setScoreLoading(false); });
    return () => { cancelled = true; };
  }, [stock, period]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    overlayCodes.forEach(async code => {
      if (overlayCache[code]) return;
      const closes = await stockTerminalService.getIndexKline(code, 250);
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

  const visibleBars = useMemo(() => {
    if (!replayActive || bars.length === 0) return bars;
    const n = Math.max(30, Math.round(replayCursor * bars.length));
    return bars.slice(0, n);
  }, [bars, replayActive, replayCursor]);

  const toggleSubplot = (sp: SubplotType) => {
    setConfig({
      ...config,
      subplots: config.subplots.includes(sp) ? config.subplots.filter(x => x !== sp) : [...config.subplots, sp],
    });
  };

  const up = (profile?.pct_change ?? stock.pct_change ?? 0) >= 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 工具条 */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-slate-100 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
            <CandlestickChart className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-xs font-black text-slate-800 truncate">{stock.name}</span>
            <span className="text-[10px] font-mono text-slate-400">{stock.symbol}</span>
            {profile && (
              <span className={`text-[11px] font-mono font-bold ${up ? 'text-rose-500' : 'text-emerald-500'}`}>
                {profile.close?.toFixed(2) ?? '--'} {up ? '+' : ''}{(profile.pct_change ?? 0).toFixed(2)}%
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="grid grid-cols-5 gap-0.5 p-0.5 bg-slate-100/70 rounded-lg shrink-0">
            {([['daily', '日'], ['weekly', '周'], ['monthly', '月'], ['min5', '5分'], ['min1', '1分']] as const).map(([v, label]) => (
              <button key={v} disabled={v === 'min1' && minAvail.min1 === false && period !== 'min1'}
                onClick={() => setPeriod(v)} title={v === 'min1' && minAvail.min1 === false ? '本地无1分钟数据' : undefined}
                className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold transition-colors ${period === v ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-400 hover:text-slate-600'} disabled:text-slate-200`}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg p-0.5">
            {([
              ['MA', 'ma', Activity],
              ['BOLL', 'boll', Activity],
            ] as const).map(([label, key]) => (
              <button key={key} onClick={() => setConfig({ ...config, [key]: !config[key as 'ma' | 'boll'] })}
                className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold transition-colors ${config[key as 'ma' | 'boll'] ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-400 hover:text-slate-600'}`}>
                {label}
              </button>
            ))}
            {(['vol', 'macd', 'kdj', 'rsi'] as SubplotType[]).map(sp => (
              <button key={sp} onClick={() => toggleSubplot(sp)}
                className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold transition-colors ${config.subplots.includes(sp) ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-400 hover:text-slate-600'}`}>
                {SUBPLOT_META[sp]}
              </button>
            ))}
          </div>
          <Select mode="multiple" allowClear maxCount={4} placeholder="叠加指数" value={overlayCodes}
            onChange={setOverlayCodes} options={INDEX_OPTIONS} size="small" style={{ minWidth: 140 }} maxTagTextLength={4} popupMatchSelectWidth={false} />
          <button onClick={() => setSignalOn(!signalOn)} disabled={!signals.length}
            className={`flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-lg transition-colors ${signalOn && signals.length ? 'bg-rose-50 text-rose-600 border border-rose-100' : 'text-slate-400 hover:text-slate-600 border border-transparent'}`}
            title={signals.length ? '模型推理分数信号' : '无推理信号'}>
            <TrendingUp className="w-3 h-3" /> 信号{signals.length > 0 && <span className="text-[9px] bg-rose-100 rounded px-0.5">{signals.length}</span>}
          </button>
          {scoreSeries.length > 0 && (
            <Tooltip title={`推理历史分数（${scoreSeries.map(s => s.model).join(', ')}）`}>
              <span className="flex items-center gap-1 text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 px-1.5 py-0.5 rounded-lg">
                <TrendingUp className="w-2.5 h-2.5" /> 分数{scoreSeries.length > 1 ? `×${scoreSeries.length}` : ''}
              </span>
            </Tooltip>
          )}
          <ChartBacktestPanel symbol={stock.symbol} onResult={setBtData} />
          <KlineReplay active={replayActive} onToggle={() => { setReplayActive(!replayActive); setReplayCursor(0.5); setReplayPlaying(false); }}
            cursor={replayCursor} onCursor={setReplayCursor} playing={replayPlaying} onPlaying={setReplayPlaying}
            speed={replaySpeed} onSpeed={setReplaySpeed} totalBars={bars.length} cursorIndex={visibleBars.length} />
          <Tooltip title={isWatched ? '移出自选' : '加入自选'}>
            <Button size="small" type="text" onClick={toggleWatch}
              icon={<Star className={`w-3.5 h-3.5 ${isWatched ? 'fill-amber-400 text-amber-400' : 'text-slate-400'}`} />} />
          </Tooltip>
          <Tooltip title="添加到模拟盘">
            <Button size="small" type="text" onClick={() => navigate('/trading', { state: { symbol: stock.symbol } })}
              icon={<ArrowLeftRight className="w-3.5 h-3.5 text-slate-500" />} />
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
          <KlineChart bars={visibleBars} config={config} overlays={overlays} height={height} signals={signalOn ? signals : []} btEquity={btData?.points ?? []} scoreSeries={scoreSeries} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-slate-400">
            <Activity className="w-8 h-8 opacity-40" />
            <span className="text-[11px]">暂无 K 线数据</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** 日线重采样为周/月线 */
function resampleBars(bars: KlineBar[], period: 'weekly' | 'monthly'): KlineBar[] {
  const map = new Map<string, KlineBar[]>();
  for (const b of bars) {
    const key = period === 'weekly' ? weekKey(b.date) : b.date.slice(0, 7);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(b);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, grp]) => ({
    date: period === 'weekly' ? grp[grp.length - 1].date : `${grp[0].date.slice(0, 7)}-月末`,
    open: grp[0].open,
    high: Math.max(...grp.map(g => g.high)),
    low: Math.min(...grp.map(g => g.low)),
    close: grp[grp.length - 1].close,
    volume: grp.reduce((s, g) => s + (g.volume ?? 0), 0),
  }));
}
function weekKey(date: string): string {
  const d = new Date(date + 'T00:00:00');
  const day = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}
