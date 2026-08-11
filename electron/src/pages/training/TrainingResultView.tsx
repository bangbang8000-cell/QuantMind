import React from 'react';
import { Card, Divider, Alert, Descriptions, Tag, Space, Typography, Empty, Button } from 'antd';
import { BarChart, MonitorPlay, Activity } from 'lucide-react';
import { 
  BarChart as ReBarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer, 
  ReferenceLine, 
  Cell 
} from 'recharts';
import dayjs from 'dayjs';
import { clsx } from 'clsx';
import { 
  TrainingResult, 
  TrainingRequestPayload,
  getObjectiveMetricDescription,
  getTargetModeDescription,
} from './trainingUtils';

const { Text } = Typography;

const MARKET_LABELS: Record<string, string> = {
  CN: 'A股',
  HK: '港股',
  US: '美股',
  CRYPTO: '区块链',
  FUTURES: '期货',
};

interface TrainingResultViewProps {
  result: TrainingResult | null;
  resultError: string;
  settingDefaultModel: boolean;
  onSetDefaultModel: () => void;
  trainingStatus: string;
}

const MetricCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  centered?: boolean;
  valueClassName?: string;
  hintClassName?: string;
}> = ({ label, value, hint, centered = false, valueClassName, hintClassName }) => (
  <div className={clsx('rounded-2xl border border-slate-200 bg-white p-4 shadow-sm', centered && 'text-center')}>
    <div className={clsx('text-[10px] font-black uppercase tracking-[0.18em] text-slate-400', centered && 'text-center')}>{label}</div>
    <div className={clsx('mt-2 text-lg font-semibold text-slate-900', centered && 'text-center', valueClassName)}>{value}</div>
    {hint ? <div className={clsx('mt-1 text-xs text-slate-500', centered && 'text-center', hintClassName)}>{hint}</div> : null}
  </div>
);

const SectionHeader: React.FC<{ title: string; desc: string; icon?: React.ReactNode }> = ({ title, desc, icon }) => (
  <div className="flex items-start justify-between gap-4">
    <div>
      <div className="flex items-center gap-2">
        {icon}
        <Typography.Title level={4} className="!mb-0 !text-slate-900">
          {title}
        </Typography.Title>
      </div>
      <Typography.Paragraph className="!mb-0 !mt-2 !text-xs !text-slate-500 leading-relaxed">
        {desc}
      </Typography.Paragraph>
    </div>
  </div>
);

const renderMetaLabel = (zh: string, en: string): React.ReactNode => (
  <div className="flex flex-col items-start text-left leading-tight">
    <span className="text-slate-700">{zh}</span>
    <span className="mt-1 text-xs font-normal text-slate-500">{en}</span>
  </div>
);

