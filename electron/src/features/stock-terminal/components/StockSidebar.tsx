/** 个股终端左侧栏：搜索 + 市场分段 + 看板筛选（页面持有条件）+ 信息丰富的股票列表 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, RefreshCw, Star, ChevronDown } from 'lucide-react';
import { Input, Spin, message, Dropdown } from 'antd';
import { StockListItem, StockListResponse } from '../types';
import { stockTerminalService } from '../services/stockTerminalService';
import { ListFilters, bucketScoreRange, StockFilterPanel, BOARD_OPTIONS, CAP_TIER_OPTIONS, TREND_OPTIONS, BUCKET_OPTIONS } from './StockFilterPanel';

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
  /** 当前列表基准信号日回传（日历高亮 + 面板日期 chip） */
  onSignalDate?: (d?: string) => void;
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

export function StockSidebar({ selected, onSelect, watchlistSymbols, onlyWatchlist, onOnlyWatchlist, filters, onFiltersChange, onModels, models: modelOptions = [], onTotals, onSignalDate, fullTotal = 0 }: Props) {
  const [market, setMarket] = useState('ALL');
  const [q, setQ] = useState('');
  const [data, setData] = useState<StockListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [optionCounts, setOptionCounts] = useState<Record<string, Record<string, number>>>({});
  const [facets, setFacets] = useState<Record<string, string[]>>({});
  const listRef = useRef<HTMLDivElement>(null);
  const itemsRef = useRef<StockListItem[]>([]);
  const initialAutoSelected = useRef(false);
  // selected 只影响「首次自动选中」逻辑，不触发列表重新请求（否则点股票整表刷新，表格打架）
  const selectedRef = useRef<string | null>(selected);
  selectedRef.current = selected;
  // 列表跳转：切日期/筛选后选中股票可能掉到几千名——按 find_rank 跳到对应页并滚动到该行。
  // jumpKey 防重复跳转（同一日期+股票只跳一次）；pageOffsetRef 记录当前 items 的起始排名偏移。
  const jumpKeyRef = useRef<string>('');
  const pageOffsetRef = useRef(0);

  /** 组装 /list 请求参数（首页附带 with_counts / find_symbol） */
  const buildParams = useCallback((page: number, withCounts: boolean) => {
    const range = bucketScoreRange(filters.bucket);
    return {
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
      side: filters.side,
      ...(withCounts ? { with_counts: true } : {}),
      ...(withCounts && selectedRef.current ? { find_symbol: selectedRef.current } : {}),
    };
  }, [market, q, filters]);

  const fetchList = useCallback(async (page = 1, append = false) => {
    setLoading(true);
    try {
      const resp = await stockTerminalService.getStockList(buildParams(page, !append));
      const models = resp.models ?? [];
      if (models.length) onModels?.(models);
      if (!append) {
        pageOffsetRef.current = (page - 1) * PAGE_SIZE;
        setOptionCounts(resp.option_counts ?? {});
        setFacets(resp.facets ?? {});
        onSignalDate?.(resp.signal_date);
      }
      itemsRef.current = append ? [...itemsRef.current, ...resp.items] : resp.items;
      setData({ ...resp, items: itemsRef.current });
      onTotals?.(resp.total);
      // 默认选中排名第一（仅首次加载且未选中）
      if (!append && !initialAutoSelected.current && !selectedRef.current && itemsRef.current.length) {
        initialAutoSelected.current = true;
        onSelect(itemsRef.current[0]);
      }
      // 列表自动跳转：选中股票不在当前页时，按 find_rank 跳到其所在页并滚动定位
      const sel = selectedRef.current;
      if (!append && sel && resp.find_rank != null && !resp.items.some(it => it.symbol === sel)) {
        const targetPage = Math.ceil(resp.find_rank / PAGE_SIZE);
        const jumpKey = `${resp.signal_date ?? ''}:${sel}:${targetPage}`;
        if (jumpKeyRef.current !== jumpKey) {
          jumpKeyRef.current = jumpKey;
          const pageResp = await stockTerminalService.getStockList(buildParams(targetPage, false));
          if (pageResp.items.some(it => it.symbol === sel)) {
            pageOffsetRef.current = (targetPage - 1) * PAGE_SIZE;
            itemsRef.current = pageResp.items;
            setData({ ...resp, items: pageResp.items, page: targetPage });
            requestAnimationFrame(() => {
              const row = listRef.current?.querySelector<HTMLElement>(`[data-symbol="${sel}"]`);
              row?.scrollIntoView({ block: 'center' });
            });
          }
        }
      }
    } catch {
      if (!append) message.error('股票列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [buildParams, onModels, onTotals, onSelect, onSignalDate]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const SIDE_LABEL: Record<string, string> = { BUY: '买入', SELL: '卖出', HOLD: '持有' };
  /** 得分档表头短名（列宽有限） */
  const BUCKET_SHORT: Record<string, string> = {
    golden: '黄金', optional: '可选', caution: '谨慎', extreme: '极端高',
    neg_extreme: '极端低', neg_short: '做空', pos: '正分', neg: '负分',
  };

  /** 表头列筛选下拉（板块/行业/市值/趋势/得分/信号），长菜单限高滚动避免盖住整个列表 */
  const headerDropdown = (items: { value: string; label: string }[], current: string | undefined, onPick: (v?: string) => void, placeholder: string) => (
    <Dropdown
      trigger={['click']}
      placement="bottom"
      menu={{
        items: [
          { key: '__all', label: `全部${placeholder}` },
          ...items.map(x => ({ key: x.value, label: x.label })),
        ],
        selectable: true,
        selectedKeys: current ? [current] : ['__all'],
        onClick: ({ key }) => onPick(key === '__all' ? undefined : key),
        style: { maxHeight: 260, overflowY: 'auto' },
      }}
    >
      <button className={`flex items-center justify-center gap-0.5 px-0.5 rounded transition-colors ${current ? 'text-blue-600 font-black' : 'hover:text-blue-500'}`}>
        <span className="truncate">{current ? (SIDE_LABEL[current] ?? current) : placeholder}</span>
        <ChevronDown className="w-2.5 h-2.5 shrink-0 opacity-60" />
      </button>
    </Dropdown>
  );

  /** 列筛选值集合（优先后端 facets，回退全量选项） */
  const fac = (key: string, fallback: { value: string; label: string }[]): { value: string; label: string }[] => {
    const f = facets[key];
    return f && f.length ? f.map(v => ({ value: v, label: v })) : fallback;
  };

  return (
    <div className="w-[37rem] flex-1 min-h-0 flex flex-col bg-white/80 backdrop-blur-xl rounded-3xl border border-white/90 shadow-xs p-4 overflow-hidden">
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

      {/* 筛选面板：columnOnly 只留 模型+概念 两列（其余维度在列表表头筛选） */}
      <StockFilterPanel
        filters={filters}
        onChange={onFiltersChange}
        total={data?.total ?? 0}
        fullTotal={fullTotal}
        models={modelOptions}
        compact
        columnOnly
        optionCounts={optionCounts}
      />

      {/* 当前信号日 chip：随日历切换显示该日期（琥珀底色），点击回到最新 */}
      {(() => {
        // 切了历史日优先显示 filters.date；否则显示最近信号日 signal_date
        const shownDate = filters.date || data?.signal_date;
        if (!shownDate) return null;
        const isHistorical = !!filters.date;
        return (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-[9px] font-bold text-slate-400">信号日</span>
            <button
              onClick={() => onFiltersChange({ ...filters, date: undefined })}
              title={isHistorical ? '当前列表基准日，点击回到最新' : '当前列表基准信号日'}
              className={`shrink-0 text-[10px] font-mono font-bold rounded-md px-1.5 py-0.5 border transition-colors ${
                isHistorical
                  ? 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100'
                  : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
              }`}
            >
              {shownDate}
              {isHistorical && <span className="ml-0.5 opacity-70">✕</span>}
            </button>
          </div>
        );
      })()}

      {/* 列表头：板块/行业/市值/趋势/得分/信号 直接点表头筛选 */}
      <div className={`${GRID} px-1 pb-1 pt-2 text-[10px] font-bold text-slate-400 border-b border-slate-100 shrink-0`}>
        <span className="text-center">排名</span>
        <span>股票</span>
        <span className="text-center">{headerDropdown(fac('board', BOARD_OPTIONS.map(b => ({ value: b, label: b }))), filters.board, v => onFiltersChange({ ...filters, board: v }), '板块')}</span>
        <span className="text-center">{headerDropdown(fac('industry', []), filters.industry, v => onFiltersChange({ ...filters, industry: v }), '行业')}</span>
        <span className="text-center">{headerDropdown(fac('cap_tier', CAP_TIER_OPTIONS), filters.capTier, v => onFiltersChange({ ...filters, capTier: v }), '市值')}</span>
        <span className="text-center">{headerDropdown(fac('trend', TREND_OPTIONS), filters.trend, v => onFiltersChange({ ...filters, trend: v }), '趋势')}</span>
        <span className="text-right">{headerDropdown(fac('bucket', BUCKET_OPTIONS), filters.bucket, v => onFiltersChange({ ...filters, bucket: v, scoreMin: undefined }),
          filters.bucket ? (BUCKET_SHORT[filters.bucket] ?? '得分') : '得分')}</span>
        <span className="text-center">{headerDropdown(fac('side', [{ value: 'BUY', label: '买入' }, { value: 'SELL', label: '卖出' }, { value: 'HOLD', label: '持有' }]), filters.side, v => onFiltersChange({ ...filters, side: v }), '信号')}</span>
      </div>

      {/* 股票列表 */}
      <div ref={listRef} onScroll={handleScroll} className="flex-1 min-h-0 overflow-x-auto overflow-y-auto">
        <Spin spinning={loading && !data} size="small">
          {visibleItems.map((it, i) => {
            const isSel = it.symbol === selected;
            const up = (it.pct_change ?? 0) >= 0;
            const rank = pageOffsetRef.current + i + 1;   // 跳页后显示真实名次
            const rankMedal = rank <= 3 ? ['🥇', '🥈', '🥉'][rank - 1] : String(rank);
            return (
              <button
                key={it.symbol}
                data-symbol={it.symbol}
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
