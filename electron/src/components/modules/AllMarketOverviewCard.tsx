import React from 'react';
import { Card } from '../common/Card';
import { MarketOverviewSkeleton } from '../common/CardSkeletons';
import { useMarketData } from '../../hooks/useMarketData';
import { MARKET_INDICES, type MarketId } from '../../services/marketService';
import type { MarketIndex } from '../../services/marketService';

const MARKETS: { id: MarketId; label: string }[] = [
  { id: 'CN', label: 'A股' },
  { id: 'HK', label: '港股' },
  { id: 'US', label: '美股' },
  { id: 'CRYPTO', label: '区块链' },
  { id: 'FUTURES', label: '期货' },
];

const MarketMiniPanel: React.FC<{ market: MarketId; label: string }> = ({ market, label }) => {
  const { data, loading } = useMarketData({ market });

  const fallbackData: Partial<MarketIndex>[] = (MARKET_INDICES[market] || MARKET_INDICES.CN).map(
    ({ name, basePrice }) => ({ name, price: basePrice, change: 0, changePercent: 0 })
  );

  if (loading) {
    return (
      <div className="flex-1 min-w-0 p-3">
        <div className="text-xs font-bold text-slate-400 mb-2">{label}</div>
        <MarketOverviewSkeleton />
      </div>
    );
  }

  const displayData = data?.indices || fallbackData;

  return (
    <div className="flex-1 min-w-0 p-3">
      <div className="text-xs font-bold text-slate-500 mb-2 tracking-wide">{label}</div>
      <div className="space-y-1.5">
        {displayData.slice(0, 6).map((item, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between px-2 py-1 rounded-md bg-slate-50/70 border border-slate-100/60"
          >
            <span className="text-xs font-medium text-slate-600 truncate min-w-0 mr-1 flex-shrink-0" style={{ maxWidth: '5em' }}>
              {item.name}
            </span>
            <span
              className={`text-xs font-bold font-mono flex-shrink-0 ${
                (item.changePercent ?? 0) > 0
                  ? 'text-[var(--profit-primary)]'
                  : (item.changePercent ?? 0) < 0
                    ? 'text-[var(--loss-primary)]'
                    : 'text-slate-500'
              }`}
            >
              {(item.changePercent ?? 0) > 0 ? '+' : ''}{(item.changePercent ?? 0).toFixed(2)}% ({(item.change ?? 0) > 0 ? '+' : ''}{(item.change ?? 0).toFixed(2)})
            </span>
            <span className="text-xs font-bold text-slate-700 min-w-[4.5em] text-right font-mono flex-shrink-0">
              {(item.price ?? 0).toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const AllMarketOverviewCard: React.FC = () => {
  return (
    <Card title="大盘概览" height="100%" background="market">
      <div className="flex gap-0 divide-x divide-slate-100 h-full py-1">
        {MARKETS.map(({ id, label }) => (
          <MarketMiniPanel key={id} market={id} label={label} />
        ))}
      </div>
    </Card>
  );
};
