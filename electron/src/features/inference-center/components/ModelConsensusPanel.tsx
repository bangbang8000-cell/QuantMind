import React from 'react';
import { ModelConsensusItem } from '../../../services/inferenceCenterService';
import { Layers, ShieldCheck, CheckCircle2, TrendingUp } from 'lucide-react';

interface ModelConsensusPanelProps {
  consensus: ModelConsensusItem[];
  consensusScore: number;
}

export const ModelConsensusPanel: React.FC<ModelConsensusPanelProps> = ({
  consensus,
  consensusScore,
}) => {
  const getRatingBadge = (rating: string) => {
    switch (rating) {
      case 'STRONG_BUY':
        return <span className="text-[10px] font-black text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-md">强烈看多</span>;
      case 'BUY':
        return <span className="text-[10px] font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded-md">偏多</span>;
      case 'HOLD':
        return <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">观望</span>;
      case 'SELL':
        return <span className="text-[10px] font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-md">看空</span>;
      default:
        return <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{rating}</span>;
    }
  };

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/80 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-800 m-0">多模型横向共识矩阵 (Consensus Grid)</h4>
            <p className="text-[11px] text-slate-400 m-0">异构多模型对同一标的的综合预测研判</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-100 px-3 py-1 rounded-xl">
          <span className="text-[11px] text-slate-500 font-semibold">综合共识得分:</span>
          <span className="text-sm font-black font-mono text-blue-600">{consensusScore.toFixed(1)}/100</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 flex-1 min-h-0 overflow-y-auto">
        {consensus.map((item, idx) => (
          <div
            key={item.model_id || idx}
            className="flex flex-col justify-between p-3 rounded-xl bg-white border border-slate-100 shadow-xs hover:shadow-sm transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 min-w-0 pr-2">
                <div className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="text-xs font-bold text-slate-800 truncate">{item.model_name}</span>
              </div>
              {getRatingBadge(item.rating)}
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-50">
              <span className="text-[11px] text-slate-400 font-medium">预期 T+{item.horizon} 回报</span>
              <span className={`text-xs font-black font-mono ${item.expected_return >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                {item.expected_return >= 0 ? `+${item.expected_return.toFixed(2)}%` : `${item.expected_return.toFixed(2)}%`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
