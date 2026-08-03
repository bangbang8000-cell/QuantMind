import React from 'react';
import { Empty, Input, Segmented, Tag } from 'antd';
import { Search } from 'lucide-react';
import type { QuantDbFeatureCategory, QuantDbFeatures, QuantDbFeatureValues } from '../types';

/** 类别 → 中文标签。顺序即 Tab 顺序。 */
const CATEGORY_LABELS: Array<{ key: QuantDbFeatureCategory; label: string }> = [
  { key: 'valuation', label: '估值' },
  { key: 'technical', label: '技术' },
  { key: 'momentum', label: '动量' },
  { key: 'volatility', label: '波动' },
  { key: 'liquidity', label: '流动性' },
  { key: 'fundFlow', label: '资金流' },
  { key: 'fundamental', label: '基本面' },
  { key: 'style', label: '风格' },
  { key: 'industry', label: '行业' },
  { key: 'chip', label: '筹码' },
  { key: 'concept', label: '概念' },
  { key: 'sentiment', label: '情绪' },
  { key: 'microstructure', label: '微观结构' },
  { key: 'other', label: '其他' },
];

/** 常见因子名的中文释义，未收录的回落到原始列名。 */
const FIELD_LABELS: Record<string, string> = {
  pe_ttm: 'PE(TTM)',
  pe_static: 'PE(静态)',
  pb: 'PB',
  ps_ttm: 'PS(TTM)',
  total_mv: '总市值',
  float_mv: '流通市值',
  dividend_rate: '股息率',
  net_profit_ttm: '净利润(TTM)',
  revenue_ttm: '营收(TTM)',
  mom_ret_1d: '1日动量',
  mom_ret_5d: '5日动量',
  mom_ret_20d: '20日动量',
  mom_ret_60d: '60日动量',
  mom_ret_120d: '120日动量',
  vol_std_20: '20日波动率',
  vol_atr_14: 'ATR(14)',
  vol_skew: '波动偏度',
  vol_up_down_ratio: '涨跌波动比',
  liq_mfi_14: 'MFI(14)',
  liq_obv_20: 'OBV(20)',
  flow_net_amount: '净流入额',
  flow_large_net: '大单净额',
  flow_net_ratio: '净流入占比',
  style_beta_20: 'Beta(20)',
  style_idio_vol_20: '特质波动(20)',
  ind_strength_20: '行业强度(20)',
  ind_crowding_20: '行业拥挤度',
  chip_profit_ratio_20: '获利盘(20)',
  chip_concentration_20: '筹码集中度',
  concept_hot_score: '概念热度',
  micro_vpin_20: 'VPIN(20)',
  micro_kyle_lambda: 'Kyle Lambda',
  micro_amihud_illiquidity: 'Amihud 非流动性',
  buy_pressure: '买压',
  sell_pressure: '卖压',
  liquidity_score: '流动性评分',
};

/** 数值格式化：按量级自适应，极小值用科学计数法，大额转亿。 */
const formatValue = (value: number | string | boolean | null): string => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'string') return value || '-';
  if (!Number.isFinite(value)) return '-';

  const abs = Math.abs(value);
  if (abs === 0) return '0';
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  if (abs < 1e-4) return value.toExponential(2);
  if (abs < 1) return value.toFixed(4);
  if (abs < 100) return value.toFixed(3);
  return value.toFixed(2);
};

const valueTone = (value: number | string | boolean | null): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'text-slate-800';
  if (value > 0) return 'text-rose-500';
  if (value < 0) return 'text-emerald-600';
  return 'text-slate-800';
};

interface FactorPanelProps {
  features: QuantDbFeatures | null;
  loading?: boolean;
}

/**
 * QuantDB 全字段因子面板：按类别分 Tab 展示，支持字段名搜索。
 * 后端一次返回 300+ 字段，直接铺开无法阅读，因此分类 + 搜索是必需的。
 */