/** WFA 诊断解读：基于 IC 均值/标准差/正窗占比/ICIR 组合判断，输出可读结论 */
const WfaInterpretation: React.FC<{ wfa: any }> = ({ wfa }) => {
  if (!wfa || !wfa.enabled) return null;
  const icMean = Number(wfa.ic_mean);
  const icStd = Number(wfa.ic_std);
  const positiveRate = Number(wfa.positive_rate);
  const icir = Number(wfa.overall_icir);
  const hasIcir = Number.isFinite(icir) && !Number.isNaN(icir);

  const checks: Array<{ label: string; ok: boolean; text: string }> = [];
  if (icMean >= 0.05) checks.push({ label: 'IC 强度', ok: true, text: `IC均值 ${icMean.toFixed(4)} ≥ 0.05，信号强度良好` });
  else if (icMean >= 0) checks.push({ label: 'IC 强度', ok: true, text: `IC均值 ${icMean.toFixed(4)} 为正，信号有效但偏弱（<0.05）` });
  else checks.push({ label: 'IC 强度', ok: false, text: `IC均值 ${icMean.toFixed(4)} 为负，信号方向可能反了` });

  if (icStd <= 0.02) checks.push({ label: 'IC 稳定性', ok: true, text: `标准差 ${icStd.toFixed(4)} ≤ 0.02，各窗口波动小` });
  else checks.push({ label: 'IC 稳定性', ok: false, text: `标准差 ${icStd.toFixed(4)} > 0.02，各窗口波动偏大` });

  if (positiveRate >= 0.75) checks.push({ label: '正窗占比', ok: true, text: `${Math.round(positiveRate * 100)}% 窗口 IC 为正，跨期一致性好` });
  else if (positiveRate >= 0.5) checks.push({ label: '正窗占比', ok: true, text: `${Math.round(positiveRate * 100)}% 窗口为正，存在少数走弱窗口` });
  else checks.push({ label: '正窗占比', ok: false, text: `仅 ${Math.round(positiveRate * 100)}% 窗口为正，多数窗口失效` });

  if (hasIcir) {
    if (Math.abs(icir) >= 0.3) checks.push({ label: 'ICIR', ok: true, text: `ICIR ${icir.toFixed(3)}，收益/波动比合理` });
    else checks.push({ label: 'ICIR', ok: false, text: `ICIR ${icir.toFixed(3)} < 0.3，信号相对波动偏弱` });
  }

  const okCount = checks.filter(c => c.ok).length;

  return (
    <div className="mt-3 rounded-xl bg-slate-50/70 border border-slate-100 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[9px] font-black uppercase tracking-wider text-slate-500">判断解读</div>
        <Text className={clsx('text-[9px] font-black', okCount === checks.length ? 'text-emerald-600' : okCount >= 2 ? 'text-amber-600' : 'text-rose-500')}>
          {okCount}/{checks.length} 项达标
        </Text>
      </div>
      <div className="space-y-1">
        {checks.map((c, i) => (
          <div key={i} className="flex items-start gap-1.5">
            <span className={clsx('mt-0.5 text-[8px] font-black', c.ok ? 'text-emerald-500' : 'text-rose-400')}>{c.ok ? '✓' : '✗'}</span>
            <Text className={clsx('text-[10px] leading-snug', c.ok ? 'text-slate-600' : 'text-rose-500/80')}>
              <span className="font-bold text-slate-500">{c.label}：</span>{c.text}
            </Text>
          </div>
        ))}
      </div>
      <Text className="block mt-2 text-[10px] text-slate-400 leading-relaxed">
        {okCount === checks.length
          ? '整体稳定可用，适合作为选股模型。'
          : okCount >= 2
            ? '多数维度达标，个别窗口波动可接受，建议关注 IC 表现最弱的区间。'
            : '多个维度未达标，建议调整特征/参数后重新训练，或考虑融合其他模型。'}
      </Text>
    </div>
  );
};

