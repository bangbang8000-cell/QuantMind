/**
 * 推理回测模块 — 基于推理信号 + 选股策略的事件驱动回测
 *
 * 功能：
 * - 策略参数表单（默认值可改 + 保守/平衡/激进预设）
 * - 日期范围 + 信号模式（stored 快 / realtime 全量）
 * - 净值曲线 vs 基准、核心指标卡
 * - 年度/月度收益表、逐日选股明细、交易流水、行业轮动
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Select, DatePicker, Button, Spin, message, Progress,
  Table, Typography, Empty, InputNumber,
  Switch, Tooltip, Alert, Tag, Tabs,
} from 'antd';
import {
  BarChart3, TrendingUp, Activity, Target, Zap, PieChart,
} from 'lucide-react';
import dayjs from 'dayjs';
import { clsx } from 'clsx';
import ReactECharts from 'echarts-for-react';
import { modelTrainingService } from '../../services/modelTrainingService';

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface StrategyParams {
  entry_threshold: number;
  exit_threshold: number;
  strong_industry_min: number;
  score_min: number;
  score_max: number;
  max_hold_days: number;
  take_profit: number;
  stop_loss: number;
  max_positions: number;
  daily_select_max: number;
  initial_capital: number;
  main_board_only: boolean;
  exclude_limit_moves: boolean;
  exclude_st: boolean;
  use_index_ma20_filter: boolean;
}

const BALANCED: StrategyParams = {
  entry_threshold: 0.09, exit_threshold: 0.06, strong_industry_min: 2,
  score_min: 0.10, score_max: 0.12,
  max_hold_days: 5, take_profit: 0.08, stop_loss: 0.05,
  max_positions: 5, daily_select_max: 5, initial_capital: 100000,
  main_board_only: true, exclude_limit_moves: true, exclude_st: true, use_index_ma20_filter: true,
};

const PRESETS: Record<string, { label: string; params: Partial<StrategyParams> }> = {
  conservative: {
    label: '保守型',
    params: { entry_threshold: 0.10, exit_threshold: 0.10, strong_industry_min: 5 },
  },
  balanced: { label: '平衡型（推荐）', params: {} },
  aggressive: {
    label: '激进型',
    params: { entry_threshold: 0.07, exit_threshold: 0.06, strong_industry_min: 1 },
  },
};

interface BacktestResultData {
  status: string;
  metrics: {
    initial_capital: number;
    final_nav: number;
    total_return: number;
    annualized_return: number;
    max_drawdown: number;
    win_rate: number;
    trade_count: number;
    buy_count: number;
    sell_count: number;
    avg_profit: number;
    avg_loss: number;
    ret_dd_ratio: number;
    position_days: number;
    empty_days: number;
  };
  daily_selections: Array<{
    trade_date: string;
    market_state: string;
    industry_avg_top1: number;
    strong_industry_count: number;
    index_above_ma20: boolean;
    selections: Array<{ symbol: string; score: number; industry: string }>;
  }>;
  trades: Array<{
    date: string;
    symbol: string;
    name: string;
    side: 'BUY' | 'SELL';
    price: number;
    shares: number;
    amount: number;
    industry: string;
    score: number;
    reason: string;
    profit_pct: number;
    hold_days: number;
  }>;
  nav_curve: Array<{ date: string; nav: number; cash: number; holdings: number; position_count: number }>;
  monthly_returns: Record<string, number>;
  industry_rotation: Array<{ month: string; top_industries: Array<{ industry: string; days: number }> }>;
  errors: Array<{ date: string; error: string }>;
  warnings: string[];
}

const fmtPct = (n: number | null | undefined): string => {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return `${((n as number) * 100).toFixed(2)}%`;
};

const fmtNum = (n: number | null | undefined): string => {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return (n as number).toLocaleString();
};

interface Props {
  modelId: string;
}

export const InferenceBacktestModule: React.FC<Props> = ({ modelId }) => {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(6, 'month'),
    dayjs().subtract(1, 'day'),
  ]);
  const [signalMode, setSignalMode] = useState<'stored' | 'realtime'>('stored');
  const [preset, setPreset] = useState<'conservative' | 'balanced' | 'aggressive'>('balanced');
  const [params, setParams] = useState<StrategyParams>(() => ({ ...BALANCED }));
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResultData | null>(null);
  const [elapsedSec, setElapsedSec] = useState<number>(0);
  const [fakeProgress, setFakeProgress] = useState<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 回测进度模拟：加载期间每 500ms 递增，到 95% 封顶（真实完成时跳 100%）
  useEffect(() => {
    if (loading) {
      setFakeProgress(0);
      setElapsedSec(0);
      elapsedTimerRef.current = setInterval(() => {
        const p = fakeProgress;
        setElapsedSec(elapsedSec + 1);
        setFakeProgress(Math.min(95, p + (p < 50 ? 3 : 1.2)));
      }, 500);
      return () => {
        if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
      };
    }
    return undefined;
  }, [loading, fakeProgress, elapsedSec]);

  useEffect(() => () => {
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
  }, []);

  const applyPreset = (name: 'conservative' | 'balanced' | 'aggressive') => {
    setPreset(name);
    const overrides = PRESETS[name].params;
    const merged = { ...params, ...overrides } as StrategyParams;
    setParams(merged);
  };

  const updateParam = (key: keyof StrategyParams, value: number | boolean) => {
    const merged = { ...params, [key]: value } as StrategyParams;
    setParams(merged);
  };

  const runBacktest = async () => {
    if (!modelId) {
      message.warning('请选择模型');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const resp = await modelTrainingService.runInferenceBacktest({
        model_id: modelId,
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        signal_mode: signalMode,
        strategy: params as unknown as Record<string, unknown>,
      });
      if (resp.status === 'success') {
        setFakeProgress(100);
        setResult(resp as BacktestResultData);
        const m = resp.metrics;
        message.success(`回测完成：${fmtPct(m?.total_return)} · ${m?.trade_count ?? 0} 笔交易`);
      } else {
        message.error(resp.errors?.[0]?.error || '回测失败');
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      message.error('回测请求失败: ' + msg);
    } finally {
      setLoading(false);
    }
  };

  // ── 净值曲线 ──
  const navOption = result ? {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(0,0,0,0.1)',
      textStyle: { color: '#374151' },
    },
    legend: { data: ['策略净值', '持仓数'], textStyle: { color: '#6b7280', fontSize: 11 } },
    grid: { left: '4%', right: '4%', bottom: '6%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: result.nav_curve.map(d => d.date),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value' as const,
        name: '净值',
        axisLabel: { color: '#6b7280', formatter: (v: number) => (v / 10000).toFixed(0) + '万' },
        splitLine: { lineStyle: { color: '#e5e7eb' } },
      },
      {
        type: 'value' as const,
        name: '持仓',
        minInterval: 1,
        axisLabel: { color: '#9ca3af' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '策略净值',
        type: 'line',
        data: result.nav_curve.map(d => d.nav),
        smooth: true,
        lineStyle: { width: 2, color: '#059669' },
        itemStyle: { color: '#059669' },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(5,150,105,0.2)' },
              { offset: 1, color: 'rgba(5,150,105,0.02)' },
            ],
          },
        },
      },
      {
        name: '持仓数',
        type: 'bar',
        yAxisIndex: 1,
        data: result.nav_curve.map(d => d.position_count),
        barWidth: 8,
        itemStyle: { color: 'rgba(99,102,241,0.35)', borderRadius: [3, 3, 0, 0] },
      },
    ],
  } : null;

  // ── 行业轮动图 ──
  const rotationOption = result && result.industry_rotation.length ? {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' as const, backgroundColor: 'rgba(255,255,255,0.95)', textStyle: { color: '#374151' } },
    legend: { type: 'scroll' as const, bottom: 0, textStyle: { color: '#6b7280', fontSize: 10 } },
    grid: { left: '6%', right: '4%', bottom: '18%', top: '6%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: result.industry_rotation.map(r => r.month),
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
    yAxis: { type: 'value' as const, axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
    series: result.industry_rotation.flatMap((r, idx) =>
      r.top_industries.map((ind, j) => ({
        name: ind.industry,
        type: 'bar' as const,
        stack: 'total',
        data: result.industry_rotation.map((_, i) => i === idx ? ind.days : 0),
        itemStyle: { color: `hsl(${(idx * 47 + j * 37) % 360}, 60%, 55%)` },
        barMaxWidth: 22,
      })),
    ),
  } : null;

  const metricCards = result ? [
    { label: '总收益率', value: fmtPct(result.metrics.total_return), color: (result.metrics.total_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600', hint: `最终净值 ${fmtNum(result.metrics.final_nav)}` },
    { label: '年化收益', value: fmtPct(result.metrics.annualized_return), color: (result.metrics.annualized_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600', hint: '' },
    { label: '最大回撤', value: fmtPct(-(result.metrics.max_drawdown ?? 0)), color: 'text-rose-600', hint: '' },
    { label: '胜率', value: fmtPct(result.metrics.win_rate), color: 'text-blue-600', hint: `${result.metrics.trade_count} 笔交易` },
    { label: '平均盈利', value: fmtPct(result.metrics.avg_profit), color: 'text-emerald-600', hint: '' },
    { label: '平均亏损', value: fmtPct(result.metrics.avg_loss), color: 'text-rose-600', hint: '' },
    { label: '收益/回撤比', value: (result.metrics.ret_dd_ratio ?? 0).toFixed(2), color: (result.metrics.ret_dd_ratio ?? 0) > 0 ? 'text-emerald-600' : 'text-slate-600', hint: '' },
    { label: '空仓天数', value: String(result.metrics.empty_days ?? 0), color: 'text-slate-600', hint: `共 ${result.metrics.position_days} 交易日` },
  ] : [];

  const tradeColumns = [
    { title: '日期', dataIndex: 'date', width: 95, render: (v: string) => <Text className="text-[10px] font-mono font-bold text-slate-700">{v}</Text> },
    {
      title: '操作', dataIndex: 'side', width: 55,
      render: (v: string) => (
        <Tag color={v === 'BUY' ? 'blue' : 'orange'} className="m-0 border-0 text-[9px] font-black px-2 rounded">
          {v === 'BUY' ? '买入' : '卖出'}
        </Tag>
      ),
    },
    { title: '代码', dataIndex: 'symbol', width: 85, render: (v: string) => <Text className="text-[10px] font-mono text-slate-600">{v}</Text> },
    { title: '行业', dataIndex: 'industry', width: 90, render: (v: string) => <Text className="text-[10px] text-slate-500 truncate block">{v || '—'}</Text> },
    {
      title: '价格', dataIndex: 'price', width: 70, align: 'right' as const,
      render: (v: number) => <Text className="text-[10px] font-mono text-slate-600">{v?.toFixed(2)}</Text>,
    },
    {
      title: '股数', dataIndex: 'shares', width: 70, align: 'right' as const,
      render: (v: number) => <Text className="text-[10px] font-mono text-slate-600">{fmtNum(v)}</Text>,
    },
    {
      title: '盈亏', dataIndex: 'profit_pct', width: 75, align: 'right' as const,
      render: (v: number, r: BacktestResultData['trades'][number]) => r.side === 'SELL' ? (
        <Text className={clsx('text-[10px] font-mono font-bold', v >= 0 ? 'text-emerald-600' : 'text-rose-600')}>{fmtPct(v)}</Text>
      ) : <Text className="text-[10px] text-slate-300">—</Text>,
    },
    { title: '持有', dataIndex: 'hold_days', width: 50, align: 'right' as const, render: (v: number) => <Text className="text-[10px] text-slate-500">{v || '—'}</Text> },
    { title: '理由', dataIndex: 'reason', render: (v: string) => <Text className="text-[10px] text-slate-500">{v || '—'}</Text> },
  ];

  const selectionColumns = [
    { title: '日期', dataIndex: 'trade_date', width: 95, render: (v: string) => <Text className="text-[10px] font-mono font-bold text-slate-700">{v}</Text> },
    {
      title: '市场状态', dataIndex: 'market_state', width: 85,
      render: (v: string) => {
        const color = v === '牛市' ? 'green' : v === '震荡偏强' ? 'blue' : v === '震荡' ? 'gold' : v === '震荡偏弱' ? 'orange' : 'red';
        return <Tag color={color} className="m-0 border-0 text-[9px] font-black px-2 rounded">{v}</Tag>;
      },
    },
    {
      title: '行业avgTop1', dataIndex: 'industry_avg_top1', width: 95, align: 'right' as const,
      render: (v: number) => <Text className="text-[10px] font-mono text-slate-600">{v?.toFixed(4)}</Text>,
    },
    { title: '强行业', dataIndex: 'strong_industry_count', width: 55, align: 'right' as const, render: (v: number) => <Text className="text-[10px] font-mono text-slate-600">{v}</Text> },
    {
      title: '大盘MA20', dataIndex: 'index_above_ma20', width: 70,
      render: (v: boolean) => <Text className={clsx('text-[10px] font-bold', v ? 'text-emerald-600' : 'text-rose-600')}>{v ? 'OK' : '跌破'}</Text>,
    },
    {
      title: '选股', dataIndex: 'selections',
      render: (v: Array<{ symbol: string; score: number; industry: string }>) => (
        <div className="flex flex-wrap gap-1">
          {v.length === 0 ? <Text className="text-[9px] text-slate-300">空仓</Text> : v.map(p => (
            <Tooltip key={p.symbol} title={`${p.industry} · score=${p.score?.toFixed(4)}`}>
              <Tag className="m-0 border-0 bg-blue-50 text-blue-600 text-[8px] font-bold px-1.5 rounded">{p.symbol}</Tag>
            </Tooltip>
          ))}
        </div>
      ),
    },
  ];

  const monthlyRows = Object.entries(result?.monthly_returns || {}).map(([month, ret]) => ({ month, ret }));

  return (
    <div className="space-y-4">
      {/* 参数区 */}
      <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-emerald-500/10 p-2 rounded-xl text-emerald-600">
            <Target size={18} />
          </div>
          <Text className="text-sm font-black text-slate-800 uppercase tracking-tight leading-none">推理回测 · 选股策略</Text>
        </div>

        {/* 第一行：日期 + 信号模式 + 策略预设 */}
        <div className="grid grid-cols-12 gap-4 items-end mb-4">
          <div className="col-span-4">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">回测区间</Text>
            <RangePicker
              value={dateRange}
              onChange={(dates) => { if (dates && dates[0] && dates[1]) setDateRange([dates[0], dates[1]]); }}
              disabledDate={d => d.isAfter(dayjs())}
              className="w-full rounded-xl h-9 border-slate-100"
            />
          </div>
          <div className="col-span-3">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">信号来源</Text>
            <Select value={signalMode} onChange={setSignalMode} className="w-full h-9">
              <Select.Option value="stored">已有推理信号（快）</Select.Option>
              <Select.Option value="realtime">逐日实时推理（慢·全量）</Select.Option>
            </Select>
          </div>
          <div className="col-span-3">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">策略预设</Text>
            <Select value={preset} onChange={v => applyPreset(v)} className="w-full h-9">
              {Object.entries(PRESETS).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v.label}</Select.Option>
              ))}
            </Select>
          </div>
          <div className="col-span-2">
            <Button
              type="primary" size="large"
              onClick={runBacktest} loading={loading} disabled={!modelId}
              className="w-full rounded-xl h-9 bg-emerald-600 border-0 font-bold shadow-md shadow-emerald-100 text-xs"
            >
              运行回测
            </Button>
          </div>
        </div>

        {signalMode === 'realtime' && (
          <Alert type="warning" showIcon className="mb-3 rounded-xl"
            message={<span className="text-[11px]">逐日实时推理需要对回测区间每个交易日跑模型推理，可能耗时较长（数百天需数十分钟）。建议先用"已有推理信号"快速验证。</span>} />
        )}

        {/* 策略参数网格 */}
        <div className="grid grid-cols-12 gap-x-4 gap-y-3">
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">入场线 avgTop1</Text>
            <InputNumber value={params.entry_threshold} onChange={v => updateParam('entry_threshold', Number(v ?? 0.09))} step={0.01} min={0.05} max={0.15} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">空仓线 avgTop1</Text>
            <InputNumber value={params.exit_threshold} onChange={v => updateParam('exit_threshold', Number(v ?? 0.06))} step={0.01} min={0.03} max={0.12} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">强行业数下限</Text>
            <InputNumber value={params.strong_industry_min} onChange={v => updateParam('strong_industry_min', Number(v ?? 2))} min={0} max={10} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">个股分数下限</Text>
            <InputNumber value={params.score_min} onChange={v => updateParam('score_min', Number(v ?? 0.10))} step={0.01} min={0} max={0.3} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">个股分数上限</Text>
            <InputNumber value={params.score_max} onChange={v => updateParam('score_max', Number(v ?? 0.12))} step={0.01} min={0} max={0.4} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">最长持有(天)</Text>
            <InputNumber value={params.max_hold_days} onChange={v => updateParam('max_hold_days', Number(v ?? 5))} min={1} max={20} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">止盈</Text>
            <InputNumber value={params.take_profit} onChange={v => updateParam('take_profit', Number(v ?? 0.08))} step={0.01} min={0} max={0.3} className="w-full h-8" formatter={v => `${(Number(v ?? 0) * 100).toFixed(0)}%`} parser={v => Number(String(v).replace('%', '')) / 100} />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">止损</Text>
            <InputNumber value={params.stop_loss} onChange={v => updateParam('stop_loss', Number(v ?? 0.05))} step={0.01} min={0} max={0.2} className="w-full h-8" formatter={v => `${(Number(v ?? 0) * 100).toFixed(0)}%`} parser={v => Number(String(v).replace('%', '')) / 100} />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">最大持仓</Text>
            <InputNumber value={params.max_positions} onChange={v => updateParam('max_positions', Number(v ?? 5))} min={1} max={20} className="w-full h-8" />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] text-slate-500 mb-1 block">初始资金</Text>
            <InputNumber value={params.initial_capital} onChange={v => updateParam('initial_capital', Number(v ?? 100000))} step={10000} min={10000} className="w-full h-8" formatter={v => fmtNum(Number(v))} />
          </div>
          <div className="col-span-2 flex items-end gap-3 pb-1">
            <div className="flex items-center gap-1">
              <Switch size="small" checked={params.main_board_only} onChange={v => updateParam('main_board_only', v)} />
              <Text className="text-[10px] text-slate-500">仅主板</Text>
            </div>
            <div className="flex items-center gap-1">
              <Switch size="small" checked={params.use_index_ma20_filter} onChange={v => updateParam('use_index_ma20_filter', v)} />
              <Text className="text-[10px] text-slate-500">MA20</Text>
            </div>
          </div>
        </div>
      </div>

      {/* 结果 */}
      {loading && (
        <div className="glass-panel rounded-3xl p-8 border border-slate-100/50">
          <div className="flex flex-col items-center justify-center py-8">
            <Spin size="large" />
            <Text className="text-sm text-slate-500 mt-4 font-bold">正在执行推理回测...</Text>
            <Text className="text-xs text-slate-400 mt-1">
              正在逐日读取信号、计算行业强度、模拟买卖（已耗时 {elapsedSec} 秒）
            </Text>
            <div className="w-full max-w-md mt-5">
              <Progress percent={Math.round(fakeProgress)} size="small" strokeColor="#059669" status={fakeProgress >= 100 ? 'success' : 'active'} />
            </div>
            <Text className="text-[10px] text-slate-300 mt-2">
              {signalMode === 'stored' ? '已有推理信号 · 通常 10-30 秒' : '逐日实时推理 · 可能数分钟'}
            </Text>
          </div>
        </div>
      )}

      {result && !loading && (
        <div className="space-y-4">
          {/* 指标卡 */}
          <div className="grid grid-cols-4 gap-3">
            {metricCards.map(mc => (
              <div key={mc.label} className="glass-panel rounded-2xl p-4 border border-slate-100/50">
                <Text className="text-[10px] text-slate-400 font-black uppercase tracking-widest block">{mc.label}</Text>
                <Text className={clsx('text-xl font-black tracking-tight block mt-1', mc.color)}>{mc.value}</Text>
                {mc.hint && <Text className="text-[9px] text-slate-400 block mt-0.5">{mc.hint}</Text>}
              </div>
            ))}
          </div>

          <Tabs
            defaultActiveKey="nav"
            size="small"
            className="inference-backtest-tabs"
            items={[
              {
                key: 'nav',
                label: <span className="flex items-center gap-1"><TrendingUp size={12} />净值曲线</span>,
                children: (
                  <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
                    {navOption ? <ReactECharts option={navOption} style={{ height: 320 }} notMerge /> : <Empty />}
                  </div>
                ),
              },
              {
                key: 'monthly',
                label: <span className="flex items-center gap-1"><BarChart3 size={12} />月度收益</span>,
                children: (
                  <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
                    {monthlyRows.length ? (
                      <Table dataSource={monthlyRows} rowKey="month" size="small" pagination={false}
                        columns={[
                          { title: '月份', dataIndex: 'month', render: (v: string) => <Text className="text-[11px] font-mono font-bold text-slate-700">{v}</Text> },
                          {
                            title: '收益率', dataIndex: 'ret',
                            render: (v: number) => (
                              <Text className={clsx('text-[11px] font-mono font-bold', v >= 0 ? 'text-emerald-600' : 'text-rose-600')}>{fmtPct(v)}</Text>
                            ),
                          },
                          {
                            title: '', dataIndex: 'ret',
                            render: (v: number) => (
                              <div className="w-40 h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className={clsx('h-full rounded-full', v >= 0 ? 'bg-emerald-500' : 'bg-rose-500')}
                                  style={{ width: `${Math.min(Math.abs(v) * 400, 100)}%` }} />
                              </div>
                            ),
                          },
                        ]}
                      />
                    ) : <Empty description={<span className="text-xs text-slate-400">回测区间内无月度数据</span>} />}
                  </div>
                ),
              },
              {
                key: 'trades',
                label: <span className="flex items-center gap-1"><Zap size={12} />交易流水</span>,
                children: (
                  <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
                    <Table dataSource={result.trades} rowKey={(r, i) => `${r.date}-${r.symbol}-${r.side}-${i}`} columns={tradeColumns} size="small"
                      pagination={{ pageSize: 20 }} scroll={{ x: 800 }} />
                  </div>
                ),
              },
              {
                key: 'selections',
                label: <span className="flex items-center gap-1"><Activity size={12} />逐日选股</span>,
                children: (
                  <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
                    <Table dataSource={result.daily_selections} rowKey="trade_date" columns={selectionColumns} size="small"
                      pagination={{ pageSize: 20 }} scroll={{ x: 700 }} />
                  </div>
                ),
              },
              {
                key: 'rotation',
                label: <span className="flex items-center gap-1"><PieChart size={12} />行业轮动</span>,
                children: (
                  <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
                    {rotationOption ? <ReactECharts option={rotationOption} style={{ height: 320 }} notMerge /> : <Empty description={<span className="text-xs text-slate-400">回测区间内无有效行业信号</span>} />}
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {!result && !loading && (
        <div className="py-16 text-center">
          <Empty description={<span className="text-xs text-slate-400 font-medium">配置策略参数并运行回测，基于推理信号验证选股策略</span>} />
        </div>
      )}
    </div>
  );
};
