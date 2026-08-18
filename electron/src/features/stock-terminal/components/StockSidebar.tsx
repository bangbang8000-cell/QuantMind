/** 个股终端左侧栏：搜索 + 市场分段 + 看板筛选（页面持有条件）+ 信息丰富的股票列表 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, RefreshCw, Star } from 'lucide-react';
import { Input, Spin, message } from 'antd';
import { StockListItem, StockListResponse } from '../types';
import { stockTerminalService } from '../services/stockTerminalService';
import { ListFilters, bucketScoreRange, StockFilterPanel } from './StockFilterPanel';

interface Props {
  selected: string | null;
  onSelect: (item: StockListItem) => void;
  watchlistSymbols: Set<string>;   // prefix 格式（SH600519）
  onlyWatchlist: boolean;
  onOnlyWatchlist: (v: boolean) => void;
  /** 筛选条件（页面持有，看板面板在左侧列表上方） */
  filters: ListFilters;
  onFiltersChange: (f: ListFilters) => void;
  onModels?: (models: { model_id: string; display_name?: string }[]) => void;
  /** 全部模型列表（页面持有，用于筛选面板下拉选项） */
  models?: { model_id: string; display_name?: string }[];
  /** 列表数量回传（供筛选面板计数） */
  onTotals?: (filtered: number) => void;
  /** 全市场总量（筛选面板命中统计） */
  fullTotal?: number;
}

const PAGE_SIZE = 100;

