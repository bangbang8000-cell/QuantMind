/**
 * 模型评估模块 — 滚动回测评估模型预测质量
 *
 * 功能：
 * - 选择模型 + 日期范围 + 预测周期
 * - 运行滚动回测，对比预测分数与实际收益
 * - 展示 IC、IC_IR、命中率、十分位收益等指标
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Select, DatePicker, Button, Space, Spin, message,
  Row, Col, Statistic, Table, Typography, Divider, Empty, Popconfirm,
  InputNumber, Switch, Tooltip, Alert, Tag,
} from 'antd';
import {
  BarChart3, TrendingUp, Activity, Target, Zap, Trash2, RotateCcw,
} from 'lucide-react';
import dayjs from 'dayjs';
import { clsx } from 'clsx';
import ReactECharts from 'echarts-for-react';
import { modelTrainingService } from '../../services/modelTrainingService';

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface ModelInfo {
  model_id: string;
  model_dir: string;
  framework: string;
  feature_count: number;
  target_horizon_days: number;
  metrics: Record<string, any>;
  type: string;
}

interface BacktestResult {
  status: string;
  model_id: string;
  horizon: number;
  label_definition?: string;
  warnings?: string[];
  metrics: {
    ic_mean: number;
    ic_std: number;
    ic_ir: number;
    hit_rate: number;
    ic_positive_rate?: number;
    n_dates: number;
    avg_top_decile: number;
    avg_bottom_decile: number;
    monotonicity: number;
    decile_rank_ic: number;
    n_deciles?: number;
    t_stat?: number | null;
    overlap_factor?: number;
    sample_interval?: number;
    benchmark_type?: string;
    // 主指标：纯多头（A股可实现）
    long_return_gross?: number;
    long_return_net?: number;
    long_excess_net?: number;
    sharpe_long?: number;
    sharpe_long_excess?: number;
    max_drawdown_long?: number;
    cumulative_long_net?: number[];
    // 成本
    cost_per_period?: number;
    cost_drag_annual?: number;
    turnover_mean?: number;
    cost_model?: Record<string, number>;
    // 参考指标：多空（需融券，理论值）
    long_short_return: number;
    long_short_is_theoretical?: boolean;
    sharpe_ls?: number;
    max_drawdown_ls?: number;
    cumulative_ic?: number[];
    cumulative_ls?: number[];
    monthly_ic?: Record<string, number>;
    up_capture?: number;
    down_capture?: number;
  };
  avg_decile_returns: Record<number, number>;
  per_day: Array<{
    date: string;
    ic: number;
    n_stocks: number;
    decile_returns: Record<number, number>;
    top_return?: number;
    bottom_return?: number;
    top_10pct_return: number;
    bottom_10pct_return: number;
    top_win_rate?: number;
  }>;
  errors: Array<{ date: string; error: string }>;
}

/** A股标准费率，与后端 trading_cost.py 默认值保持一致 */
const DEFAULT_COST = {
  commission_rate: 0.00025,
  stamp_duty: 0.001,
  transfer_fee: 0.00001,
  slippage: 0.001,
};

interface ModelEvaluationModuleProps {
  initialModelId?: string;
  compact?: boolean;
}

