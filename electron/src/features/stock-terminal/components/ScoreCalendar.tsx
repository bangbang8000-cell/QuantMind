/** 分数日历：个股历史推理分数画在月历上（红正绿负、深浅按绝对值、同日多模型取最新） */

import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, CalendarDays } from 'lucide-react';
import { Spin } from 'antd';
import { modelTrainingService } from '../../../services/modelTrainingService';

/** 单日分数条目：value 用于着色，score 为基准值（同 value），side 为信号方向 */
export interface CalendarScore { date: string; value: number; side: string | null; }

/** 月份聚合：key=YYYY-MM（如 2026-08），scores 为当月每日分数（最新覆盖同模型重复） */
export interface MonthBucket { key: string; year: number; month: number; scores: Map<string, number>; sides: Map<string, string>; }

/** 分数着色：红=正、绿=负（A股涨红跌绿），深浅按 |v|：0-0.05 淡 / 0.05-0.10 中 / 0.10-0.20 深 / ≥0.20 最深+白字 */
export function scoreCellClass(v: number): string {
  const a = Math.abs(v);
  const pos = v >= 0;
  const deep = a >= 0.20;
  const mid = a >= 0.10;
  const light = a >= 0.05;
  const base = pos
    ? (deep ? 'bg-rose-600' : mid ? 'bg-rose-400' : light ? 'bg-rose-300' : 'bg-rose-100')
    : (deep ? 'bg-emerald-600' : mid ? 'bg-emerald-500' : light ? 'bg-emerald-300' : 'bg-emerald-100');
  const txt = deep ? 'text-white' : pos ? 'text-rose-700' : 'text-emerald-700';
  return `${base} ${txt}`;
}