function fmtPct(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return '--';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function fmtMv(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return '--';
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万亿`;
  return `${v.toFixed(0)}亿`;
}

/** suffix(600519.SH) -> prefix(SH600519)，自选表用 prefix 格式 */
export function toPrefix(symbol: string): string {
  const [code, ex] = symbol.split('.');
  return ex && code ? `${ex}${code}` : symbol;
}

const SIDE_COLOR: Record<string, string> = {
  BUY: 'bg-rose-50 text-rose-600',
  SELL: 'bg-emerald-50 text-emerald-600',
  HOLD: 'bg-slate-50 text-slate-400',
};

const TREND_COLOR: Record<string, string> = {
  '连续上升': 'text-rose-500',
  '上升': 'text-rose-400',
  '先升后降': 'text-amber-600 font-bold',
  '连续下降': 'text-emerald-600',
  '下降': 'text-emerald-500',
};

/** 板块按市场着色（板块/行业两列共用） */
export const BOARD_TONE: Record<string, string> = {
  '沪市主板': 'bg-rose-50 text-rose-600 border-rose-200',
  '深市主板': 'bg-blue-50 text-blue-600 border-blue-200',
  '科创板': 'bg-violet-50 text-violet-600 border-violet-200',
  '创业板': 'bg-amber-50 text-amber-600 border-amber-200',
  '北交所': 'bg-emerald-50 text-emerald-600 border-emerald-200',
};

export function boardToneOf(board?: string): string {
  return board ? (BOARD_TONE[board] ?? 'bg-slate-50 text-slate-500 border-slate-200') : 'bg-slate-50 text-slate-400 border-slate-200';
}

const MARKETS: [string, string][] = [['ALL', '全部'], ['SH', '沪市'], ['SZ', '深市'], ['BJ', '北交']];

export function StockSidebar({ selected, onSelect, watchlistSymbols, onlyWatchlist, onOnlyWatchlist, filters, onFiltersChange, onModels, models: modelOptions = [], onTotals, fullTotal = 0 }: Props) {
  const [market, setMarket] = useState('ALL');
  const [q, setQ] = useState('');
  const [data, setData] = useState<StockListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [optionCounts, setOptionCounts] = useState<Record<string, Record<string, number>>>({});
  const listRef = useRef<HTMLDivElement>(null);
  const itemsRef = useRef<StockListItem[]>([]);
  const initialAutoSelected = useRef(false);

  const fetchList = useCallback(async (page = 1, append = false) => {
    setLoading(true);
    try {
      const range = bucketScoreRange(filters.bucket);
      const resp = await stockTerminalService.getStockList({
        market, q: q || undefined, page, page_size: PAGE_SIZE,
        date: filters.date,
        score_min: range.min ?? filters.scoreMin,
        score_max: range.max,
        model: filters.model,
        industry: filters.industry,
        concept: filters.concept,
        board: filters.board,
        cap_tier: filters.capTier,
        trend: filters.trend,
        tag: filters.tagId,
        index_code: filters.indexCode,
        with_counts: !append,  // 下拉命中数只在首页请求附带
      });
      const models = resp.models ?? [];
      if (models.length) onModels?.(models);
      if (!append) setOptionCounts(resp.option_counts ?? {});
      itemsRef.current = append ? [...itemsRef.current, ...resp.items] : resp.items;
      setData({ ...resp, items: itemsRef.current });
      onTotals?.(resp.total);
      // 默认选中排名第一（仅首次加载且未选中）
      if (!append && !initialAutoSelected.current && !selected && itemsRef.current.length) {
        initialAutoSelected.current = true;
        onSelect(itemsRef.current[0]);
      }
    } catch {
      if (!append) message.error('股票列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [market, q, filters, selected, onModels, onTotals, onSelect]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = setTimeout(() => fetchList(1, false), q ? 300 : 0);
    return () => clearTimeout(t);
  }, [fetchList, q]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (!el || loading || !data) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      if (data.items.length < data.total) fetchList(data.page + 1, true);
    }
  }, [loading, data, fetchList]);

  const visibleItems = useMemo(
    () => onlyWatchlist ? (data?.items ?? []).filter(it => watchlistSymbols.has(toPrefix(it.symbol))) : (data?.items ?? []),
    [data, onlyWatchlist, watchlistSymbols],
  );

  // 板块等列紧凑化，1.7fr 把剩余空间都留给股票名称
  const GRID = 'grid grid-cols-[30px_1.7fr_62px_86px_48px_56px_54px_34px] gap-1';

  return (
    <div className="w-[37rem] shrink-0 flex flex-col bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs p-4 overflow-hidden">
      {/* 搜索框 + 市场分段 + 自选（自选放北交后面，省空间） */}
      <div className="flex items-center gap-1.5 mb-2">
        <div className="flex-1 flex items-center bg-white border border-slate-200 hover:border-blue-400 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 rounded-xl px-3 py-1 transition-all shadow-2xs">
          <Search className="w-3.5 h-3.5 text-blue-500 shrink-0" />
          <Input
            variant="borderless"
            placeholder="输入代码 / 名称"
            value={q}
            onChange={e => setQ(e.target.value)}
            allowClear
            className="p-0 font-mono font-bold text-sm text-blue-600"
            style={{ padding: 0 }}
          />
        </div>
        <div className="grid grid-cols-5 gap-0.5 p-0.5 bg-slate-100/70 rounded-lg shrink-0">
          {MARKETS.map(([v, label]) => (
            <button
              key={v}
              onClick={() => setMarket(v)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all ${
                market === v ? 'bg-white text-blue-600 shadow-2xs' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {label}
            </button>
          ))}
          <button
            onClick={() => onOnlyWatchlist(!onlyWatchlist)}
            title="只看自选"
            className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all flex items-center justify-center gap-0.5 ${
              onlyWatchlist ? 'bg-white text-amber-600 shadow-2xs' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Star className="w-2.5 h-2.5" /> 自选
          </button>
        </div>
      </div>

      {/* 看板筛选（条件由页面持有，命中组合每条件单独一行） */}
      <StockFilterPanel
        filters={filters}
        onChange={onFiltersChange}
        total={data?.total ?? 0}
        fullTotal={fullTotal}
        models={modelOptions}
        compact
        optionCounts={optionCounts}
      />

      {/* 列表头 */}
      <div className={`${GRID} px-1 pb-1 pt-2 text-[10px] font-bold text-slate-400 border-b border-slate-100 shrink-0`}>
        <span className="text-center">排名</span><span>股票</span><span className="text-center">板块</span><span className="text-center">行业</span>
        <span className="text-center">市值</span><span className="text-center">趋势</span><span className="text-right">得分</span><span className="text-center">信号</span>
      </div>

      {/* 股票列表 */}
      <div ref={listRef} onScroll={handleScroll} className="flex-1 min-h-0 overflow-x-auto overflow-y-auto">
        <Spin spinning={loading && !data} size="small">
          {visibleItems.map((it, i) => {
            const isSel = it.symbol === selected;
            const up = (it.pct_change ?? 0) >= 0;
            const rank = i + 1;
            const rankMedal = rank <= 3 ? ['🥇', '🥈', '🥉'][rank - 1] : String(rank);
            return (
              <button
                key={it.symbol}
                onClick={() => onSelect(it)}
                className={`w-full ${GRID} items-center px-1.5 py-1.5 rounded-lg text-left transition-colors ${
                  isSel ? 'bg-blue-50 border border-blue-200' : 'hover:bg-slate-50 border border-transparent'
                }`}
              >
                <span className={`text-center text-[10px] font-mono font-bold ${rank <= 3 ? 'text-base leading-none' : 'text-slate-400'}`}>{rankMedal}</span>
                {/* 股票单元格：2行2列表格（名称|涨幅 / 代码|价格·市值），搜索输入时实时刷新 */}
                <span className="flex flex-col min-w-0">
                  <span className="flex items-center justify-between gap-1">
                    <span className="text-xs font-bold text-slate-700 truncate flex items-center gap-0.5 min-w-0">
                      {watchlistSymbols.has(toPrefix(it.symbol)) && <Star className="w-2.5 h-2.5 text-amber-400 fill-amber-400 shrink-0" />}
                      {it.is_st && <span className="text-[9px] bg-rose-50 text-rose-500 rounded px-0.5 shrink-0">ST</span>}
                      <span className="truncate">{it.name}</span>
                    </span>
                    <span className={`text-[10px] font-mono shrink-0 ${up ? 'text-rose-500' : 'text-emerald-500'}`}>{fmtPct(it.pct_change)}</span>
                  </span>
                  <span className="flex items-center justify-between gap-1">
                    <span className="text-[9px] text-slate-400 font-mono truncate">{it.symbol}</span>
                    <span className="text-[10px] text-slate-500 font-mono shrink-0">{it.close?.toFixed(2) ?? '--'} · {fmtMv(it.total_mv)}</span>
                  </span>
                </span>
                <span className="text-center">
                  <span className={`inline-block text-[8px] font-bold rounded px-0.5 py-0.5 border max-w-full truncate ${boardToneOf(it.board)}`} title={it.board}>
                    {it.board?.replace('市主板', '主板') ?? '--'}
                  </span>
                </span>
                <span className="text-[10px] text-slate-500 text-center truncate" title={it.industry ?? ''}>{it.industry ?? '--'}</span>
                <span className="text-[10px] text-slate-500 text-center truncate">{it.cap_tier || '--'}</span>
                <span className={`text-[10px] text-center truncate ${TREND_COLOR[it.trend ?? ''] ?? 'text-slate-400'}`}>{it.trend ?? '-'}</span>
                <span className={`text-right text-[10px] font-mono font-bold ${(it.fusion ?? 0) >= 0 ? 'text-blue-600' : 'text-slate-400'}`}>
                  {it.fusion != null ? `+${(it.fusion).toFixed(3)}`.replace('+-', '-') : '--'}
                </span>
                <span className="text-center">
                  <span className={`text-[9px] rounded px-1 py-0.5 font-bold ${SIDE_COLOR[it.side ?? 'HOLD'] ?? SIDE_COLOR.HOLD}`}>
                    {(it.side ?? 'HOLD') === 'HOLD' ? '-' : it.side}
                  </span>
                </span>
              </button>
            );
          })}
          {loading && data && (
            <div className="flex items-center justify-center py-2 text-[10px] text-slate-400 gap-1">
              <RefreshCw className="w-3 h-3 animate-spin" /> 加载更多…
            </div>
          )}
          {!loading && visibleItems.length === 0 && (
            <div className="text-center py-8 text-[11px] text-slate-400">无匹配股票</div>
          )}
        </Spin>
      </div>
    </div>
  );
}
