/** 分数日历：个股历史推理分数画在月历上（红正绿负、深浅按绝对值、同日多模型取最新）
 *
 * 交互：
 * - 点击有分数日期 -> 整表切换到该信号日（onBarClick）
 * - 点击无分数日期 -> 弹「是否现在推理」（用该日前一交易日的股市数据，onInfer 处理）
 * - 拖动跨多个日期 -> 弹批量推理确认（range 模式，onBatchInfer 处理）
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, CalendarDays, Zap } from 'lucide-react';
import { Modal, Spin, message } from 'antd';
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
  onBarClick?: (date: string) => void;  // 点击日期 -> 整表切换到该信号日分数
  selectedDate?: string | null;  // 当前列表基准信号日（琥珀色圈高亮）
  height?: number;         // 可用高度，决定是否滚动
  /** 当前筛选模型（列表下拉选的 model_id），推理补分数时用；缺省=全模型融合 */
  modelId?: string;
  /** 推理完成后回调（单日或批量），供外层刷新日历数据 */
  onInferred?: () => void;
  /** 变化时重新拉取推理历史（外层在推理完成后自增触发刷新） */
  refreshKey?: number;
}

export function ScoreCalendar({ symbol, onBarClick, selectedDate, modelId, onInferred, refreshKey = 0 }: Props) {
  const [items, setItems] = useState<{ trade_date: string; fusion_score: number | null; signal_side: string | null }[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewKey, setViewKey] = useState<string>('');  // 当前查看月份 YYYY-MM（空=最新月）
  const [inferring, setInferring] = useState(false);
  // 拖动选择：按下无分数日期开始，滑过多日成区间
  const dragStartRef = useRef<string | null>(null);
  const dragDatesRef = useRef<Set<string>>(new Set());
  // 拖过有分数格子松手时抑制一次 onClick（否则推理确认+切日期同时弹）
  const suppressClickRef = useRef(false);

  useEffect(() => {
    if (!symbol) { setItems([]); return; }
    let cancelled = false;
    setLoading(true);
    const code = symbol.split('.')[0];
    modelTrainingService.getStockInferenceHistory(code, 500).then(resp => {
      if (!cancelled) setItems(resp?.items ?? []);
    }).catch(() => { if (!cancelled) setItems([]); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, refreshKey]);

  /** 单日推理：用所选日（后端会回退到最近可用交易日）补分数 */
  const inferSingle = async (date: string) => {
    const model = modelId || '';
    Modal.confirm({
      title: '该日期无推理分数',
      content: `是否现在用「${model ? '当前筛选模型' : '全模型融合'}」推理 ${date}？\n（将使用该日前一交易日的股市数据）`,
      okText: '开始推理',
      cancelText: '取消',
      onOk: async () => {
        setInferring(true);
        try {
          if (model) {
            await modelTrainingService.runModelInference(model, date);
          } else {
            // 无模型筛选时用最近有分数的模型推理（融合口径没有单模型入口）
            const history = await modelTrainingService.getStockInferenceHistory(symbol.split('.')[0], 500);
            const models = history?.models ?? [];
            if (!models.length) throw new Error('暂无可用模型');
            await modelTrainingService.runModelInference(models[0].model_id, date);
          }
          message.success(`${date} 推理完成，刷新日历…`);
          onInferred?.();
        } catch {
          message.error(`${date} 推理失败，请稍后重试`);
        } finally {
          setInferring(false);
        }
      },
    });
  };

  /** 批量推理（range 模式）：拖动选中的日期区间 */
  const inferBatch = (dates: string[]) => {
    if (!dates.length) return;
    const sorted = [...dates].sort();
    const start = sorted[0], end = sorted[sorted.length - 1];
    Modal.confirm({
      title: `批量推理 ${sorted.length} 个交易日`,
      content: `区间 ${start} ~ ${end}，将按交易日逐个补推理分数。是否开始？`,
      okText: '开始批量推理',
      cancelText: '取消',
      onOk: async () => {
        setInferring(true);
        try {
          const model = modelId || '';
          let targetModel = model;
          if (!targetModel) {
            const history = await modelTrainingService.getStockInferenceHistory(symbol.split('.')[0], 500);
            const models = history?.models ?? [];
            if (!models.length) throw new Error('暂无可用模型');
            targetModel = models[0].model_id;
          }
          const batch = await modelTrainingService.submitBatchInference({
            model_id: targetModel,
            mode: 'range',
            start_date: start,
            end_date: end,
            reuse_existing: true,
          });
          // 轮询直到完成（分批推理跑后台，最多等 10 分钟）
          const deadline = Date.now() + 10 * 60 * 1000;
          while (Date.now() < deadline) {
            await new Promise(r => setTimeout(r, 3000));
            const st = await modelTrainingService.getBatchInference(batch.batch_id);
            if (st.status === 'completed' || st.status === 'partial' || st.status === 'failed') {
              if (st.status === 'failed') message.error('批量推理失败');
              else message.success(`批量推理完成（${st.progress_done}/${st.progress_total ?? st.progress_done}）`);
              onInferred?.();
              return;
            }
          }
          message.warning('批量推理仍在后台进行，稍后刷新日历可见');
          onInferred?.();
        } catch {
          message.error('批量推理提交失败');
        } finally {
          setInferring(false);
        }
      },
    });
  };

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
    const out: ({ kind: 'blank' } | { kind: 'day'; date: string; day: number; value: number | null; side: string | null; today: boolean; active: boolean })[] = [];
    for (let i = 0; i < lead; i++) out.push({ kind: 'blank' });
    for (let d = 1; d <= days; d++) {
      const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      out.push({
        kind: 'day', date, day: d,
        value: bucket.scores.get(date) ?? null,
        side: bucket.sides.get(date) ?? null,
        today: date === new Date().toISOString().slice(0, 10),
        active: date === selectedDate,   // 当前列表基准信号日
      });
    }
    return out;
  }, [bucket, selectedDate]);

  const monthScoreRange = useMemo(() => {
    const vals = cells.filter((c): c is any => c.kind === 'day' && c.value != null).map((c: any) => c.value);
    if (!vals.length) return null;
    return { min: Math.min(...vals), max: Math.max(...vals), count: vals.length };
  }, [cells]);

  const prev = () => { if (monthIdx > 0) setViewKey(months[monthIdx - 1].key); };
  const next = () => { if (monthIdx >= 0 && monthIdx < months.length - 1) setViewKey(months[monthIdx + 1].key); };

  // ── 拖动多选（仅无分数日期）：按下开始，滑过多日成区间，松手批量推理 ──
  const [dragSet, setDragSet] = useState<Set<string>>(new Set());

  const startDrag = (date: string) => {
    dragStartRef.current = date;
    dragDatesRef.current = new Set([date]);
    setDragSet(new Set([date]));
  };
  const extendDrag = (date: string) => {
    if (!dragStartRef.current) return;
    dragDatesRef.current.add(date);
    setDragSet(new Set(dragDatesRef.current));
  };
  const endDrag = (commit: boolean) => {
    const dates = dragDatesRef.current;
    const wasDragging = dragStartRef.current != null;
    dragStartRef.current = null;
    dragDatesRef.current = new Set();
    setDragSet(new Set());
    if (!commit || !dates.size) return;
    suppressClickRef.current = wasDragging;   // 拖过的松手不触发 onClick 切日期
    if (dates.size > 1) inferBatch([...dates]);
    else inferSingle([...dates][0]);   // 单击无分数日期 -> 单日推理
  };

  // 拖出格子/日历区松开也要收尾；endDragRef 每帧更新，避免窗口监听持首帧闭包
  const endDragRef = useRef<(commit: boolean) => void>(() => {});
  endDragRef.current = endDrag;
  useEffect(() => {
    const up = () => endDragRef.current(true);
    window.addEventListener('mouseup', up);
    return () => window.removeEventListener('mouseup', up);
  }, []);

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
      <Spin spinning={loading || inferring} size="small" tip={inferring ? '推理中…' : undefined}>
        <div className="grid grid-cols-7 gap-1">
          {cells.map((c, i) => c.kind === 'blank' ? <span key={`b${i}`} /> : (
            <button
              key={c.date}
              onMouseDown={() => { if (c.value == null) startDrag(c.date); }}
              onMouseEnter={() => { if (c.value == null && dragStartRef.current) extendDrag(c.date); }}
              onMouseUp={() => endDrag(true)}
              onClick={() => {
                if (c.value == null || dragStartRef.current) return;
                if (suppressClickRef.current) { suppressClickRef.current = false; return; }
                onBarClick?.(c.date);
              }}
              disabled={c.value == null && inferring}
              title={c.value != null
                ? `${c.date} 分数 ${fmtScore(c.value)}${c.side ? ` · ${c.side}` : ''}（点击整表切换当天）`
                : `${c.date} 无推理 · 点击推理该日；按住拖动可批量选多日`}
              className={`aspect-square rounded-md text-[9px] font-mono font-bold flex flex-col items-center justify-center leading-none border transition-transform ${
                c.value != null ? 'hover:scale-105 cursor-pointer' : 'cursor-pointer hover:border-blue-300 hover:bg-blue-50'
              } ${
                c.value == null
                  ? (dragSet.has(c.date) ? 'bg-blue-100 text-blue-500 border-blue-400' : 'bg-slate-50 text-slate-300 border-slate-100')
                  : `${scoreCellClass(c.value)} border-transparent`
              } ${c.today ? 'ring-2 ring-blue-400 ring-offset-1' : ''} ${c.active ? 'ring-2 ring-amber-500 ring-offset-1' : ''}`}
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

      {/* 拖动提示：拖动中显示已选天数 */}
      {dragSet.size > 1 && (
        <div className="flex items-center gap-1 text-[9px] font-bold text-blue-600 bg-blue-50 border border-blue-200 rounded px-2 py-1">
          <Zap className="w-3 h-3" /> 已选 {dragSet.size} 天，松手批量推理
        </div>
      )}

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