export function fmtScore(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(4)}`;
}

/** 聚合多模型分数历史为 月->日 映射（同日多模型取最新 created_at，即 items 顺序末位） */
export function bucketByMonth(items: { trade_date: string; fusion_score: number | null; signal_side: string | null }[]): MonthBucket[] {
  const byMonth = new Map<string, { year: number; month: number; scores: Map<string, number>; sides: Map<string, string> }>();
  for (const it of items) {
    if (it.fusion_score == null) continue;
    const d = String(it.trade_date ?? '').slice(0, 10);
    if (d.length !== 10) continue;
    const key = d.slice(0, 7);
    let b = byMonth.get(key);
    if (!b) {
      b = { year: Number(d.slice(0, 4)), month: Number(d.slice(5, 7)), scores: new Map(), sides: new Map() };
      byMonth.set(key, b);
    }
    b.scores.set(d, Number(it.fusion_score));  // 后写覆盖先写：取最新
    if (it.signal_side) b.sides.set(d, String(it.signal_side));
  }
  return [...byMonth.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, b]) => ({ key, ...b }));
}

const WD = ['日', '一', '二', '三', '四', '五', '六'];  // 周天为第一天

interface Props {
  symbol: string;          // suffix（600519.SH）
  onBarClick?: (date: string) => void;  // 点击日期联动 K 线（可选，暂未使用）
  height?: number;         // 可用高度，决定是否滚动
}

export function ScoreCalendar({ symbol, onBarClick }: Props) {
  const [items, setItems] = useState<{ trade_date: string; fusion_score: number | null; signal_side: string | null }[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewKey, setViewKey] = useState<string>('');  // 当前查看月份 YYYY-MM（空=最新月）

  useEffect(() => {
    if (!symbol) { setItems([]); return; }
    let cancelled = false;
    setLoading(true);
    const code = symbol.split('.')[0];
    modelTrainingService.getStockInferenceHistory(code, 500).then(resp => {
      if (!cancelled) setItems(resp?.items ?? []);
    }).catch(() => { if (!cancelled) setItems([]); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  const months = useMemo(() => bucketByMonth(items), [items]);

  // 默认跳到最新有分数的月份
  const [initialized, setInitialized] = useState(false);
  const curKey = months.length ? months[months.length - 1].key : '';
  useEffect(() => {
    if (!initialized && curKey) { setViewKey(curKey); setInitialized(true); }
  }, [curKey, initialized]);

  const monthIdx = months.findIndex(m => m.key === viewKey);
  const bucket = monthIdx >= 0 ? months[monthIdx] : null;

  // 计算月历格子
  const cells = useMemo(() => {
    if (!bucket) return [];
    const { year, month } = bucket;
    const first = new Date(year, month - 1, 1);
    const lead = first.getDay();   // 周天(0)为第一天
    const days = new Date(year, month, 0).getDate();
    const out: ({ kind: 'blank' } | { kind: 'day'; date: string; day: number; value: number | null; side: string | null; today: boolean })[] = [];
    for (let i = 0; i < lead; i++) out.push({ kind: 'blank' });
    for (let d = 1; d <= days; d++) {
      const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      out.push({
        kind: 'day', date, day: d,
        value: bucket.scores.get(date) ?? null,
        side: bucket.sides.get(date) ?? null,
        today: date === new Date().toISOString().slice(0, 10),
      });
    }
    return out;
  }, [bucket]);

  const monthScoreRange = useMemo(() => {
    const vals = cells.filter((c): c is any => c.kind === 'day' && c.value != null).map((c: any) => c.value);
    if (!vals.length) return null;
    return { min: Math.min(...vals), max: Math.max(...vals), count: vals.length };
  }, [cells]);

  const prev = () => { if (monthIdx > 0) setViewKey(months[monthIdx - 1].key); };
  const next = () => { if (monthIdx >= 0 && monthIdx < months.length - 1) setViewKey(months[monthIdx + 1].key); };

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* 月切换 */}
      <div className="flex items-center justify-between px-1">
        <button onClick={prev} disabled={monthIdx <= 0}
          className="w-5 h-5 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-50 disabled:opacity-30">
          <ChevronLeft className="w-3 h-3" />
        </button>
        <span className="text-xs font-black text-slate-700 font-mono">{bucket ? `${bucket.year}年${bucket.month}月` : '--'}</span>
        <button onClick={next} disabled={monthIdx < 0 || monthIdx >= months.length - 1}
          className="w-5 h-5 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-50 disabled:opacity-30">
          <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      {/* 星期头 */}
      <div className="grid grid-cols-7 text-center text-[9px] font-bold text-slate-400">
        {WD.map(w => <span key={w}>{w}</span>)}
      </div>

      {/* 月历格子 */}
      <Spin spinning={loading} size="small">
        <div className="grid grid-cols-7 gap-1">
          {cells.map((c, i) => c.kind === 'blank' ? <span key={`b${i}`} /> : (
            <button
              key={c.date}
              onClick={() => onBarClick?.(c.date)}
              title={`${c.date} ${c.value != null ? `分数 ${fmtScore(c.value)}${c.side ? ` · ${c.side}` : ''}` : '无推理'}`}
              className={`aspect-square rounded-md text-[9px] font-mono font-bold flex flex-col items-center justify-center leading-none border transition-transform hover:scale-105 ${
                c.value == null ? 'bg-slate-50 text-slate-300 border-slate-100' : `${scoreCellClass(c.value)} border-transparent`
              } ${c.today ? 'ring-2 ring-blue-400 ring-offset-1' : ''}`}
            >
              {c.day}
              {c.value != null && <span className="text-[7px] opacity-80">{c.side === 'BUY' ? 'B' : c.side === 'SELL' ? 'S' : ''}</span>}
            </button>
          ))}
          {cells.length === 0 && (
            <div className="col-span-7 flex flex-col items-center justify-center gap-1 py-8 text-[10px] text-slate-400">
              <CalendarDays className="w-5 h-5 opacity-40" />
              暂无推理分数历史
            </div>
          )}
        </div>
      </Spin>

      {/* 月份统计 + 图例 */}
      <div className="mt-auto pt-1.5 border-t border-slate-100 flex flex-col gap-1">
        {monthScoreRange && (
          <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 px-1">
            <span>推理日 <b className="text-slate-700">{monthScoreRange.count}</b> 天</span>
            <span>最低 <b className="text-emerald-600">{monthScoreRange.min.toFixed(3)}</b> · 最高 <b className="text-rose-600">{monthScoreRange.max.toFixed(3)}</b></span>
          </div>
        )}
        <div className="flex items-center justify-center gap-1 flex-wrap text-[8px] text-slate-400">
          <span>红=正分</span>
          <span className="w-3 h-3 rounded-sm bg-rose-100" />
          <span className="w-3 h-3 rounded-sm bg-rose-300" />
          <span className="w-3 h-3 rounded-sm bg-rose-400" />
          <span className="w-3 h-3 rounded-sm bg-rose-600" />
          <span className="ml-1">绿=负分</span>
          <span className="w-3 h-3 rounded-sm bg-emerald-100" />
          <span className="w-3 h-3 rounded-sm bg-emerald-300" />
          <span className="w-3 h-3 rounded-sm bg-emerald-500" />
          <span className="w-3 h-3 rounded-sm bg-emerald-600" />
          <span className="ml-1">B=买入 S=卖出</span>
        </div>
      </div>
    </div>
  );
}