export const FactorPanel: React.FC<FactorPanelProps> = ({ features, loading }) => {
  const [activeCategory, setActiveCategory] = React.useState<string>('valuation');
  const [query, setQuery] = React.useState<string>('');

  // 只保留有数据的类别，避免空 Tab
  const availableCategories = React.useMemo(() => {
    if (!features) return [];
    return CATEGORY_LABELS.filter(({ key }) => {
      const values = features[key];
      return values && Object.keys(values).length > 0;
    });
  }, [features]);

  // 当前类别失效时回落到第一个可用类别
  React.useEffect(() => {
    if (!availableCategories.length) return;
    if (!availableCategories.some((c) => c.key === activeCategory)) {
      setActiveCategory(availableCategories[0].key);
    }
  }, [availableCategories, activeCategory]);

  const lowerQuery = query.trim().toLowerCase();

  // 有搜索词时跨类别检索，否则只看当前类别
  const entries = React.useMemo(() => {
    if (!features) return [];
    const collect = (key: QuantDbFeatureCategory): Array<[string, QuantDbFeatureValues[string], string]> => {
      const values = features[key];
      if (!values) return [];
      const label = CATEGORY_LABELS.find((c) => c.key === key)?.label || key;
      return Object.entries(values).map(([field, value]) => [field, value, label]);
    };

    const source = lowerQuery
      ? availableCategories.flatMap((c) => collect(c.key))
      : collect(activeCategory as QuantDbFeatureCategory);

    return source
      .filter(([field]) => {
        if (!lowerQuery) return true;
        const label = FIELD_LABELS[field] || '';
        return field.toLowerCase().includes(lowerQuery) || label.toLowerCase().includes(lowerQuery);
      })
      .sort((left, right) => left[0].localeCompare(right[0]));
  }, [features, activeCategory, lowerQuery, availableCategories]);

  if (loading) {
    return <div className="flex h-40 items-center justify-center text-xs text-slate-400">因子数据加载中...</div>;
  }

  if (!features || !availableCategories.length) {
    return <Empty description="暂无 QuantDB 因子数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const totalFields = availableCategories.reduce(
    (sum, c) => sum + Object.keys(features[c.key] || {}).length,
    0
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-black uppercase tracking-widest text-slate-500">全量因子</span>
          <Tag className="rounded-lg border-none bg-slate-100 text-[10px] font-bold text-slate-500">
            {totalFields} 字段
          </Tag>
          {features.tradeDate && (
            <span className="text-[10px] font-bold text-slate-400">{features.tradeDate}</span>
          )}
        </div>
        <Input
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索因子（跨类别）"
          prefix={<Search className="h-3.5 w-3.5 text-slate-400" />}
          className="h-8 w-56 rounded-xl border-slate-200 text-xs font-medium"
        />
      </div>

      {!lowerQuery && (
        <div className="custom-scrollbar overflow-x-auto pb-1">
          <Segmented
            size="small"
            value={activeCategory}
            onChange={(value) => setActiveCategory(String(value))}
            options={availableCategories.map(({ key, label }) => ({
              label: `${label} (${Object.keys(features[key] || {}).length})`,
              value: key,
            }))}
            className="research-next-segmented rounded-xl bg-slate-100 p-1"
          />
        </div>
      )}

      {entries.length === 0 ? (
        <Empty description="无匹配因子" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="custom-scrollbar grid max-h-[320px] grid-cols-2 gap-2 overflow-y-auto pr-1 md:grid-cols-3 lg:grid-cols-4">
          {entries.map(([field, value, categoryLabel]) => (
            <div
              key={`${categoryLabel}-${field}`}
              className="rounded-xl border border-slate-100 bg-slate-50/70 p-2.5"
              title={field}
            >
              <div className="truncate text-[9px] font-bold text-slate-400">
                {FIELD_LABELS[field] || field}
              </div>
              <div className={`mt-1 truncate text-xs font-black ${valueTone(value)}`}>
                {formatValue(value)}
              </div>
              {lowerQuery && (
                <div className="mt-0.5 text-[8px] font-bold uppercase text-slate-300">{categoryLabel}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