export const TrainingResultView: React.FC<TrainingResultViewProps> = ({
  result,
  resultError,
  settingDefaultModel,
  onSetDefaultModel,
  trainingStatus,
}) => {
  if (!result && !resultError) {
    return (
      <Card className="rounded-3xl border-slate-200 shadow-sm" styles={{ body: { padding: 20 } }}>
         <SectionHeader
          title="第五步：结果入库"
          desc="展示训练完成后会进入模型管理页的元数据与产物预览。"
          icon={<BarChart size={18} className="text-indigo-500" />}
        />
        <Divider className="my-4" />
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先执行训练，再查看结果摘要" />
      </Card>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <Card className="rounded-3xl border-slate-200 shadow-sm" styles={{ body: { padding: 20 } }}>
        <SectionHeader
          title="第五步：结果入库"
          desc="展示训练完成后会进入模型管理页的元数据与产物预览。"
          icon={<BarChart size={18} className="text-indigo-500" />}
        />
        <Divider className="my-4" />
        {resultError ? (
          <Alert type="error" showIcon className="mb-4 rounded-2xl" message="训练结果异常" description={resultError} />
        ) : null}
        {result ? (
          <div className="space-y-4">
            {result.metrics?.score_direction === 'reversed' && (
              <Alert
                type="warning"
                showIcon
                message="检测到反向模型"
                description="验证集 IC < 0，模型预测方向与实际收益相反（高分=跌，低分=涨）。推理时已自动翻转分数，但建议检查特征选择是否合理或重新训练。"
                className="rounded-2xl border-amber-100 bg-amber-50/70"
              />
            )}
            <Alert
              type="success"
              showIcon
              message={result.summary.status}
              description={result.summary.notes}
              className="rounded-2xl border-emerald-100 bg-emerald-50/70"
            />

            <Card className="rounded-2xl border-slate-200" size="small" title="模型注册与同步状态">
              <div className="flex flex-wrap items-center gap-3">
                <Tag
                  className={clsx(
                    'm-0 rounded-full border-0 px-3 py-1',
                    result.modelRegistration?.status === 'ready'
                      ? 'bg-emerald-50 text-emerald-600'
                      : result.modelRegistration?.status === 'failed'
                        ? 'bg-rose-50 text-rose-600'
                        : 'bg-amber-50 text-amber-600',
                  )}
                >
                  {result.modelRegistration?.status || 'unknown'}
                </Tag>
                {result.metadata.market ? (
                  <Tag className="m-0 rounded-full border-0 bg-blue-50 px-3 py-1 text-blue-600">
                    {MARKET_LABELS[result.metadata.market.toUpperCase()] || result.metadata.market}
                  </Tag>
                ) : null}
                <Text className="text-xs text-slate-600">
                  model_id: {result.modelRegistration?.modelId || result.modelId}
                </Text>
                <Button
                  size="small"
                  type="primary"
                  className="rounded-xl bg-blue-600"
                  loading={settingDefaultModel}
                  disabled={result.modelRegistration?.status !== 'ready'}
                  onClick={onSetDefaultModel}
                >
                  设为默认模型
                </Button>
              </div>
            </Card>

            <div className="grid gap-3 md:grid-cols-2">
              <MetricCard
                label="模型标识"
                value={result.modelId}
                hint={result.modelName}
                centered
                valueClassName="text-sm leading-tight break-all"
                hintClassName="text-[10px] leading-tight break-all"
              />
              <MetricCard
                label="T+N"
                value={`T+${result.metadata.target_horizon_days}`}
                hint={result.metadata.target_mode === 'classification' ? '分类目标' : '回归目标'}
                centered
              />
              <MetricCard
                label="提交特征数"
                value={`${result.metadata.requested_feature_count}`}
                hint={`${result.request.selectedFeatures.length} 个提交维度`}
                centered
              />
              <MetricCard
                label="实际入模特征数"
                value={`${result.metadata.feature_count}`}
                hint={result.metadata.feature_categories.join(' / ') || '—'}
                centered
              />
            </div>
            
            <Card className="rounded-2xl border-slate-200" size="small" title="模型元数据预览">
              <Descriptions size="small" bordered column={1}>
                <Descriptions.Item label={renderMetaLabel('展示名称', 'display_name')}>
                  <Text code className="text-[11px] break-all">{result.metadata.display_name}</Text>
                </Descriptions.Item>
                <Descriptions.Item label={renderMetaLabel('预测类型', 'target_mode')}>
                  {getTargetModeDescription(result.metadata.target_mode)}
                </Descriptions.Item>
                <Descriptions.Item label={renderMetaLabel('标签公式', 'label_formula')}>
                  <Text code className="text-[11px] break-all">{result.metadata.label_formula}</Text>
                </Descriptions.Item>
                <Descriptions.Item label={renderMetaLabel('时间窗口', 'training_window')}>
                  <Text code className="text-[11px] break-all">{result.metadata.training_window}</Text>
                </Descriptions.Item>
                <Descriptions.Item label={renderMetaLabel('目标函数', 'objective_metric')}>
                  {getObjectiveMetricDescription(result.metadata.objective, result.metadata.metric)}
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card className="rounded-2xl border-slate-200" size="small" title="建议落盘文件">
              <div className="flex flex-wrap gap-2">
                {result.artifacts.map((artifact) => (
                  <Tag key={artifact} className="m-0 rounded-full border-0 bg-indigo-50 px-3 py-1 text-indigo-600">
                    {artifact}
                  </Tag>
                ))}
              </div>
            </Card>
          </div>
        ) : null}
      </Card>

      <Card className="rounded-3xl border-slate-200 shadow-sm" styles={{ body: { padding: 20 } }}>
        <SectionHeader
          title="结果摘要"
          desc="给模型管理页与后续回放使用的最小信息集合。"
          icon={<MonitorPlay size={18} className="text-indigo-500" />}
        />
        <Divider className="my-4" />
        {result ? (
          <div className="space-y-4">
            <MetricCard label="结果状态" value={trainingStatus === 'completed' ? '已生成' : '等待完成'} hint={result.completedAt ? dayjs(result.completedAt).format('YYYY-MM-DD HH:mm:ss') : ''} />
            
            {result.metrics && (
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">IC 评估图表</div>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <ReBarChart
                    data={[
                      { name: '训练集', IC: result.metrics.train.ic, RankIC: result.metrics.train.rank_ic },
                      { name: '验证集', IC: result.metrics.val.ic, RankIC: result.metrics.val.rank_ic },
                      { name: '测试集', IC: result.metrics.test.ic, RankIC: result.metrics.test.rank_ic },
                    ]}
                    barCategoryGap="30%"
                    margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => v.toFixed(2)} />
                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <ReferenceLine y={0.05} stroke="#f59e0b" strokeDasharray="5 3" />
                    <ReferenceLine y={0.10} stroke="#10b981" strokeDasharray="5 3" />
                    <Bar dataKey="IC" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="RankIC" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                  </ReBarChart>
                </ResponsiveContainer>
                
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {(['train', 'val', 'test'] as const).map((split, i) => {
                    const labels = ['训练集', '验证集', '测试集'];
                    const seg = result.metrics![split];
                    const icVal = seg.ic;
                    const color = icVal >= 0.10 ? 'text-emerald-600' : icVal >= 0.05 ? 'text-amber-600' : 'text-rose-500';
                    return (
                      <div key={split} className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                        <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">{labels[i]}</div>
                        <div className={`mt-0.5 text-sm font-bold ${color}`}>{icVal.toFixed(4)}</div>
                        <div className="text-[9px] text-slate-400">RankIC {seg.rank_ic.toFixed(4)}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {result.wfa?.enabled && result.wfa.windows?.length > 0 && (
              <div className="rounded-2xl border border-violet-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity size={14} className="text-violet-500" />
                    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                      WFA 稳定性诊断
                    </div>
                  </div>
                  <Tag
                    className={clsx('m-0 rounded-full border-0 px-2.5 py-0.5', result.wfa.stability === 'stable' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600')}
                  >
                    {result.wfa.stability === 'stable' ? '稳定' : '不稳定'}
                  </Tag>
                </div>

                <div className="mb-4 grid grid-cols-2 gap-2">
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">IC 均值</div>
                    <div className={`mt-0.5 text-sm font-bold ${result.wfa.ic_mean >= 0.05 ? 'text-emerald-600' : result.wfa.ic_mean >= 0 ? 'text-amber-600' : 'text-rose-500'}`}>
                      {Number(result.wfa.ic_mean).toFixed(4)}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">IC 标准差</div>
                    <div className={`mt-0.5 text-sm font-bold ${result.wfa.ic_std <= 0.02 ? 'text-emerald-600' : 'text-amber-600'}`}>
                      {Number(result.wfa.ic_std).toFixed(4)}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">ICIR</div>
                    <div className={`mt-0.5 text-sm font-bold ${Number(result.wfa.overall_icir) >= 0.3 ? 'text-emerald-600' : 'text-slate-700'}`}>
                      {Number.isFinite(Number(result.wfa.overall_icir)) ? Number(result.wfa.overall_icir).toFixed(3) : '—'}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">正窗占比</div>
                    <div className="mt-0.5 text-sm font-bold text-slate-700">{Math.round(Number(result.wfa.positive_rate) * 100)}%</div>
                  </div>
                </div>

                <ResponsiveContainer width="100%" height={180}>
                  <ReBarChart
                    data={result.wfa.windows.map(w => ({
                      name: `W${w.window_idx + 1}`,
                      IC: Number(w.ic),
                      RankIC: Number(w.rank_ic),
                    }))}
                    barCategoryGap="25%"
                    margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => v.toFixed(2)} />
                    <Tooltip
                      contentStyle={{ borderRadius: 12, fontSize: 11 }}
                      formatter={(value: any, name: string, props: any) => {
                        const w = result.wfa?.windows?.[props?.payload?.payloadIndex ?? 0];
                        if (w && name === 'IC') {
                          return [`${Number(value).toFixed(4)}`, `${w.val_start} ~ ${w.val_end}`];
                        }
                        return [value, name];
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <ReferenceLine y={0} stroke="#cbd5e1" />
                    <Bar dataKey="IC" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="RankIC" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                  </ReBarChart>
                </ResponsiveContainer>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                  <span className="font-mono">{result.wfa.windows.length} 个窗口</span>
                  <span>·</span>
                  <span>{result.wfa.strategy === 'rolling' ? '滚动窗口' : '扩张窗口'}</span>
                  <span>·</span>
                  <span>模型: {result.wfa.model_type}</span>
                  <span>·</span>
                  <span>IC 区间 [{Number(result.wfa.ic_min).toFixed(4)}, {Number(result.wfa.ic_max).toFixed(4)}]</span>
                </div>

                {/* 判断解读 */}
                <WfaInterpretation wfa={result.wfa} />
              </div>
            )}

            {result.drift?.enabled && (
              <div className="rounded-2xl border border-sky-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity size={14} className="text-sky-500" />
                    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                      数据漂移检测 (PSI)
                    </div>
                  </div>
                  <Tag
                    className={clsx('m-0 rounded-full border-0 px-2.5 py-0.5', result.drift.overall === 'stable' ? 'bg-emerald-50 text-emerald-600' : result.drift.overall === 'warning' ? 'bg-amber-50 text-amber-600' : 'bg-rose-50 text-rose-600')}
                  >
                    {result.drift.overall === 'stable' ? '稳定' : result.drift.overall === 'warning' ? '预警' : '严重漂移'}
                  </Tag>
                </div>

                <div className="mb-3 grid grid-cols-2 gap-2">
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">最大 PSI</div>
                    <div className={`mt-0.5 text-sm font-bold ${Number(result.drift.max_psi) < 0.1 ? 'text-emerald-600' : Number(result.drift.max_psi) < 0.25 ? 'text-amber-600' : 'text-rose-500'}`}>
                      {Number(result.drift.max_psi).toFixed(4)}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">漂移特征</div>
                    <div className="mt-0.5 text-sm font-bold text-slate-700">
                      稳定 {result.drift.drift?.stable ?? 0} / 中 {result.drift.drift?.medium ?? 0} / 重 {result.drift.drift?.severe ?? 0}
                    </div>
                  </div>
                </div>

                {result.drift.top_drift_features?.length > 0 && (
                  <div className="space-y-1">
                    {result.drift.top_drift_features.slice(0, 8).map((f, i) => (
                      <div key={i} className="flex items-center gap-2 px-2 py-1 bg-slate-50/60 rounded-lg border border-slate-100/50">
                        <Text className="text-[9px] font-mono text-slate-500 flex-1 truncate">{f.feature}</Text>
                        {f.benign_scale && (
                          <Tag className="m-0 rounded-md border-0 px-1.5 py-0 text-[8px] font-black bg-sky-50 text-sky-500">量能</Tag>
                        )}
                        <Text className={`text-[10px] font-black font-mono ${f.level === 'stable' ? 'text-emerald-600' : f.level === 'medium' ? 'text-amber-600' : 'text-rose-500'}`}>
                          {Number(f.rank_disp ?? f.psi).toFixed(3)}
                        </Text>
                        <Tag className={`m-0 rounded-md border-0 px-1.5 py-0 text-[8px] font-black ${f.level === 'stable' ? 'bg-emerald-50 text-emerald-600' : f.level === 'medium' ? 'bg-amber-50 text-amber-600' : 'bg-rose-50 text-rose-600'}`}>
                          {f.level === 'stable' ? '稳定' : f.level === 'medium' ? '中' : '重'}
                        </Tag>
                      </div>
                    ))}
                  </div>
                )}

                <Text className="block mt-2 text-[10px] text-slate-400 leading-relaxed">
                  对比 {result.drift.train_start} ~ {result.drift.train_end}（训练）与 {result.drift.recent_start} ~ {result.drift.recent_end}（最近实盘）的截面结构。数值为个股截面 rank 位移（0~1），&gt;0.1 结构漂移，&gt;0.2 严重；标记"量能"的是水平膨胀但截面稳定的良性漂移。重训前请结合实盘 RankIC 判断。
                </Text>
              </div>
            )}

            {result.multiHorizon && result.multiHorizon.horizons?.length > 0 && (
              <div className="rounded-2xl border border-indigo-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity size={14} className="text-indigo-500" />
                    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                      多周期训练结果
                    </div>
                  </div>
                  <Tag className="m-0 rounded-full border-0 px-2.5 py-0.5 bg-indigo-50 text-indigo-600">
                    融合模型已创建
                  </Tag>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">训练周期</div>
                    <div className="mt-0.5 text-sm font-bold text-slate-700">
                      {result.multiHorizon.horizons.map((h) => `T+${h.replace('T', '')}`).join(' / ')}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-center">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">融合模型 ID</div>
                    <div className="mt-0.5 text-[11px] font-mono font-bold text-indigo-600 break-all">
                      {result.multiHorizon.fusion_model_id || '—'}
                    </div>
                  </div>
                </div>

                {result.multiHorizon.child_results?.length > 0 && (
                  <div className="space-y-1.5">
                    {result.multiHorizon.child_results.map((cr) => {
                      const m = cr.result?.metrics?.val || {};
                      return (
                        <div key={cr.run_id} className="flex items-center gap-2 px-2 py-1.5 bg-slate-50/60 rounded-lg border border-slate-100/50">
                          <Text className="text-[9px] font-black text-slate-500 font-mono w-10">T+{cr.target_horizon_days}</Text>
                          <Text className="text-[9px] font-mono text-slate-400 flex-1 truncate">{cr.run_id}</Text>
                          <Text className="text-[9px] text-slate-500 font-mono">
                            IC {Number(m.ic ?? '0').toFixed(4)} · ICIR {Number(m.rank_icir ?? '0').toFixed(3)}
                          </Text>
                        </div>
                      );
                    })}
                  </div>
                )}

                <Text className="block mt-2 text-[10px] text-slate-400 leading-relaxed">
                  已按各周期验证集 ICIR 加权创建融合模型，可在模型管理页查看源模型权重，并用融合模型进行推理/选股/回测。
                </Text>
              </div>
            )}

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">后续动作</div>
              <div className="mt-2 text-sm text-slate-700">
                1. 将 metadata.json 写入模型目录<br/>
                2. 在模型管理页展示 T+N / label_formula<br/>
                3. 将相同口径带入回测中心复用
              </div>
            </div>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="训练完成后，这里会展示元数据摘要" />
        )}
      </Card>
    </div>
  );
};
