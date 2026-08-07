import React, { useEffect, useState, useCallback } from 'react';
import {
  Button, Tag, Typography, Empty, Progress, Table, Tooltip, DatePicker, message, Modal, Select,
} from 'antd';
import { clsx } from 'clsx';
import dayjs from 'dayjs';
import {
  CheckCircle2, XCircle, Clock, Activity,
  CalendarRange, Info,
} from 'lucide-react';
import {
  modelTrainingService,
  BatchInferenceRecord,
} from '../../services/modelTrainingService';

const { Text } = Typography;

// ─── 单日结果表 ──────────────────────────────────────────────────────────────

type MemberRun = NonNullable<BatchInferenceRecord['member_runs']>[number];

const DayTable: React.FC<{ batch: BatchInferenceRecord }> = ({ batch }) => {
  const memberRuns = batch.member_runs || [];

  const statusMap: Record<string, { color: string; label: string }> = {
    pending: { color: 'default', label: '等待' },
    running: { color: 'processing', label: '运行中' },
    completed: { color: 'success', label: '完成' },
    failed: { color: 'error', label: '失败' },
    reused: { color: 'cyan', label: '复用' },
  };

  const columns = [
    {
      title: '#',
      width: 44,
      render: (_: unknown, __: unknown, idx: number) => (
        <Text className="text-[10px] font-black text-slate-400">{idx + 1}</Text>
      ),
    },
    {
      title: '交易日',
      dataIndex: 'trade_date',
      width: 110,
      render: (v: string) => (
        <Text className="text-[11px] font-mono font-bold text-slate-700">{v}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string, r: MemberRun) => {
        const key = r.reused ? 'reused' : v;
        const cfg = statusMap[key] || statusMap.pending;
        return <Tag color={cfg.color} className="m-0 border-0 text-[9px] font-black px-2 rounded-md">{cfg.label}</Tag>;
      },
    },
    {
      title: '信号数',
      dataIndex: 'signals_count',
      width: 70,
      render: (v: number) => (
        <Text className="text-[10px] font-mono text-slate-500">{v || '—'}</Text>
      ),
    },
  ];

  if (!memberRuns.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span className="text-[10px] text-slate-400">暂无逐日数据</span>} />;
  }

  return (
    <Table
      dataSource={memberRuns}
      columns={columns}
      rowKey="trade_date"
      size="small"
      pagination={false}
      scroll={{ y: 300 }}
      rowClassName={(_, idx) => clsx(idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/30')}
    />
  );
};

// ─── 主组件 ──────────────────────────────────────────────────────────────────

interface Props {
  modelId: string;
  horizonDays: number;
}

export const BatchSingleDayPanel: React.FC<Props> = ({ modelId }) => {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null]>([
    dayjs().subtract(10, 'day'),
    dayjs(),
  ]);
  const [reuseExisting, setReuseExisting] = useState(true);
  const [concurrency, setConcurrency] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [currentBatch, setCurrentBatch] = useState<BatchInferenceRecord | null>(null);
  const [pollTimer, setPollTimer] = useState<ReturnType<typeof setInterval> | null>(null);
  const [batches, setBatches] = useState<BatchInferenceRecord[]>([]);
  // 区间交易日统计（用于智能提示）
  const [rangeTradingDays, setRangeTradingDays] = useState<number | null>(null);
  const [rangeChecking, setRangeChecking] = useState(false);

  const loadBatches = useCallback(async () => {
    try {
      const result = await modelTrainingService.listBatchInferences(modelId);
      setBatches(result.items || []);
    } catch {
      // ignore
    }
  }, [modelId]);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  // 区间变化时查询实际交易日数，用于智能提示
  useEffect(() => {
    const [start, end] = dateRange;
    if (!start || !end) {
      setRangeTradingDays(null);
      return;
    }
    setRangeChecking(true);
    setRangeTradingDays(null);
    const timer = setTimeout(async () => {
      try {
        const dates = await modelTrainingService.getBacktestTradingDates(
          start.format('YYYY-MM-DD'),
          end.format('YYYY-MM-DD'),
        );
        setRangeTradingDays(dates.length);
      } catch {
        setRangeTradingDays(null);
      } finally {
        setRangeChecking(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [dateRange]);

  const startPolling = useCallback((batchId: string) => {
    if (pollTimer) clearInterval(pollTimer);
    const timer = setInterval(async () => {
      try {
        const batch = await modelTrainingService.getBatchInference(batchId);
        setCurrentBatch(batch);
        if (batch.status === 'completed' || batch.status === 'partial' || batch.status === 'failed') {
          clearInterval(timer);
          setPollTimer(null);
        }
      } catch {
        clearInterval(timer);
        setPollTimer(null);
      }
    }, 3000);
    setPollTimer(timer);
  }, [pollTimer]);

  useEffect(() => {
    return () => {
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [pollTimer]);

  const handleSubmit = async () => {
    const [start, end] = dateRange;
    if (!start || !end) {
      message.warning('请选择日期范围');
      return;
    }
    if (start.isAfter(end)) {
      message.warning('起始日期不能晚于结束日期');
      return;
    }
    if (end.isAfter(dayjs())) {
      message.warning('结束日期不能晚于今天');
      return;
    }
    // 长区间智能提示：超过 60 个交易日需确认
    const days = rangeTradingDays;
    if (days !== null && days > 60) {
      const estMinSerial = Math.round(days * 10 / 60);
      const estMinPara = Math.max(1, Math.round(estMinSerial / concurrency));
      const confirmed = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: `确认批量推理 ${days} 个交易日？`,
          content: `区间内共 ${days} 个交易日，并发 ${concurrency} 预计约 ${estMinPara} 分钟（串行约 ${estMinSerial} 分钟）。\n任务会持续运行，可在"历史批次"查看进度；中途停止后可重新提交同区间续跑（复用已完成交易日）。`,
          okText: '确认执行',
          okButtonProps: { danger: false },
          cancelText: '取消',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!confirmed) return;
    }
    setSubmitting(true);
    try {
      const batch = await modelTrainingService.submitBatchInference({
        model_id: modelId,
        mode: 'range',
        start_date: start.format('YYYY-MM-DD'),
        end_date: end.format('YYYY-MM-DD'),
        reuse_existing: reuseExisting,
        concurrency,
      });
      setCurrentBatch(batch);
      message.success(`批量单日推理已提交：${batch.batch_id}`);
      startPolling(batch.batch_id);
      loadBatches();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提交失败';
      message.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSelectBatch = async (batch: BatchInferenceRecord) => {
    setCurrentBatch(batch);
    if (batch.status === 'running') {
      startPolling(batch.batch_id);
    }
  };

  const handleStopBatch = async () => {
    if (!currentBatch) return;
    const confirmed = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '停止批量推理？',
        content: '将停止当前批次，已完成的交易日保留。之后重新提交同区间并开启"复用已有结果"，可续跑剩余交易日。',
        okText: '停止',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      });
    });
    if (!confirmed) return;
    setStopping(true);
    try {
      await modelTrainingService.deleteBatchInference(currentBatch.batch_id);
      message.success('已停止批量推理，可重新提交续跑');
      if (pollTimer) clearInterval(pollTimer);
      setPollTimer(null);
      setCurrentBatch({ ...currentBatch, status: 'failed' } as BatchInferenceRecord);
      loadBatches();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '停止失败';
      message.error(msg);
    } finally {
      setStopping(false);
    }
  };

  const progressPct = currentBatch
    ? Math.round((currentBatch.progress_done / Math.max(currentBatch.progress_total, 1)) * 100)
    : 0;

  const mode = currentBatch?.params?.window_meta?.mode ?? 'lookback';

  return (
    <div className="space-y-4">
      {/* 输入区 */}
      <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-emerald-500/10 p-2 rounded-xl text-emerald-600">
            <CalendarRange size={18} />
          </div>
          <Text className="text-sm font-black text-slate-800 uppercase tracking-tight leading-none">批量单日推理</Text>
        </div>

        <div className="grid grid-cols-12 gap-4 items-end">
          <div className="col-span-5">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">日期范围</Text>
            <DatePicker.RangePicker
              value={[dateRange[0], dateRange[1]]}
              onChange={(dates) => {
                if (dates && dates[0] && dates[1]) {
                  setDateRange([dates[0], dates[1]]);
                }
              }}
              disabledDate={d => d.isAfter(dayjs())}
              className="w-full rounded-xl h-9 border-slate-100"
              allowClear={false}
            />
          </div>
          <div className="col-span-2">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">并发度</Text>
            <Select value={concurrency} onChange={setConcurrency} className="w-full h-9" size="small">
              <Select.Option value={1}>1（串行）</Select.Option>
              <Select.Option value={3}>3（推荐）</Select.Option>
              <Select.Option value={5}>5（最快）</Select.Option>
            </Select>
          </div>
          <div className="col-span-3">
            <Text className="text-[10px] font-black text-slate-400 uppercase mb-1.5 block tracking-widest pl-1">续跑</Text>
            <div className="flex items-center gap-2 h-9 px-1">
              <label className="flex items-center gap-1 cursor-pointer">
                <input type="checkbox" checked={reuseExisting} onChange={e => setReuseExisting(e.target.checked)} className="accent-emerald-600" />
                <Text className="text-[10px] text-slate-600 font-medium">复用已有结果</Text>
              </label>
              <Tooltip title="开启后，已推理成功的交易日自动跳过。中途停止后重新提交同区间，可续跑剩余交易日，不重复计算">
                <Info size={12} className="text-slate-400 cursor-help" />
              </Tooltip>
            </div>
          </div>
          <div className="col-span-2">
            <Button
              type="primary"
              size="large"
              onClick={handleSubmit}
              loading={submitting}
              className="w-full rounded-xl h-9 bg-emerald-600 border-0 font-bold shadow-md shadow-emerald-100 text-xs"
            >
              批量推理
            </Button>
          </div>
        </div>

        {dateRange[0] && dateRange[1] && (
          <div className="mt-3 px-1 space-y-1">
            <Text className="text-[10px] text-slate-400">
              将按所选区间内的每个交易日并发执行单日推理
              {rangeChecking ? '（正在计算交易日数...）' : rangeTradingDays !== null
                ? `（约 ${rangeTradingDays} 个交易日 · 并发${concurrency}预计 ${Math.max(1, Math.round(rangeTradingDays * 10 / 60 / concurrency))} 分钟）`
                : ''}
            </Text>
            {rangeTradingDays !== null && rangeTradingDays > 60 && (
              <div className="flex items-center gap-1.5">
                <Info size={11} className="text-amber-500" />
                <Text className="text-[10px] text-amber-600 font-bold">
                  区间较长：并发{concurrency}预计约 {Math.max(1, Math.round(rangeTradingDays * 10 / 60 / concurrency))} 分钟，提交前会再次确认
                </Text>
              </div>
            )}
            {reuseExisting && (
              <div className="flex items-center gap-1.5">
                <Info size={11} className="text-emerald-500" />
                <Text className="text-[10px] text-emerald-600">
                  已开启续跑：区间内已推理成功的交易日将自动跳过，只补跑缺失的天数
                </Text>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 当前批次进度 */}
      {currentBatch && (
        <div className="glass-panel rounded-3xl p-5 border border-slate-100/50">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className={clsx(
                'p-2 rounded-xl',
                currentBatch.status === 'running' ? 'bg-blue-500/10 text-blue-500' :
                currentBatch.status === 'completed' ? 'bg-emerald-500/10 text-emerald-500' :
                currentBatch.status === 'partial' ? 'bg-amber-500/10 text-amber-500' :
                'bg-rose-500/10 text-rose-500'
              )}>
                {currentBatch.status === 'running' ? <Activity size={16} /> :
                 currentBatch.status === 'completed' ? <CheckCircle2 size={16} /> :
                 currentBatch.status === 'failed' ? <XCircle size={16} /> :
                 <Clock size={16} />}
              </div>
              <div>
                <Text className="text-xs font-black text-slate-800 block">{currentBatch.batch_id}</Text>
                <Text className="text-[10px] text-slate-400">
                  {mode === 'range'
                    ? `${currentBatch.params?.window_meta?.start_date} ~ ${currentBatch.params?.window_meta?.end_date}`
                    : currentBatch.anchor_date}
                  {' '}· 共 {currentBatch.progress_total} 个交易日
                  {typeof currentBatch.params?.concurrency === 'number' && currentBatch.params.concurrency > 1
                    ? ` · 并发 ${currentBatch.params.concurrency}`
                    : ''}
                </Text>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {currentBatch.status === 'running' && (
                <Button
                  size="small"
                  danger
                  onClick={handleStopBatch}
                  loading={stopping}
                  className="rounded-lg text-[10px] font-bold h-7 px-3 border-rose-200 text-rose-600"
                >
                  停止
                </Button>
              )}
              <Tag color={
                currentBatch.status === 'completed' ? 'green' :
                currentBatch.status === 'running' ? 'blue' :
                currentBatch.status === 'partial' ? 'orange' : 'red'
              } className="m-0 border-0 text-[9px] font-black uppercase rounded-md px-2">
                {currentBatch.status === 'failed' ? '已停止' : currentBatch.status}
              </Tag>
            </div>
          </div>

          {currentBatch.status === 'running' && (
            <Progress
              percent={progressPct}
              size="small"
              className="mb-1"
              strokeColor="#059669"
            />
          )}

          {currentBatch.error_message && (
            <div className="mt-2 p-2 bg-rose-50 rounded-lg border border-rose-100">
              <Text className="text-[10px] text-rose-600">{currentBatch.error_message}</Text>
            </div>
          )}

          {currentBatch.params?.window_meta?.warnings?.length > 0 && currentBatch.status !== 'failed' && (
            <div className="mt-2 p-2.5 bg-amber-50 rounded-lg border border-amber-100">
              {currentBatch.params.window_meta.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <Info size={11} className="text-amber-500 mt-0.5 shrink-0" />
                  <Text className="text-[10px] text-amber-700 leading-relaxed">{w}</Text>
                </div>
              ))}
            </div>
          )}

          {currentBatch.member_runs && currentBatch.member_runs.length > 0 && (
            <div className="mt-3">
              <DayTable batch={currentBatch} />
            </div>
          )}
        </div>
      )}

      {/* 历史批次 */}
      {batches.length > 0 && (
        <div className="glass-panel rounded-2xl p-4 border border-slate-100/50">
          <div className="flex items-center gap-2 mb-2">
            <Clock size={12} className="text-slate-400" />
            <Text className="text-[10px] font-black text-slate-400 uppercase tracking-widest">历史批次</Text>
          </div>
          <div className="flex gap-2 flex-wrap">
            {batches.slice(0, 8).map(b => {
              const bMode = b.params?.window_meta?.mode ?? 'lookback';
              const label = bMode === 'range'
                ? `${b.params?.window_meta?.start_date} ~ ${b.params?.window_meta?.end_date}`
                : `${b.anchor_date} N=${b.window_days}`;
              return (
                <Button
                  key={b.batch_id}
                  size="small"
                  type={currentBatch?.batch_id === b.batch_id ? 'primary' : 'default'}
                  className={clsx('rounded-lg text-[9px] font-bold h-7 px-3', currentBatch?.batch_id === b.batch_id ? 'bg-emerald-600 border-emerald-600' : 'border-slate-200')}
                  onClick={() => handleSelectBatch(b)}
                >
                  {label}
                  <Tag color={b.status === 'completed' ? 'green' : b.status === 'running' ? 'blue' : b.status === 'partial' ? 'orange' : 'red'}
                    className="m-0 ml-1 border-0 text-[7px] px-1 rounded">{b.status}</Tag>
                </Button>
              );
            })}
          </div>
        </div>
      )}

      {/* 空状态 */}
      {!currentBatch && (
        <div className="py-16">
          <Empty description={<span className="text-xs text-slate-400 font-medium">选择日期范围并提交批量单日推理，逐日执行并展示进度</span>} />
        </div>
      )}
    </div>
  );
};
