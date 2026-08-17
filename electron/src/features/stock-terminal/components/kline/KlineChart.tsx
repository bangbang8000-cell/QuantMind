/** 个股终端 K 线图：主图（蜡烛+MA/BOLL+指数叠加）+ 副图（VOL/MACD/KDJ/RSI 可增删） */

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { KlineBar } from '../../types';
import { boll, kdj, macd, rsi, sma, volMa, Series } from '../../engine/indicators';

export type SubplotType = 'vol' | 'macd' | 'kdj' | 'rsi';

export interface IndicatorConfig {
  ma: boolean;
  boll: boolean;
  subplots: SubplotType[];
}

export interface IndexOverlay {
  code: string;
  name: string;
  closes: { date: string; close: number }[];
  color: string;
}

export interface SignalPoint {
  date: string;
  fusion: number | null;
  side: string;
}

/** 推理分数历史叠加（多模型）：每模型一条分数线 */
export interface ScoreSeries {
  model: string;
  color: string;
  points: { date: string; fusion: number | null; side: string | null }[];
}

const COLORS = {
  up: '#e11d48',        // A股：涨红
  down: '#059669',      // 跌绿
  ma5: '#f59e0b',
  ma10: '#3b82f6',
  ma20: '#8b5cf6',
  ma60: '#64748b',
  boll: '#94a3b8',
  volUp: '#fda4af',
  volDown: '#6ee7b7',
  dif: '#3b82f6',
  dea: '#f59e0b',
  histUp: '#e11d48',
  histDown: '#059669',
  k: '#3b82f6',
  d: '#f59e0b',
  j: '#8b5cf6',
  rsi: '#6366f1',
};

const SUB_HEIGHT = 110; // 每个副图高度 px
const MAIN_MIN = 300;

interface Props {
  bars: KlineBar[];
  config: IndicatorConfig;
  overlays: IndexOverlay[];
  height?: number;
  signals?: SignalPoint[];
  btEquity?: { date: string; equity: number }[];
  scoreSeries?: ScoreSeries[];
}

