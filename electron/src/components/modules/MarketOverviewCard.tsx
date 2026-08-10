import React from 'react';
import { Card } from '../common/Card';
import { MarketOverviewSkeleton } from '../common/CardSkeletons';
import { useMarketData } from '../../hooks/useMarketData';
import { useAppSelector } from '../../store';
import { selectCurrentMarket } from '../../store/slices/uiSlice';
import { MARKET_INDICES, type MarketId } from '../../services/marketService';
import type { MarketIndex } from '../../services/marketService';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const MARKET_LABELS: Record<MarketId, string> = {
  CN: 'A股',
  HK: '港股',
  US: '美股',
  CRYPTO: '区块链',
  FUTURES: '期货',
};

export const MarketOverviewCard: React.FC = () => {
  const currentMarket = useAppSelector(selectCurrentMarket);
  const { data, loading, error } = useMarketData({ market: currentMarket });

  // 市场默认数据
  const fallbackData: Partial<MarketIndex>[] = (MARKET_INDICES[currentMarket] || MARKET_INDICES.CN).map(
    ({ name, basePrice }) => ({ name, price: basePrice, change: 0, changePercent: 0 })
  );

  if (loading) {
    return <MarketOverviewSkeleton />;
  }

  if (error) {
    console.error('获取市场数据出错:', error);
  }

  const displayData = (data?.indices || fallbackData) as MarketIndex[];
  const stats = data?.stats;
  const upCount = stats?.up ?? displayData.filter((x) => (x.changePercent ?? 0) > 0).length;
  const downCount = stats?.down ?? displayData.filter((x) => (x.changePercent ?? 0) < 0).length;
  const flatCount = stats?.flat ?? displayData.filter((x) => (x.changePercent ?? 0) === 0).length;
  const trend = upCount >= downCount ? (upCount === downCount ? 'flat' : 'up') : 'down';
  const lastUpdate = data?.lastUpdate ? String(data.lastUpdate).slice(0, 10) : '';
  const isRealData = Boolean(data?.sourceUsed) || (data?.indices && data.indices.length > 0 && data.indices.some((x) => x.change !== 0));

  return (
    <Card title={`${MARKET_LABELS[currentMarket]}概览`} height="100%" background="market">
      <div className="flex flex-col h-full py-1 gap-2">
        {/* 市场状态横幅 */}
        <div className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
          trend === 'up'
            ? 'bg-red-50 border-red-100'
            : trend === 'down'
              ? 'bg-emerald-50 border-emerald-100'
              : 'bg-slate-50 border-slate-100'
        }`}>
          <div className="flex items-center gap-2">
            {trend === 'up' ? (
              <TrendingUp size={16} className="text-[var(--profit-primary)]" />
            ) : trend === 'down' ? (
              <TrendingDown size={16} className="text-[var(--loss-primary)]" />
            ) : (
              <Minus size={16} className="text-slate-400" />
            )}
            <span className={`text-xs font-bold ${
              trend === 'up' ? 'text-[var(--profit-primary)]' : trend === 'down' ? 'text-[var(--loss-primary)]' : 'text-slate-500'
            }`}>
              {trend === 'up' ? '市场偏强' : trend === 'down' ? '市场偏弱' : '市场震荡'}
            </span>
          </div>
          <div className="flex items-center gap-3 text-[10px] font-semibold">
            <span className="text-[var(--profit-primary)]">↑ {upCount}</span>
            <span className="text-[var(--loss-primary)]">↓ {downCount}</span>
            <span className="text-slate-400">- {flatCount}</span>
            {lastUpdate && <span className="text-slate-400 ml-1">{lastUpdate}</span>}
          </div>
        </div>

        {/* 市场数据项 - 优化布局 */}
        {displayData.slice(0, 6).map((item, index) => {
          const pct = item.changePercent ?? 0;
          const isUp = pct > 0;
          const isDown = pct < 0;
          // 迷你涨跌柱：按涨跌幅比例缩放（最大 ±5%）
          const barWidth = Math.min(Math.abs(pct) / 5 * 100, 100);
          return (
            <div
              key={index}
              className="
                flex items-center justify-between px-3 py-2 rounded-lg
                bg-slate-50 border border-slate-100/80
                transition-all duration-200 hover:bg-slate-100 hover:shadow-sm
              "
            >
              {/* 股票名称 */}
              <div className="text-sm font-bold text-slate-700 min-w-[70px]">
                {item.name}
              </div>

              {/* 迷你涨跌柱 */}
              <div className="flex-1 flex items-center gap-1.5 mx-2">
                <div className="h-1.5 flex-1 rounded-full bg-slate-200/70 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${isUp ? 'bg-[var(--profit-primary)]' : isDown ? 'bg-[var(--loss-primary)]' : 'bg-slate-400'}`}
                    style={{ width: isUp || isDown ? `${barWidth}%` : '0%' }}
                  />
                </div>
                <span className={`text-[10px] font-mono font-bold w-[52px] text-right ${
                  isUp ? 'text-[var(--profit-primary)]' : isDown ? 'text-[var(--loss-primary)]' : 'text-slate-500'
                }`}>
                  {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
                </span>
              </div>

              {/* 价格 + 成交额 */}
              <div className="text-right min-w-[90px]">
                <div className="text-sm font-black text-slate-800 font-mono">
                  {item.price?.toFixed(item.price && item.price < 10 ? 3 : 2)}
                </div>
                {item.amount ? (
                  <div className="text-[9px] text-slate-400 font-mono mt-0.5">
                    {formatAmount(item.amount)}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}

        {/* 数据源标识 */}
        <div className="text-[9px] text-slate-300 text-right px-1 mt-auto">
          {isRealData ? `数据截至 ${lastUpdate}` : '实时行情'} · {data?.sourceUsed === 'local_parquet' ? '本地数据' : '实时数据'}
        </div>
      </div>
    </Card>
  );
};

// 格式化大额成交额（万/亿/万亿）
function formatAmount(amount: number): string {
  const abs = Math.abs(amount);
  if (abs >= 1e12) return `${(amount / 1e12).toFixed(2)}万亿`;
  if (abs >= 1e8) return `${(amount / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) return `${(amount / 1e4).toFixed(1)}万`;
  return amount.toFixed(0);
}