export const ModelEvaluationModule: React.FC<ModelEvaluationModuleProps> = ({ initialModelId, compact }) => {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>(initialModelId || '');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(6, 'month'),
    dayjs().subtract(1, 'day'),
  ]);
  const [horizon, setHorizon] = useState<number>(10);
  const [sampleInterval, setSampleInterval] = useState<number>(3);
  const [loading, setLoading] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string>('');
  const [multiHorizonResult, setMultiHorizonResult] = useState<any>(null);
  const [multiHorizonLoading, setMultiHorizonLoading] = useState(false);
  const [cost, setCost] = useState({ ...DEFAULT_COST });
  const [excludeLimitMoves, setExcludeLimitMoves] = useState(true);

  useEffect(() => {
    loadModels();
  }, []);

  // Load history when model changes
  useEffect(() => {
    if (selectedModelId) {
      loadHistory(selectedModelId);
    } else {
      setHistory([]);
      setResult(null);
    }
  }, [selectedModelId]);

  // 成本参数默认值从模型 metadata.context 回填（后端同样做三级回退，此处仅为可见性）
  useEffect(() => {
    const ctx = (models.find(m => m.model_id === selectedModelId) as any)?.context;
    setCost({
      ...DEFAULT_COST,
      ...(Number.isFinite(ctx?.commission_rate) ? { commission_rate: ctx.commission_rate } : {}),
      ...(Number.isFinite(ctx?.slippage) ? { slippage: ctx.slippage } : {}),
    });
  }, [selectedModelId, models]);

  const loadModels = async () => {
    setModelsLoading(true);
    try {
      const list = await modelTrainingService.listModelsForBacktest();
      setModels(list);
    } catch (e: any) {
      message.error('加载模型列表失败: ' + (e.message || '未知错误'));
    } finally {
      setModelsLoading(false);
    }
  };

  const loadHistory = async (modelId: string) => {
    setHistoryLoading(true);
    try {
      const records = await modelTrainingService.getBacktestHistory(modelId);
      setHistory(records);
      // Auto-load latest result
      if (records.length > 0 && !result) {
        loadDetail(modelId, records[0].run_id);
      }
    } catch (e: any) {
      // Silent fail for history
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadDetail = async (modelId: string, runId: string) => {
    try {
      const detail = await modelTrainingService.getBacktestDetail(modelId, runId);
      setResult(detail);
      setActiveRunId(runId);
    } catch (e: any) {
      message.error('加载回测详情失败');
    }
  };

  const deleteHistoryItem = async (runId: string) => {
    try {
      await modelTrainingService.deleteBacktestHistory(selectedModelId, runId);
      setHistory(prev => prev.filter(h => h.run_id !== runId));
      if (activeRunId === runId) {
        setResult(null);
        setActiveRunId('');
      }
      message.success('已删除');
    } catch (e: any) {
      message.error('删除失败');
    }
  };

  const runBacktest = async () => {
    if (!selectedModelId) {
      message.warning('请选择模型');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const resp = await modelTrainingService.runModelBacktest({
        model_id: selectedModelId,
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        horizon,
        sample_interval: sampleInterval,
        cost,
        exclude_limit_moves: excludeLimitMoves,
      });
      if (resp.status === 'success') {
        setResult(resp);
        setActiveRunId(resp.run_id || '');
        message.success(`回测完成，共 ${resp.metrics.n_dates} 个交易日`);
        // Reload history
        loadHistory(selectedModelId);
      } else {
        message.error(resp.error || '回测失败');
      }
    } catch (e: any) {
      message.error('回测请求失败: ' + (e.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  const runMultiHorizonBacktest = async () => {
    if (!selectedModelId) {
      message.warning('请选择模型');
      return;
    }
    setMultiHorizonLoading(true);
    setMultiHorizonResult(null);
    try {
      const resp = await modelTrainingService.runMultiHorizonBacktest({
        model_id: selectedModelId,
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        horizons: [1, 5, 10, 20],
        sample_interval: sampleInterval,
        cost,
        exclude_limit_moves: excludeLimitMoves,
      });
      if (resp.status === 'success') {
        setMultiHorizonResult(resp);
        message.success('多周期对比回测完成');
      } else {
        message.error(resp.error || '多周期回测失败');
      }
    } catch (e: any) {
      message.error('多周期回测请求失败: ' + (e.message || '未知错误'));
    } finally {
      setMultiHorizonLoading(false);
    }
  };

  // IC 时间序列图
  const icChartOption = result ? {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(0,0,0,0.1)',
      textStyle: { color: '#374151' },
      formatter: (params: any) => {
        const p = params[0];
        return `${p.axisValue}<br/>IC: ${(p.value as number).toFixed(4)}`;
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: result.per_day.map(d => d.date),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280' },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    series: [
      {
        name: 'IC',
        type: 'line',
        data: result.per_day.map(d => d.ic),
        smooth: true,
        lineStyle: { width: 2, color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59,130,246,0.2)' },
              { offset: 1, color: 'rgba(59,130,246,0.02)' },
            ],
          },
        },
        markLine: {
          silent: true,
          data: [{ yAxis: 0, lineStyle: { color: '#ef4444', type: 'dashed' as const, width: 1 } }],
        },
      },
    ],
  } : null;

  // 十分位收益柱状图
  const decileChartOption = result ? {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(0,0,0,0.1)',
      textStyle: { color: '#374151' },
      formatter: (params: any) => {
        const p = params[0];
        return `Decile ${p.axisValue}<br/>平均收益: ${((p.value as number) * 100).toFixed(2)}%`;
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: Array.from({ length: 10 }, (_, i) => `D${i + 1}`),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280' },
    },
    yAxis: {
      type: 'value' as const,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    series: [{
      name: '平均收益',
      type: 'bar',
      data: Array.from({ length: 10 }, (_, i) => result.avg_decile_returns[i] ?? 0),
      itemStyle: {
        color: (params: any) => {
          const val = params.value as number;
          return val >= 0 ? '#ef4444' : '#22c55e';
        },
        borderRadius: [4, 4, 0, 0],
      },
    }],
  } : null;

  // Per-day table columns
  const columns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
    {
      title: 'IC', dataIndex: 'ic', key: 'ic', width: 100,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
          {v.toFixed(4)}
        </span>
      ),
    },
    { title: '股票数', dataIndex: 'n_stocks', key: 'n_stocks', width: 80 },
    {
      title: 'Top 10%', dataIndex: 'top_10pct_return', key: 'top10', width: 100,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#ef4444' : '#22c55e' }}>
          {(v * 100).toFixed(2)}%
        </span>
      ),
    },
    {
      title: 'Bottom 10%', dataIndex: 'bottom_10pct_return', key: 'bottom10', width: 100,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#ef4444' : '#22c55e' }}>
          {(v * 100).toFixed(2)}%
        </span>
      ),
    },
    {
      title: '多空收益', key: 'ls', width: 100,
      render: (_: any, record: any) => {
        const ls = (record.top_10pct_return || 0) - (record.bottom_10pct_return || 0);
        return (
          <span style={{ color: ls > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
            {(ls * 100).toFixed(2)}%
          </span>
        );
      },
    },
  ];

  // A股习惯：涨红跌绿。正值为红（rose），负值为绿（emerald）
  const pnlColor = (v: number) => (v >= 0 ? 'text-rose-600' : 'text-emerald-600');
  const pct = (v: number | undefined | null, digits = 2) =>
    v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`;

  const metricCards = result?.metrics ? [
    {
      // 主决策指标：扣除交易成本后的多头超额（A股可实现）
      label: '多头超额(净)',
      value: pct(result.metrics.long_excess_net),
      icon: TrendingUp,
      color: pnlColor(result.metrics.long_excess_net ?? 0),
      desc: `Top${result.metrics.n_deciles ?? 10}分位 − 等权基准 − 交易成本，每期持有 T+${result.horizon}`,
    },
    {
      label: '多头Sharpe',
      value: result.metrics.sharpe_long?.toFixed(2) ?? '—',
      icon: Zap,
      color: pnlColor(result.metrics.sharpe_long ?? 0),
      desc: '多头净收益年化Sharpe，已按重叠持有期做Newey-West校正',
    },
    {
      label: 'IC 均值',
      value: result.metrics.ic_mean.toFixed(4),
      icon: Activity,
      color: pnlColor(result.metrics.ic_mean),
      desc: `预测分与真实 T+${result.horizon} 前瞻收益的秩相关（典型有效区间 0.02~0.06）`,
    },
    {
      label: '方向命中率',
      value: `${(result.metrics.hit_rate * 100).toFixed(1)}%`,
      icon: Target,
      color: result.metrics.hit_rate >= 0.5 ? 'text-rose-600' : 'text-emerald-600',
      desc: 'Top组合中前瞻收益为正的个股占比（随机为50%）',
    },
  ] : [];

  // 累积IC曲线
  const cumulativeICOption = result?.metrics?.cumulative_ic ? {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(0,0,0,0.1)',
      textStyle: { color: '#374151' },
      formatter: (params: any) => {
        const p = params[0];
        return `${p.axisValue}<br/>累积IC: ${(p.value as number).toFixed(4)}`;
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: result.per_day.map(d => d.date),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280' },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    series: [{
      name: '累积IC',
      type: 'line',
      data: result.metrics.cumulative_ic,
      smooth: true,
      lineStyle: { width: 2, color: '#8b5cf6' },
      itemStyle: { color: '#8b5cf6' },
      areaStyle: {
        color: {
          type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(139,92,246,0.2)' },
            { offset: 1, color: 'rgba(139,92,246,0.02)' },
          ],
        },
      },
    }],
  } : null;

  // 月度IC分布
  const monthlyICOption = result?.metrics?.monthly_ic ? (() => {
    const months = Object.keys(result.metrics.monthly_ic).sort();
    const values = months.map(m => result.metrics.monthly_ic[m]);
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis' as const,
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: 'rgba(0,0,0,0.1)',
        textStyle: { color: '#374151' },
        formatter: (params: any) => {
          const p = params[0];
          return `${p.axisValue}<br/>月度IC: ${(p.value as number).toFixed(4)}`;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category' as const,
        data: months,
        axisLine: { lineStyle: { color: '#d1d5db' } },
        axisLabel: { color: '#6b7280', rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value' as const,
        axisLine: { lineStyle: { color: '#d1d5db' } },
        axisLabel: { color: '#6b7280' },
        splitLine: { lineStyle: { color: '#e5e7eb' } },
      },
      series: [{
        name: '月度IC',
        type: 'bar',
        data: values,
        itemStyle: {
          color: (params: any) => {
            const val = params.value as number;
            return val >= 0 ? '#ef4444' : '#22c55e';
          },
          borderRadius: [4, 4, 0, 0],
        },
      }],
    };
  })() : null;

  // 多空净值曲线
  const lsEquityOption = result?.metrics?.cumulative_ls ? {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(0,0,0,0.1)',
      textStyle: { color: '#374151' },
      formatter: (params: any) => {
        const p = params[0];
        return `${p.axisValue}<br/>累积多空收益: ${((p.value as number) * 100).toFixed(2)}%`;
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: result.per_day.map(d => d.date),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280', formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    series: [{
      name: '多空净值',
      type: 'line',
      data: result.metrics.cumulative_ls,
      smooth: true,
      lineStyle: { width: 2, color: '#f59e0b' },
      itemStyle: { color: '#f59e0b' },
      areaStyle: {
        color: {
          type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(245,158,11,0.2)' },
            { offset: 1, color: 'rgba(245,158,11,0.02)' },
          ],
        },
      },
      markLine: {
        silent: true,
        data: [{ yAxis: 0, lineStyle: { color: '#ef4444', type: 'dashed' as const, width: 1 } }],
      },
    }],
  } : null;

  return (
    <div className="space-y-6">
      {/* 配置面板 */}
      <Card title="回测配置" className="shadow-sm">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <Text className="text-xs text-gray-500 mb-1 block">选择模型</Text>
            <Select
              style={{ width: 280 }}
              placeholder="选择要评估的模型"
              value={selectedModelId || undefined}
              onChange={setSelectedModelId}
              loading={modelsLoading}
              showSearch
              optionFilterProp="label"
              options={models.map(m => ({
                value: m.model_id,
                label: `${m.model_id} (${m.framework}, ${m.feature_count}特征)`,
              }))}
            />
          </div>
          <div>
            <Text className="text-xs text-gray-500 mb-1 block">日期范围</Text>
            <RangePicker
              value={dateRange}
              onChange={(dates) => {
                if (dates && dates[0] && dates[1]) {
                  setDateRange([dates[0], dates[1]]);
                }
              }}
              format="YYYY-MM-DD"
            />
          </div>
          <div>
            <Text className="text-xs text-gray-500 mb-1 block">预测周期</Text>
            <Select
              style={{ width: 100 }}
              value={horizon}
              onChange={setHorizon}
              options={[
                { value: 5, label: 'T+5' },
                { value: 10, label: 'T+10' },
                { value: 20, label: 'T+20' },
              ]}
            />
          </div>
          <div>
            <Text className="text-xs text-gray-500 mb-1 block">采样间隔</Text>
            <Select
              style={{ width: 120 }}
              value={sampleInterval}
              onChange={setSampleInterval}
              options={[
                { value: 3, label: '每3个交易日' },
                { value: 5, label: '每5个交易日' },
                { value: 10, label: '每10个交易日' },
                { value: 20, label: '每20个交易日' },
              ]}
            />
          </div>
          <Button
            type="primary"
            icon={<BarChart3 className="w-4 h-4" />}
            onClick={runBacktest}
            loading={loading}
            disabled={!selectedModelId}
          >
            开始回测
          </Button>
          <Button
            icon={<BarChart3 className="w-4 h-4" />}
            onClick={runMultiHorizonBacktest}
            loading={multiHorizonLoading}
            disabled={!selectedModelId}
          >
            多周期对比
          </Button>
        </div>

        <Divider className="my-4" />

        {/* 交易成本参数：留空则回退模型 metadata.context，再回退 A股标准费率 */}
        <div className="flex flex-wrap gap-4 items-end">
          <Text className="text-xs font-semibold text-gray-600 mb-1">交易成本</Text>
          {([
            ['commission_rate', '佣金(单边)'],
            ['stamp_duty', '印花税(卖出)'],
            ['transfer_fee', '过户费(沪市)'],
            ['slippage', '滑点(单边)'],
          ] as const).map(([key, label]) => (
            <div key={key}>
              <Text className="text-xs text-gray-500 mb-1 block">{label}</Text>
              <InputNumber
                style={{ width: 130 }}
                min={0}
                max={0.05}
                step={0.0001}
                value={cost[key]}
                onChange={v => setCost({ ...cost, [key]: Number(v ?? 0) })}
                formatter={v => `${(Number(v ?? 0) * 100).toFixed(4)}%`}
                parser={v => Number(String(v).replace('%', '')) / 100}
              />
            </div>
          ))}
          <div>
            <Text className="text-xs text-gray-500 mb-1 block">往返成本</Text>
            <Text className="text-sm font-bold text-rose-600 font-mono block h-8 leading-8">
              {((cost.commission_rate * 2 + cost.slippage * 2 + cost.stamp_duty) * 100).toFixed(3)}%
            </Text>
          </div>
          <Tooltip title="信号日涨停的股票次日一字板买不进，计入组合会高估收益">
            <div>
              <Text className="text-xs text-gray-500 mb-1 block">剔除涨跌停</Text>
              <Switch checked={excludeLimitMoves} onChange={setExcludeLimitMoves} />
            </div>
          </Tooltip>
        </div>
      </Card>

      {/* 样本内 / 标签警示 */}
      {result?.warnings && result.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="回测结果需谨慎解读"
          description={
            <ul className="list-disc pl-5 space-y-1 text-xs">
              {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          }
        />
      )}

      {/* 加载中 */}
      {(loading || multiHorizonLoading) && (
        <Card className="shadow-sm">
          <div className="flex items-center justify-center py-12">
            <Spin size="large" tip={multiHorizonLoading ? "正在执行多周期对比回测..." : "正在执行回测，请稍候..."} />
          </div>
        </Card>
      )}

      {/* 多周期对比回测结果 */}
      {multiHorizonResult && multiHorizonResult.status === 'success' && (
        <Card title="多周期对比回测结果" className="shadow-sm"
          extra={
            <Text className="text-xs text-gray-400">
              最佳周期: {multiHorizonResult.best_horizon}
              {multiHorizonResult.best_horizon_criterion ? `（按${multiHorizonResult.best_horizon_criterion}）` : ''}
            </Text>
          }
        >
          <Table
            dataSource={Object.entries(multiHorizonResult.horizons).map(([key, val]: [string, any]) => ({
              horizon: key,
              ...val,
            }))}
            rowKey="horizon"
            size="small"
            pagination={false}
            columns={[
              { title: '预测周期', dataIndex: 'horizon', key: 'horizon', width: 100 },
              {
                title: '多头超额(净)', key: 'excess', width: 120,
                render: (_: any, r: any) => r.long_excess_net != null ? (
                  <span className={clsx('font-semibold font-mono', pnlColor(r.long_excess_net))}>
                    {pct(r.long_excess_net)}
                  </span>
                ) : r.error || '-',
              },
              {
                title: '多头Sharpe', key: 'sharpeLong', width: 100,
                render: (_: any, r: any) => r.sharpe_long != null ? (
                  <span className={clsx('font-mono', pnlColor(r.sharpe_long))}>{r.sharpe_long.toFixed(2)}</span>
                ) : '-',
              },
              {
                title: 'IC均值', key: 'ic', width: 100,
                render: (_: any, r: any) => r.ic_mean != null ? (
                  <span className={clsx('font-semibold font-mono', pnlColor(r.ic_mean))}>
                    {r.ic_mean.toFixed(4)}
                  </span>
                ) : r.error || '-',
              },
              {
                title: 'IC_IR', key: 'icir', width: 80,
                render: (_: any, r: any) => r.ic_ir?.toFixed(2) ?? '-',
              },
              {
                title: 't值', key: 'tstat', width: 80,
                render: (_: any, r: any) => r.t_stat != null ? (
                  <span className={clsx('font-mono', Math.abs(r.t_stat) >= 2 ? 'font-bold' : 'text-gray-400')}>
                    {r.t_stat.toFixed(2)}
                  </span>
                ) : '-',
              },
              {
                title: '方向命中率', key: 'hit', width: 100,
                render: (_: any, r: any) => r.hit_rate != null ? `${(r.hit_rate * 100).toFixed(0)}%` : '-',
              },
              {
                title: (
                  <Tooltip title="A股做空需融券，券源仅约1000-1600只、成本8-10%/年，此为理论值，不可直接复制">
                    <span>多空收益 ⓘ</span>
                  </Tooltip>
                ),
                key: 'ls', width: 110,
                render: (_: any, r: any) => r.long_short_return != null ? (
                  <span className={clsx('font-mono opacity-60', pnlColor(r.long_short_return))}>
                    {pct(r.long_short_return)}
                  </span>
                ) : '-',
              },
              {
                title: 'Sharpe', key: 'sharpe', width: 80,
                render: (_: any, r: any) => r.sharpe_ls?.toFixed(2) ?? '-',
              },
              {
                title: '换手率', key: 'turnover', width: 80,
                render: (_: any, r: any) => r.turnover_mean != null ? `${(r.turnover_mean * 100).toFixed(0)}%` : '-',
              },
              { title: '天数', dataIndex: 'n_dates', key: 'n_dates', width: 60 },
            ]}
          />
        </Card>
      )}

      {/* 结果展示 */}
      {result && result.status === 'success' && (
        <>
          {/* 指标卡片 */}
          <Row gutter={16}>
            {metricCards.map((card) => {
              const Icon = card.icon;
              return (
                <Col span={6} key={card.label}>
                  <Card className="shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                        <Icon className={`w-5 h-5 ${card.color}`} />
                      </div>
                      <div>
                        <div className="text-xs text-gray-500">{card.label}</div>
                        <div className={`text-xl font-bold ${card.color}`}>{card.value}</div>
                        <div className="text-[10px] text-gray-400 mt-0.5">{card.desc}</div>
                      </div>
                    </div>
                  </Card>
                </Col>
              );
            })}
          </Row>

          {/* 补充指标 */}
          <Card className="shadow-sm" size="small">
            <div className="flex flex-wrap gap-6">
              <Statistic title="IC 标准差" value={result.metrics.ic_std.toFixed(4)} />
              <Statistic title="IC_IR" value={result.metrics.ic_ir.toFixed(2)} />
              <Statistic title="IC 为正天数占比" value={`${((result.metrics.ic_positive_rate ?? 0) * 100).toFixed(0)}%`} />
              <Statistic title="十分位单调性" value={`${(result.metrics.monotonicity * 100).toFixed(0)}%`} />
              <Statistic title="Decile Rank IC" value={result.metrics.decile_rank_ic.toFixed(4)} />
              <Tooltip title="IC序列的t统计量，已按重叠持有期做Newey-West自相关校正。|t| ≥ 2 才算统计显著。">
                <Statistic
                  title="t 值 (NW校正) ⓘ"
                  value={result.metrics.t_stat != null ? result.metrics.t_stat.toFixed(2) : '—'}
                  valueStyle={{
                    color: Math.abs(result.metrics.t_stat ?? 0) >= 2 ? '#e11d48' : '#94a3b8',
                  }}
                />
              </Tooltip>
              <Statistic title="回测天数" value={result.metrics.n_dates} />
              <Statistic title="失败天数" value={result.errors.length} />
              <Statistic
                title={`平均Top${result.metrics.n_deciles ?? 10}分位`}
                value={pct(result.metrics.avg_top_decile)}
                valueStyle={{ color: (result.metrics.avg_top_decile ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
              <Statistic
                title="平均Bottom分位"
                value={pct(result.metrics.avg_bottom_decile)}
                valueStyle={{ color: (result.metrics.avg_bottom_decile ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
            </div>
          </Card>

          {/* 交易成本 */}
          <Card className="shadow-sm" size="small" title="交易成本影响（A股实盘摩擦）">
            <div className="flex flex-wrap gap-6">
              <Statistic
                title="单边换手率"
                value={result.metrics.turnover_mean != null ? `${(result.metrics.turnover_mean * 100).toFixed(0)}%` : '—'}
              />
              <Statistic
                title="往返成本率"
                value={result.metrics.cost_model?.round_trip_cost != null
                  ? `${(result.metrics.cost_model.round_trip_cost * 100).toFixed(3)}%` : '—'}
              />
              <Statistic
                title="每期成本拖累"
                value={pct(result.metrics.cost_per_period, 3)}
                valueStyle={{ color: '#059669' }}
              />
              <Tooltip title="年化成本拖累 = 单边换手 × 往返成本 × (252 / 采样间隔)">
                <Statistic
                  title="年化成本拖累 ⓘ"
                  value={pct(result.metrics.cost_drag_annual)}
                  valueStyle={{ color: '#059669' }}
                />
              </Tooltip>
              <Statistic
                title="多头毛收益"
                value={pct(result.metrics.long_return_gross)}
                valueStyle={{ color: (result.metrics.long_return_gross ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
              <Statistic
                title="多头净收益"
                value={pct(result.metrics.long_return_net)}
                valueStyle={{ color: (result.metrics.long_return_net ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
              <Statistic
                title="多头最大回撤"
                value={pct(result.metrics.max_drawdown_long)}
                valueStyle={{ color: (result.metrics.max_drawdown_long ?? 0) < 0.2 ? '#e11d48' : '#059669' }}
              />
            </div>
          </Card>

          {/* 参考指标 */}
          <Card
            className="shadow-sm"
            size="small"
            title={
              <div className="flex items-center gap-2">
                <span>参考指标</span>
                <Tag color="orange" className="text-[10px] m-0">理论值</Tag>
              </div>
            }
            extra={
              <Text className="text-xs text-gray-400">
                基准：{result.metrics.benchmark_type === 'equal_weight_universe' ? '等权全市场（非指数）' : result.metrics.benchmark_type || '—'}
                {result.metrics.overlap_factor != null && result.metrics.overlap_factor > 1
                  ? ` · 持有期重叠 ${result.metrics.overlap_factor.toFixed(1)}x` : ''}
              </Text>
            }
          >
            <Alert
              type="info"
              showIcon
              className="mb-4"
              message="以下多空指标为理论值，A股实盘不可直接复制"
              description="做空A股需融券，券源仅约 1000-1600 只且受限，融券成本约 8-10%/年。请以上方「多头超额(净)」作为决策依据。"
            />
            <div className="flex flex-wrap gap-6">
              <Statistic
                title="多空收益(毛)"
                value={pct(result.metrics.long_short_return)}
                valueStyle={{ color: (result.metrics.long_short_return ?? 0) >= 0 ? '#e11d48' : '#059669', opacity: 0.7 }}
              />
              <Statistic
                title="多空Sharpe"
                value={result.metrics.sharpe_ls?.toFixed(2) ?? '—'}
                valueStyle={{ opacity: 0.7 }}
              />
              <Statistic
                title="多空最大回撤"
                value={pct(result.metrics.max_drawdown_ls)}
                valueStyle={{ opacity: 0.7 }}
              />
              <Statistic
                title="上涨捕捉"
                value={result.metrics.up_capture?.toFixed(4) ?? '—'}
                valueStyle={{ color: (result.metrics.up_capture ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
              <Statistic
                title="下跌捕捉"
                value={result.metrics.down_capture?.toFixed(4) ?? '—'}
                valueStyle={{ color: (result.metrics.down_capture ?? 0) >= 0 ? '#e11d48' : '#059669' }}
              />
            </div>
          </Card>

          {/* 图表 */}
          <Row gutter={16}>
            <Col span={14}>
              <Card title="IC 时间序列" className="shadow-sm" size="small">
                {icChartOption && (
                  <ReactECharts option={icChartOption} style={{ height: 300 }} />
                )}
              </Card>
            </Col>
            <Col span={10}>
              <Card title="十分位平均收益" className="shadow-sm" size="small">
                {decileChartOption && (
                  <ReactECharts option={decileChartOption} style={{ height: 300 }} />
                )}
              </Card>
            </Col>
          </Row>

          {/* 增强图表 */}
          <Row gutter={16}>
            <Col span={12}>
              <Card title="累积IC曲线" className="shadow-sm" size="small">
                {cumulativeICOption && (
                  <ReactECharts option={cumulativeICOption} style={{ height: 280 }} />
                )}
              </Card>
            </Col>
            <Col span={12}>
              <Card title="多空净值曲线" className="shadow-sm" size="small">
                {lsEquityOption && (
                  <ReactECharts option={lsEquityOption} style={{ height: 280 }} />
                )}
              </Card>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={24}>
              <Card title="月度IC分布" className="shadow-sm" size="small">
                {monthlyICOption && (
                  <ReactECharts option={monthlyICOption} style={{ height: 250 }} />
                )}
              </Card>
            </Col>
          </Row>

          {/* 逐日明细 */}
          <Card title="逐日回测明细" className="shadow-sm" size="small">
            <Table
              dataSource={result.per_day}
              columns={columns}
              rowKey="date"
              size="small"
              pagination={{ pageSize: 15, showTotal: (total) => `共 ${total} 天` }}
              scroll={{ x: 700 }}
            />
          </Card>

          {/* 错误列表 */}
          {result.errors.length > 0 && (
            <Card title={`失败日期 (${result.errors.length})`} className="shadow-sm" size="small">
              <Table
                dataSource={result.errors}
                columns={[
                  { title: '日期', dataIndex: 'date', key: 'date' },
                  { title: '错误信息', dataIndex: 'error', key: 'error' },
                ]}
                rowKey="date"
                size="small"
                pagination={false}
              />
            </Card>
          )}
        </>
      )}

      {/* 回测历史 */}
      {selectedModelId && history.length > 0 && (
        <Card title="回测历史" className="shadow-sm" size="small"
          extra={<Text className="text-xs text-gray-400">共 {history.length} 条记录</Text>}
        >
          <Table
            dataSource={history}
            rowKey="run_id"
            size="small"
            pagination={false}
            scroll={{ x: 600 }}
            rowClassName={(record) => record.run_id === activeRunId ? 'bg-blue-50' : ''}
            onRow={(record) => ({
              onClick: () => loadDetail(selectedModelId, record.run_id),
              style: { cursor: 'pointer' },
            })}
            columns={[
              {
                title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
                render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '-',
              },
              {
                title: '日期范围', key: 'range', width: 200,
                render: (_: any, r: any) => r.date_range?.length === 2
                  ? `${r.date_range[0]} ~ ${r.date_range[1]}` : '-',
              },
              { title: '天数', dataIndex: 'n_dates', key: 'n_dates', width: 60 },
              {
                title: 'IC均值', key: 'ic', width: 90,
                render: (_: any, r: any) => {
                  const ic = r.metrics?.ic_mean;
                  return ic != null ? (
                    <span style={{ color: ic > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
                      {ic.toFixed(4)}
                    </span>
                  ) : '-';
                },
              },
              {
                title: 'IC_IR', key: 'icir', width: 70,
                render: (_: any, r: any) => r.metrics?.ic_ir?.toFixed(2) ?? '-',
              },
              {
                title: '命中率', key: 'hit', width: 70,
                render: (_: any, r: any) => {
                  const hr = r.metrics?.hit_rate;
                  return hr != null ? `${(hr * 100).toFixed(0)}%` : '-';
                },
              },
              {
                title: 'T+10', key: 'horizon', width: 50,
                render: (_: any, r: any) => `T+${r.horizon || 10}`,
              },
              {
                title: '', key: 'actions', width: 40,
                render: (_: any, r: any) => (
                  <Popconfirm title="确定删除？" onConfirm={(e) => { e?.stopPropagation(); deleteHistoryItem(r.run_id); }}>
                    <Button type="text" size="small" danger icon={<Trash2 className="w-3 h-3" />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* 空状态 */}
      {!loading && !result && history.length === 0 && (
        <Card className="shadow-sm">
          <Empty
            description="选择模型和日期范围，点击「开始回测」评估模型预测质量"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      )}
    </div>
  );
};