export function KlineChart({ bars, config, overlays, height = 460, signals = [], btEquity = [], scoreSeries = [] }: Props) {
  const option = useMemo(() => {
    const dates = bars.map(b => b.date);
    const closes = bars.map(b => b.close);
    const volumes = bars.map(b => b.volume ?? 0);

    const ma5 = config.ma ? sma(closes, 5) : null;
    const ma10 = config.ma ? sma(closes, 10) : null;
    const ma20 = config.ma ? sma(closes, 20) : null;
    const ma60 = config.ma ? sma(closes, 60) : null;
    const bb = config.boll ? boll(closes) : null;
    const macdRes = config.subplots.includes('macd') ? macd(closes) : null;
    const kdjRes = config.subplots.includes('kdj') ? kdj(bars) : null;
    const rsiRes = config.subplots.includes('rsi') ? rsi(closes) : null;
    const volMa5 = config.subplots.includes('vol') ? volMa(bars, 5) : null;
    const volMa10 = config.subplots.includes('vol') ? volMa(bars, 10) : null;

    // 指数叠加：以各自首日为基准归一化为百分比，按日期对齐到 K 线轴
    const overlaySeries = overlays.map(ov => {
      const byDate = new Map(ov.closes.map(c => [c.date, c.close]));
      const base = ov.closes.length ? ov.closes[0].close : 1;
      const aligned = bars.map(b => {
        const c = byDate.get(b.date);
        return c != null && base > 0 ? Number((((c - base) / base) * 100).toFixed(2)) : null;
      });
      return { name: ov.name, data: aligned, color: ov.color };
    });

    // 主图也叠加个股自身归一化曲线？不需要--蜡烛本身就是价格。指数归一化直接画在独立 y 轴。
    const subCount = config.subplots.length;
    const mainHeight = Math.max(MAIN_MIN, height - subCount * SUB_HEIGHT - 8);
    const gridSpace = subCount * (SUB_HEIGHT + 36);

    const grids: any[] = [
      { left: 64, right: 16, top: 24, height: mainHeight },
    ];
    const xAxes: any[] = [];
    const yAxes: any[] = [];
    const series: any[] = [];

    // 主图网格 + 轴
    xAxes.push({ type: 'category', gridIndex: 0, data: dates, show: false, boundaryGap: true });
    yAxes.push({ type: 'value', gridIndex: 0, scale: true, splitLine: { lineStyle: { color: '#f1f5f9' } }, axisLabel: { fontSize: 10, color: '#64748b' } });
    if (overlaySeries.length) {
      yAxes.push({ type: 'value', gridIndex: 0, scale: true, axisLabel: { show: false }, splitLine: { show: false }, min: -30, max: (v: any) => Math.max(30, Math.ceil(Math.abs(v.max) / 10) * 10) });
    }

    // 蜡烛
    series.push({
      name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
      data: bars.map(b => [b.open, b.close, b.low, b.high]),
      itemStyle: { color: COLORS.up, color0: COLORS.down, borderColor: COLORS.up, borderColor0: COLORS.down },
    });

    const line = (name: string, data: Series, color: string, yAxisIdx = 0) =>
      series.push({
        name, type: 'line', xAxisIndex: 0, yAxisIndex: yAxisIdx, data,
        symbol: 'none', lineStyle: { width: 1, color }, itemStyle: { color }, emphasis: { disabled: true }, z: 3,
      });

    if (ma5) line('MA5', ma5, COLORS.ma5);
    if (ma10) line('MA10', ma10, COLORS.ma10);
    if (ma20) line('MA20', ma20, COLORS.ma20);
    if (ma60) line('MA60', ma60, COLORS.ma60);
    if (bb) {
      line('BOLL中轨', bb.mid, COLORS.boll);
      line('BOLL上轨', bb.upper, COLORS.boll);
      line('BOLL下轨', bb.lower, COLORS.boll);
    }
    overlaySeries.forEach((ov, i) => line(ov.name, ov.data, ov.color, 1));

    // 策略净值叠加（归一化到首日收盘价等比例，画在主图）
    if (btEquity.length) {
      const eqByDate = new Map(btEquity.map(p => [p.date, p.equity]));
      const firstEq = btEquity.length ? btEquity[0].equity : 1;
      const baseClose = bars.length ? bars[0].close : 1;
      const eqData = bars.map(b => {
        const eq = eqByDate.get(b.date);
        if (eq == null || firstEq <= 0) return null;
        return Number((baseClose * (eq / firstEq)).toFixed(2));
      });
      series.push({
        name: '策略净值', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: eqData,
        symbol: 'none', lineStyle: { width: 1.6, color: '#f97316', type: 'dashed' }, itemStyle: { color: '#f97316' },
        z: 4, emphasis: { disabled: true },
      });
    }

    // 推理分数历史叠加（多模型分数线，独立右轴）
    if (scoreSeries.length) {
      const idxByDate = new Map(dates.map((d, i) => [d, i]));
      const scoreIdx = yAxes.length; // 当前主图 y 轴数
      yAxes.push({
        type: 'value', gridIndex: 0, position: 'right', scale: true,
        axisLabel: { fontSize: 9, color: '#94a3b8', formatter: (v: number) => v.toFixed(1) },
        splitLine: { show: false },
      });
      scoreSeries.forEach(sr => {
        const data = bars.map((b, i) => {
          const p = sr.points.find(p => p.date === b.date);
          return p && p.fusion != null ? Number(p.fusion) : null;
        });
        series.push({
          name: `分数·${sr.model}`, type: 'line', xAxisIndex: 0, yAxisIndex: scoreIdx,
          data, symbol: 'circle', symbolSize: 7, connectNulls: false,
          lineStyle: { width: 1.6, color: sr.color },
          itemStyle: { color: sr.color, borderColor: '#fff', borderWidth: 1 },
          label: { show: true, position: 'top', fontSize: 8, fontWeight: 'bold', formatter: (p: any) => p?.value == null ? '' : Number(p.value).toFixed(3), color: sr.color },
          emphasis: { scale: 1.4 },
        });
      });
    }

    // 推理分数信号标记（BUY▲ / SELL▼）
    if (signals.length) {
      const buyData: any[] = [];
      const sellData: any[] = [];
      const idxByDate = new Map(dates.map((d, i) => [d, i]));
      for (const sig of signals) {
        const i = idxByDate.get(sig.date);
        if (i == null) continue;
        const bar = bars[i];
        const v = sig.side === 'BUY' ? bar.low * 0.99 : bar.high * 1.01;
        const pt = { value: [i, Number(v.toFixed(2))], sig };
        if (sig.side === 'BUY') buyData.push(pt);
        else if (sig.side === 'SELL') sellData.push(pt);
      }
      const mk = (data: any[], symbol: string, color: string, offset: number) => ({
        name: '信号', type: 'scatter', xAxisIndex: 0, yAxisIndex: 0,
        data, symbol, symbolSize: 12, symbolOffset: [0, offset],
        itemStyle: { color, borderColor: '#fff', borderWidth: 1 },
        label: { show: true, formatter: (p: any) => p.data.sig.side, fontSize: 8, color, fontWeight: 'bold', position: 'top' },
        z: 10, tooltip: { formatter: (p: any) => {
          const s = p.data.sig;
          return `${s.date}<br/>模型: ${s.side}<br/>fusion: ${s.fusion == null ? '--' : Number(s.fusion).toFixed(4)}`;
        } },
      });
      if (buyData.length) series.push(mk(buyData, 'triangle', COLORS.up, -8));
      if (sellData.length) series.push(mk(sellData, 'triangle', COLORS.down, 8));
    }

    // 副图
    config.subplots.forEach((sp, idx) => {
      const gi = idx + 1;
      grids.push({ left: 64, right: 16, top: 24 + mainHeight + 40 + idx * (SUB_HEIGHT + 36), height: SUB_HEIGHT });
      const showLabel = idx === config.subplots.length - 1;
      xAxes.push({ type: 'category', gridIndex: gi, data: dates, show: showLabel, axisLabel: { fontSize: 10, color: '#94a3b8' }, boundaryGap: true });
      yAxes.push({ type: 'value', gridIndex: gi, scale: true, splitLine: { lineStyle: { color: '#f8fafc' } }, axisLabel: { fontSize: 10, color: '#64748b' } });

      if (sp === 'vol') {
        series.push({
          name: '成交量', type: 'bar', xAxisIndex: gi, yAxisIndex: gi,
          data: volumes.map((v, i) => ({
            value: v,
            itemStyle: { color: bars[i].close >= bars[i].open ? COLORS.volUp : COLORS.volDown },
          })),
        });
        series.push({ name: 'VMA5', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: volMa5, symbol: 'none', lineStyle: { width: 1, color: COLORS.ma5 }, z: 3 });
        series.push({ name: 'VMA10', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: volMa10, symbol: 'none', lineStyle: { width: 1, color: COLORS.ma10 }, z: 3 });
      } else if (sp === 'macd' && macdRes) {
        series.push({
          name: 'MACD柱', type: 'bar', xAxisIndex: gi, yAxisIndex: gi,
          data: macdRes.hist.map(v => ({
            value: v,
            itemStyle: { color: (v ?? 0) >= 0 ? COLORS.histUp : COLORS.histDown },
          })),
        });
        series.push({ name: 'DIF', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: macdRes.dif, symbol: 'none', lineStyle: { width: 1, color: COLORS.dif }, z: 3 });
        series.push({ name: 'DEA', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: macdRes.dea, symbol: 'none', lineStyle: { width: 1, color: COLORS.dea }, z: 3 });
      } else if (sp === 'kdj' && kdjRes) {
        series.push({ name: 'K', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: kdjRes.k, symbol: 'none', lineStyle: { width: 1, color: COLORS.k }, z: 3 });
        series.push({ name: 'D', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: kdjRes.d, symbol: 'none', lineStyle: { width: 1, color: COLORS.d }, z: 3 });
        series.push({ name: 'J', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: kdjRes.j, symbol: 'none', lineStyle: { width: 1, color: COLORS.j }, z: 3 });
      } else if (sp === 'rsi' && rsiRes) {
        series.push({ name: 'RSI14', type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: rsiRes, symbol: 'none', lineStyle: { width: 1.2, color: COLORS.rsi }, z: 3 });
      }
    });

    return {
      animation: false,
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { fontSize: 10 } },
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: '#e2e8f0',
        textStyle: { color: '#334155', fontSize: 11 },
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: 'inside', xAxisIndex: xAxes.map((_, i) => i), start: 60, end: 100 },
        { type: 'slider', xAxisIndex: xAxes.map((_, i) => i), bottom: 2, height: 16, borderColor: '#e2e8f0', fillerColor: 'rgba(59,130,246,0.08)' },
      ],
      series,
    };
  }, [bars, config, overlays, height, signals, btEquity, scoreSeries]);

  return (
    <ReactECharts
      option={option}
      notMerge
      lazyUpdate
      style={{ width: '100%', height }}
      opts={{ renderer: 'canvas' }}
    />
  );
}

export const OVERLAY_COLORS = ['#0ea5e9', '#f97316', '#a855f7', '#14b8a6'];
