import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Typography, Button, Select, Table, Tag, Spin, Empty, Alert, Progress } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import {
  submitScoreCalibration,
  getCalibrationTask,
  getCalibrationHistory,
  ScoreCalibrationResponse,
  CalibrationHistoryItem,
} from '../../services/stockPickingService';

const { Text } = Typography;

/** 分数档颜色：负分红、低分灰、黄金区绿 */
const bandColor = (band: string): string => {
  if (band.includes('-')) return '#f43f5e';
  if (band === '0.08~0.10' || band === '0.10~0.12') return '#10b981';
  if (band.startsWith('0.05') || band.startsWith('0.1')) return '#f59e0b';
  return '#64748b';
};

/** 数值颜色：正绿负红 */
const numColor = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '#94a3b8';
  return v > 0 ? '#10b981' : v < 0 ? '#f43f5e' : '#64748b';
};

export const ModelScoreResearch: React.FC = () => {
  const [data, setData] = useState<ScoreCalibrationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');
  const [days, setDays] = useState(180);
  const [horizons, setHorizons] = useState('1,3,5,10');
  const [history, setHistory] = useState<CalibrationHistoryItem[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const h = await getCalibrationHistory(20);
      if (h.status === 'success') setHistory(h.items || []);
    } catch (err: any) {
      console.error('[ScoreCalibration] load history failed:', err);
    }
  }, []);

  const load = useCallback(async () => {
    clearPoll();
    setLoading(true);
    setData(null);
    setProgress(0);
    setProgressMsg('提交校准任务...');
    try {
      const res = await submitScoreCalibration({ days, horizons, top_n: 50 });
      if (res.status !== 'submitted' || !res.task_id) {
        setData({ status: 'error', detail: res.detail || '提交失败' });
        setLoading(false);
        return;
      }
      setTaskId(res.task_id);
      // 轮询进度
      pollRef.current = setInterval(async () => {
        try {
          const t = await getCalibrationTask(res.task_id!);
          setProgress(t.progress ?? 0);
          setProgressMsg(t.message || '');
          if (t.status === 'completed' && t.result) {
            clearPoll();
            // 后端 result 无 status/meta 字段，补上满足渲染判断
            setData({ ...t.result, status: 'success', meta: t.meta });
            setLoading(false);
            void loadHistory();
          } else if (t.status === 'failed' || t.status === 'error') {
            clearPoll();
            setData({ status: 'error', detail: t.error || t.detail || '校准失败' });
            setLoading(false);
          } else if (t.status === 'not_found') {
            clearPoll();
            setData({ status: 'error', detail: '任务不存在' });
            setLoading(false);
          }
        } catch (err: any) {
          // 轮询失败暂时忽略，下次再试
          console.error('[ScoreCalibration] poll failed:', err);
        }
      }, 2000);
    } catch (err: any) {
      setData({ status: 'error', detail: err?.message || '加载失败' });
      setLoading(false);
    }
  }, [days, horizons, clearPoll]);

  useEffect(() => {
    return () => clearPoll();
  }, [clearPoll]);

  useEffect(() => {
    void load();
    void loadHistory();
    return () => clearPoll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summaryColumns = [
    {
      title: '分数档',
      dataIndex: 'score_band',
      width: 110,
      render: (v: string) => <Text className="font-black" style={{ color: bandColor(v) }}>{v}</Text>,
    },
    {
      title: '样本',
      dataIndex: 'n',
      width: 70,
      render: (v: number) => <Text className="font-mono text-[10px]">{v.toLocaleString()}</Text>,
    },
    {
      title: 'Top50内',
      dataIndex: 'top50_count',
      width: 70,
      render: (v: number) => <Text className="font-mono text-[10px]">{v}</Text>,
    },
    {
      title: '平均排名',
      dataIndex: 'avg_rank',
      width: 80,
      render: (v: number) => <Text className="font-mono text-[10px] text-slate-500">{v.toLocaleString()}</Text>,
    },
    ...([1, 3, 5, 10].filter(h => horizons.split(',').includes(String(h))).map(h => ({
      title: `T+${h} 下跌`,
      key: `down_${h}`,
      width: 76,
      render: (_: unknown, r: ScoreCalibrationResponse['score_summary'] extends (infer T)[] ? T : never) => {
        const hs = (r?.horizons || []).find(x => x.horizon === h);
        if (!hs) return <Text className="text-[10px] text-slate-300">—</Text>;
        return (
          <Text className="font-mono text-[10px]" style={{ color: numColor(hs.down_prob > 50 ? -1 : 1) }}>
            {hs.down_prob.toFixed(1)}%
          </Text>
        );
      },
    }))),
    ...([1, 3, 5, 10].filter(h => horizons.split(',').includes(String(h))).map(h => ({
      title: `T+${h} 均收`,
      key: `ret_${h}`,
      width: 76,
      render: (_: unknown, r: ScoreCalibrationResponse['score_summary'] extends (infer T)[] ? T : never) => {
        const hs = (r?.horizons || []).find(x => x.horizon === h);
        if (!hs) return <Text className="text-[10px] text-slate-300">—</Text>;
        return (
          <Text className="font-mono text-[10px]" style={{ color: numColor(hs.avg_ret) }}>
            {hs.avg_ret > 0 ? '+' : ''}{hs.avg_ret.toFixed(2)}%
          </Text>
        );
      },
    }))),
  ];

  const matrixColumns = [
    { title: '分数档', dataIndex: 'score_band', width: 110, fixed: 'left' as const,
      render: (v: string) => <Text className="font-black" style={{ color: bandColor(v) }}>{v}</Text> },
    ...(['微盘', '小盘', '中盘', '大盘', '超大盘'].map(cap => ({
      title: cap,
      key: cap,
      render: (_: unknown, r: ScoreCalibrationResponse['matrix'] extends (infer T)[] ? T : never) => {
        const cell = (r?.caps || []).find(c => c.cap === cap);
        if (!cell || cell.n === 0) return <Text className="text-[10px] text-slate-300">—</Text>;
        return (
          <div className="text-[9px]">
            <div className="font-mono" style={{ color: numColor(cell.avg_ret) }}>
              {cell.avg_ret > 0 ? '+' : ''}{cell.avg_ret?.toFixed(2)}%
            </div>
            <div className="font-mono text-slate-400">跌{cell.down_prob?.toFixed(0)}%</div>
          </div>
        );
      },
    }))),
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Select value={days} onChange={setDays} style={{ width: 120 }} className="!text-xs" options={[
          { value: 60, label: '60 交易日' },
          { value: 120, label: '120 交易日' },
          { value: 180, label: '180 交易日' },
          { value: 365, label: '365 交易日' },
        ]} />
        <Select value={horizons} onChange={setHorizons} style={{ width: 140 }} className="!text-xs" options={[
          { value: '1,3,5,10', label: 'T+1/3/5/10' },
          { value: '1,5,20', label: 'T+1/5/20' },
          { value: '5', label: '仅 T+5' },
          { value: '1,3,5,10,20', label: 'T+1~T+20' },
        ]} />
        <Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}
          className="rounded-lg text-[10px] font-bold h-8 px-3">
          {loading ? '校准中...' : '重新校准'}
        </Button>
        {data?.meta && (
          <Tag className="border-0 bg-blue-50 text-blue-600 text-[9px] font-bold">
            {data.meta.backtest_days}天 / {data.meta.total_samples.toLocaleString()}样本 / 最新{data.meta.latest_trade_date}
          </Tag>
        )}
        {data?.recommended_band && (
          <Tag className="border-0 bg-emerald-50 text-emerald-600 text-[9px] font-bold">
            推荐档 {data.recommended_band.score_band}（T+5均收 {data.recommended_band.main_horizon_avg_ret}%）
          </Tag>
        )}
      </div>

      {loading && (
        <div className="rounded-2xl border border-blue-100 bg-blue-50/50 p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <Text className="text-[10px] font-black uppercase tracking-widest text-blue-600">
              模型分数校准中...
            </Text>
            <Text className="text-[10px] font-mono text-blue-500">{progress}%</Text>
          </div>
          <Progress percent={progress} size="small" status="active" strokeColor="#3b82f6" />
          <Text className="text-[10px] text-slate-500 mt-1 block">{progressMsg || '计算中，请稍候'}</Text>
        </div>
      )}

      <Spin spinning={loading}>
        {!data || data.status !== 'success' ? (
          <Empty description={data?.detail || '暂无分数校准数据'} className="py-16" />
        ) : (
          <div className="space-y-4">
            {data.score_summary && data.score_summary.length > 0 && (
              <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                  分数档 × 多周期收益
                </div>
                <Table
                  dataSource={data.score_summary}
                  columns={summaryColumns as any}
                  size="small"
                  pagination={false}
                  scroll={{ x: 900 }}
                  rowKey="score_band"
                />
              </div>
            )}

            {data.matrix && data.matrix.length > 0 && (
              <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                  分数档 × 市值 × 下跌概率（主周期 T+{data.meta?.main_horizon ?? 5}）
                </div>
                <Table
                  dataSource={data.matrix}
                  columns={matrixColumns as any}
                  size="small"
                  pagination={false}
                  scroll={{ x: 600 }}
                  rowKey="score_band"
                />
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {data.neg_industry_avg && data.neg_industry_avg.length > 0 && (
                <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                  <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                    负分行业 avg（最新日）
                  </div>
                  <div className="space-y-1">
                    {data.neg_industry_avg.map(r => (
                      <div key={r.industry} className="flex items-center justify-between text-[10px]">
                        <span className="font-bold text-slate-600">{r.industry}</span>
                        <span className="font-mono" style={{ color: numColor(r.neg_avg) }}>
                          {r.neg_avg.toFixed(3)}（{r.neg_count}只 / 最深{r.neg_min.toFixed(3)}）
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {data.neg_board_avg && data.neg_board_avg.length > 0 && (
                <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                  <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                    板块负分 avg（最新日）
                  </div>
                  <div className="space-y-1">
                    {data.neg_board_avg.map(r => (
                      <div key={r.board} className="flex items-center justify-between text-[10px]">
                        <span className="font-bold text-slate-600">{r.board}</span>
                        <span className="font-mono" style={{ color: numColor(r.neg_avg) }}>
                          {r.neg_avg.toFixed(3)}（{r.neg_count}只）
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {data.warnings && data.warnings.length > 0 && (
              <Alert type="warning" message={data.warnings.join('；')} className="!text-[10px]" />
            )}
          </div>
        )}
      </Spin>

      {/* 校准历史 */}
      {history.length > 0 && (
        <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
          <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
            校准历史（{history.length} 次）
          </div>
          <div className="space-y-1">
            {history.map(h => (
              <div key={h.task_id} className="flex items-center justify-between text-[10px] py-1 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2 min-w-0">
                  <Tag className="m-0 border-0 text-[9px] font-bold"
                    color={h.status === 'completed' ? 'green' : h.status === 'failed' ? 'red' : 'processing'}>
                    {h.status === 'completed' ? '完成' : h.status === 'failed' ? '失败' : '进行中'}
                  </Tag>
                  <span className="font-mono text-slate-600 truncate">{h.task_id.slice(0, 20)}...</span>
                  <span className="text-slate-400">
                    {h.params?.days ?? '-'}天 / T{String(h.params?.horizons ?? '')} / 样本{h.total_samples?.toLocaleString() ?? '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {h.recommended_band && (
                    <Tag className="m-0 border-0 bg-emerald-50 text-emerald-600 text-[9px] font-bold">
                      推荐 {h.recommended_band}
                    </Tag>
                  )}
                  {h.latest_trade_date && (
                    <span className="text-slate-400 font-mono">{h.latest_trade_date}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
