import React from 'react';
import { ShieldAlert, ShieldCheck, AlertTriangle, Ban } from 'lucide-react';
import type { RiskScoreData, RiskDimensionKey } from '../../services/researchService';

interface RiskScoreCardProps {
  data: RiskScoreData | null;
  loading?: boolean;
  /** 用户请求的评分基准日（如推理批次日）。传入后用于跟实际 snapshot 日比较。*/
  requestedDate?: string | null;
}

// 维度展示元信息（顺序 = 显示顺序）— v2 包含 6 个维度
const DIM_META: Array<{ key: RiskDimensionKey; label: string; hint: string }> = [
  { key: 'liquidity',   label: '流动性',     hint: '20日成交额、流通市值、换手率' },
  { key: 'volatility',  label: '波动率+量能', hint: 'ATR、异动、波动扩张、量价配合' },
  { key: 'trend',       label: '趋势',       hint: '跌破均线、空头排列、MACD' },
  { key: 'overheat',    label: '过热',       hint: '短期暴涨、RSI/KDJ 超买共振' },
  { key: 'fundamental', label: '基本面',     hint: 'ROE / PB / PE' },
  { key: 'status',      label: '状态',       hint: '连板涨停' },
];

// 评分 → 颜色（同 risk_level 分桶）
function levelStyle(score: number): { bg: string; text: string; border: string; label: string } {
  if (score >= 80) return { bg: 'bg-rose-50',    text: 'text-rose-700',    border: 'border-rose-200',    label: '极高风险' };
  if (score >= 60) return { bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-200',  label: '高风险' };
  if (score >= 40) return { bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',   label: '中等风险' };
  if (score >= 20) return { bg: 'bg-sky-50',     text: 'text-sky-700',     border: 'border-sky-200',     label: '低风险' };
  return                  { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: '极低风险' };
}

// 维度小条颜色随 score 走
function barColor(score: number): string {
  if (score >= 80) return 'bg-rose-500';
  if (score >= 60) return 'bg-orange-500';
  if (score >= 40) return 'bg-amber-500';
  if (score >= 20) return 'bg-sky-500';
  return 'bg-emerald-500';
}

export const RiskScoreCard: React.FC<RiskScoreCardProps> = ({ data, loading, requestedDate }) => {
  if (loading) {
    return (
      <div className="p-5 border border-slate-100 rounded-3xl bg-white shadow-sm mt-3">
        <div className="flex h-[140px] items-center justify-center text-slate-400">风险评分加载中…</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-5 border border-slate-100 rounded-3xl bg-white shadow-sm mt-3">
        <div className="flex h-[140px] items-center justify-center text-slate-400 text-xs">暂无风险评分数据</div>
      </div>
    );
  }

  const style = levelStyle(data.risk_score);
  const Icon = data.veto ? Ban : (data.risk_score >= 60 ? ShieldAlert : ShieldCheck);

  return (
    <div className={`p-5 border rounded-3xl shadow-sm mt-3 ${style.border} ${style.bg}`}>
      {/* 标题区：总分 + 等级 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon className={`h-5 w-5 ${style.text}`} />
          <span className={`text-[11px] font-black uppercase tracking-widest ${style.text}`}>
            风险评分卡 v2
          </span>
          {data.trade_date && (
            <span className="text-[10px] text-slate-500">
              {requestedDate
                ? (requestedDate === data.trade_date
                    ? `推理基准 ${data.trade_date}`
                    : `推理基准 ${requestedDate} → 取最近交易日 ${data.trade_date}`)
                : `最新交易日 ${data.trade_date}`}
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-2">
          <span className={`text-3xl font-black ${style.text}`}>{data.risk_score.toFixed(1)}</span>
          <span className="text-xs text-slate-500">/ 100</span>
          <span className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${style.bg} ${style.text} border ${style.border}`}>
            {style.label}
          </span>
        </div>
      </div>

      {/* 一票否决提示 */}
      {data.veto && data.veto_reasons.length > 0 && (
        <div className="mb-4 px-3 py-2 rounded-xl border border-rose-300 bg-rose-100 text-rose-800 text-xs">
          <div className="flex items-center gap-1 font-bold mb-1">
            <Ban className="h-3.5 w-3.5" /> 一票否决（不建议持仓）
          </div>
          <ul className="list-disc pl-5 space-y-0.5">
            {data.veto_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* 维度条 */}
      <div className="space-y-2">
        {DIM_META.map(({ key, label, hint }) => {
          const d = data.dimensions[key];
          if (!d) return null;
          const w = data.weights[key] ?? 0;
          return (
            <div key={key} className="grid grid-cols-12 items-center gap-2 text-[11px]">
              <div className="col-span-3 flex flex-col">
                <span className="font-bold text-slate-700">{label}</span>
                <span className="text-[9px] text-slate-400">{hint} · 权重 {(w * 100).toFixed(0)}%</span>
              </div>
              <div className="col-span-7">
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${barColor(d.score)} transition-all`}
                    style={{ width: `${Math.min(100, d.score)}%` }}
                  />
                </div>
                {d.reasons.length > 0 && (
                  <div className="mt-1 text-[10px] text-slate-500 leading-tight truncate" title={d.reasons.join('；')}>
                    {d.reasons.join('；')}
                  </div>
                )}
              </div>
              <div className="col-span-2 text-right font-bold text-slate-700">
                {d.score.toFixed(0)}
              </div>
            </div>
          );
        })}
      </div>

      {/* 非否决但高风险的额外提示 */}
      {!data.veto && data.risk_score >= 60 && (
        <div className="mt-4 px-3 py-2 rounded-xl border border-orange-200 bg-orange-50 text-orange-700 text-[11px] flex items-start gap-2">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          <span>综合风险偏高，建议降低仓位或避开。模型预期收益需远超平均水平才值得介入。</span>
        </div>
      )}
    </div>
  );
};

export default RiskScoreCard;
