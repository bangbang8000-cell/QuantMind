import React, { useState, useEffect } from 'react';
import { Sparkles, Search, Activity, Layers, Network, ArrowUpRight, TrendingUp, BarChart3, PieChart, Clock, Filter, ArrowRightLeft } from 'lucide-react';
import { Input, Spin } from 'antd';
import { BroadMarketHeader, IndexItem } from '../components/BroadMarketHeader';
import { ShenwanHeatmapChart } from '../components/ShenwanHeatmapChart';
import { CapitalFlowSankeyChart } from '../components/CapitalFlowSankeyChart';
import { StockMoneyFlowTable, StockMoneyFlowItem } from '../components/StockMoneyFlowTable';
import { MarketBreadthCard } from '../components/MarketBreadthCard';
import { TagLookupPanel } from '../components/TagLookupPanel';
import { CapitalFlowHorizontalBarChart, FlowItem } from '../components/CapitalFlowHorizontalBarChart';
import { Tag as TagIcon } from 'lucide-react';

// 兜底 Mock（仅在后端接口异常时使用；正常时绝不覆盖 QuantDB 真实数据）
const MOCK_INDICES: IndexItem[] = [
  { symbol: '000001.SH', name: '上证指数', price: 3048.52, change: 18.24, pct_change: 0.60, turnover: 4215.8, trend: [3020, 3032, 3028, 3040, 3048.52] },
  { symbol: '399001.SZ', name: '深证成指', price: 9482.16, change: 98.42, pct_change: 1.05, turnover: 5320.1, trend: [9380, 9410, 9400, 9450, 9482.16] },
  { symbol: '399006.SZ', name: '创业板指', price: 1860.30, change: 26.40, pct_change: 1.44, turnover: 2180.5, trend: [1830, 1842, 1838, 1855, 1860.30] },
  { symbol: '000300.SH', name: '沪深300', price: 3582.10, change: 24.18, pct_change: 0.68, turnover: 2890.3, trend: [3550, 3562, 3558, 3575, 3582.10] },
  { symbol: '588000.SH', name: '科创50', price: 812.45, change: 10.35, pct_change: 1.29, turnover: 890.2, trend: [800, 804, 802, 809, 812.45] },
];
const MOCK_STOCK_FLOWS: StockMoneyFlowItem[] = [
  { symbol: 'SH600036', name: '招商银行', close_price: 35.80, pct_change: 2.45, net_inflow: 482000000, main_ratio: 12.8, super_large: 280000000, large: 202000000, medium: -110000000, small: -372000000 },
  { symbol: 'SZ002594', name: '比亚迪', close_price: 248.50, pct_change: 3.12, net_inflow: 415000000, main_ratio: 15.4, super_large: 260000000, large: 155000000, medium: -80000000, small: -335000000 },
  { symbol: 'SH600519', name: '贵州茅台', close_price: 1680.00, pct_change: 1.15, net_inflow: 389000000, main_ratio: 9.2, super_large: 210000000, large: 179000000, medium: -95000000, small: -294000000 },
  { symbol: 'SH688330', name: '宏力达', close_price: 25.68, pct_change: 6.78, net_inflow: 128000000, main_ratio: 18.5, super_large: 82000000, large: 46000000, medium: -30000000, small: -98000000 },
  { symbol: 'SZ000001', name: '平安银行', close_price: 11.45, pct_change: 1.87, net_inflow: 96000000, main_ratio: 8.4, super_large: 54000000, large: 42000000, medium: -21000000, small: -75000000 },
];

/** YYYYMMDD → YYYY-MM-DD */
function formatTradeDate(d: string): string {
  if (/^\d{8}$/.test(d)) {
    return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  }
  return d;
}

export const MarketAnalysisPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [hasMock, setHasMock] = useState(false);
  const [activeTab, setActiveTab] = useState('panorama'); // 默认进入大盘全景看板
  const [searchQuery, setSearchQuery] = useState('');
  const [indices, setIndices] = useState<IndexItem[]>([]);
  const [stockFlows, setStockFlows] = useState<StockMoneyFlowItem[]>([]);

  // 🎯 多周期资金流向专属状态
  const [period, setPeriod] = useState<'1d' | '3d' | '5d' | '10d' | '20d'>('5d');
  const [flowDimension, setFlowDimension] = useState<'sector' | 'stock'>('sector');
  const [categoryMode, setCategoryMode] = useState<'shenwan' | 'concept'>('shenwan');
  const [chartViewMode, setChartViewMode] = useState<'bar' | 'treemap'>('bar');
  const [selectedFlowItem, setSelectedFlowItem] = useState<FlowItem | null>(null);

  useEffect(() => {
    fetchMarketData();
  }, []);

  const fetchMarketData = async () => {
    setLoading(true);
    try {
      const [resIdx, resStock] = await Promise.all([
        fetch('/api/v1/market-analysis/indices/overview', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}` },
        }),
        fetch('/api/v1/market-analysis/money-flow/stocks', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}` },
        }),
      ]);

      // 后端成功 → 用真实数据；仅 fetch 失败才落 Mock 兜底（不覆盖真数据）
      if (resIdx.ok) {
        const idxData = await resIdx.json();
        setIndices(idxData);
        setHasMock(false);
      } else {
        setIndices(MOCK_INDICES);
        setHasMock(true);
      }
      if (resStock.ok) {
        const stockData = await resStock.json();
        setStockFlows(stockData);
      }
    } catch (e) {
      console.warn('后端市场接口未完全就绪，使用全量真实感 Mock 数据');
      setIndices(MOCK_INDICES);
      setStockFlows(MOCK_STOCK_FLOWS);
      setHasMock(true);
    }

    setLoading(false);
  };

  const navTabs = [
    { id: 'panorama', label: '大盘全景看板', icon: Activity },
    { id: 'flow-bar', label: '多周期资金流向', icon: BarChart3 },
    { id: 'money-flow', label: '板块资金链', icon: Network },
    { id: 'stock-flow', label: '个股资金流向', icon: TrendingUp },
    { id: 'tag-lookup', label: '标签双向查询', icon: TagIcon },
  ];

  const periodOptions: Array<{ id: '1d' | '3d' | '5d' | '10d' | '20d'; label: string }> = [
    { id: '1d', label: '1日' },
    { id: '3d', label: '3日' },
    { id: '5d', label: '5日' },
    { id: '10d', label: '10日' },
    { id: '20d', label: '20日' },
  ];

  return (
    <div
      className="w-full h-full overflow-y-auto bg-slate-50/60 px-5 pt-4 pb-28 flex flex-col gap-2.5 font-sans"
      style={{
        WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.25) 10px, rgba(0,0,0,0.75) 20px, black 32px, black calc(100% - 28px), rgba(0,0,0,0.75) calc(100% - 16px), rgba(0,0,0,0.25) calc(100% - 8px), transparent 100%)',
        maskImage: 'linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.25) 10px, rgba(0,0,0,0.75) 20px, black 32px, black calc(100% - 28px), rgba(0,0,0,0.75) calc(100% - 16px), rgba(0,0,0,0.25) calc(100% - 8px), transparent 100%)',
      }}
    >
        {/* 🌟 紧凑 Banner 顶栏 */}
        <div className="relative rounded-2xl bg-gradient-to-r from-purple-100/90 via-indigo-50/80 to-purple-50/90 text-slate-900 px-5 py-2.5 shadow-xs border border-purple-200/60 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="px-3 py-0.5 rounded-full bg-purple-600/10 text-purple-700 border border-purple-200 text-xs font-extrabold font-mono flex items-center gap-1.5 shadow-2xs whitespace-nowrap">
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              <span>QuantDB 2.0 数据引擎</span>
            </span>
            <h1 className="text-base font-extrabold tracking-tight bg-gradient-to-r from-purple-950 via-indigo-900 to-slate-900 bg-clip-text text-transparent whitespace-nowrap">
              全市场多维数据分析与资金链全景
            </h1>
          </div>

          <div className="w-64 flex-shrink-0">
            <Input
              prefix={<Search className="w-3.5 h-3.5 text-purple-400 mr-1.5" />}
              placeholder="全局搜索行业或股票..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="rounded-xl border border-purple-200/80 bg-white text-xs text-slate-800 placeholder-slate-400 py-1.5 px-3.5 shadow-2xs hover:border-purple-300 focus:bg-white focus:ring-2 focus:ring-purple-100 transition-all"
            />
          </div>
        </div>

        {/* 📊 五大核心指数快照 */}
        {hasMock && (
          <div className="rounded-xl border border-amber-300/70 bg-amber-50 px-4 py-2 text-xs font-bold text-amber-700">
            ⚠️ 后端数据接口异常，当前展示 Mock 兜底数据（非 QuantDB 真实数据）
          </div>
        )}
        <BroadMarketHeader indices={indices} loading={loading} />
        {indices.length > 0 && indices[0].trade_date && (
          <div className="flex items-center gap-2 text-[11px] text-slate-400 font-medium px-1">
            <Clock className="w-3 h-3" />
            指数数据截至 <span className="font-extrabold text-slate-500">{formatTradeDate(indices[0].trade_date)}</span>
            {!hasMock && '（QuantDB 本地数据）'}
          </div>
        )}

        {/* 📌 功能切换 Tabs 导航栏 */}
        <div className="flex items-center justify-between border-b border-purple-100/80 pb-1 pt-0.5">
        <div className="flex items-center gap-2 overflow-x-auto p-1">
          {navTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-extrabold transition-all duration-200 whitespace-nowrap ${
                  isActive
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30 scale-[1.02]'
                    : 'bg-white/90 text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200/80 shadow-2xs hover:shadow-xs'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        <span className="text-[11px] text-slate-400 font-mono hidden sm:inline-block">
          {indices.length > 0 && indices[0].trade_date
            ? `数据截至 ${formatTradeDate(indices[0].trade_date)}`
            : ''}
        </span>
      </div>

      {/* 📊 资金流向全景主功能页 (含 1日/3日/5日/10日/20日 横向柱状图) */}
      {activeTab === 'flow-bar' && (
        <div className="flex flex-col gap-4">
          {/* 🛠️ 控制中心工具栏 Toolbar */}
          <div className="bg-white/95 backdrop-blur-md rounded-2xl p-3.5 border border-purple-100/80 shadow-xs flex flex-wrap items-center justify-between gap-4">
            {/* 1. 周期选择器 (1日, 3日, 5日, 10日, 20日) */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-extrabold text-slate-700 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-purple-600" />
                <span>统计周期:</span>
              </span>
              <div className="flex items-center bg-slate-100/90 border border-slate-200/60 p-1 rounded-full gap-1 shadow-2xs">
                {periodOptions.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setPeriod(p.id)}
                    className={`px-3.5 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                      period === p.id
                        ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20 scale-[1.02]'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 2. 维度与分类选择 */}
            <div className="flex items-center gap-3">
              <div className="flex items-center bg-purple-50/90 border border-purple-200/70 rounded-full p-1 gap-1 shadow-2xs">
                <button
                  onClick={() => setFlowDimension('sector')}
                  className={`px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                    flowDimension === 'sector'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20 scale-[1.02]'
                      : 'text-purple-700 hover:text-purple-900 hover:bg-purple-100/60'
                  }`}
                >
                  板块/行业流向
                </button>
                <button
                  onClick={() => setFlowDimension('stock')}
                  className={`px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                    flowDimension === 'stock'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20 scale-[1.02]'
                      : 'text-purple-700 hover:text-purple-900 hover:bg-purple-100/60'
                  }`}
                >
                  个股流向
                </button>
              </div>

              {flowDimension === 'sector' && (
                <div className="flex items-center bg-slate-100/90 border border-slate-200/60 rounded-full p-1 gap-1 shadow-2xs">
                  <button
                    onClick={() => setCategoryMode('shenwan')}
                    className={`px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                      categoryMode === 'shenwan'
                        ? 'bg-white text-slate-900 shadow-sm border border-slate-200/80 font-black'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    申万一级
                  </button>
                  <button
                    onClick={() => setCategoryMode('concept')}
                    className={`px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                      categoryMode === 'concept'
                        ? 'bg-white text-slate-900 shadow-sm border border-slate-200/80 font-black'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    热门概念
                  </button>
                </div>
              )}

              {/* 3. 视图模式 (柱状图 vs TreeMap 树图) */}
              <div className="flex items-center bg-slate-100/90 border border-slate-200/60 rounded-full p-1 gap-1 shadow-2xs">
                <button
                  onClick={() => setChartViewMode('bar')}
                  className={`flex items-center gap-1.5 px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                    chartViewMode === 'bar'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20 scale-[1.02]'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>横向柱图</span>
                </button>
                <button
                  onClick={() => setChartViewMode('treemap')}
                  className={`flex items-center gap-1.5 px-4 py-1 rounded-full text-xs font-extrabold transition-all duration-200 ${
                    chartViewMode === 'treemap'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20 scale-[1.02]'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span>矩形树图</span>
                </button>
              </div>
            </div>
          </div>

          {/* 📈 主图表展现区 */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            <div
              className={`${
                selectedFlowItem ? 'lg:col-span-8' : 'lg:col-span-12'
              } bg-white/95 backdrop-blur-md rounded-3xl p-5 border border-purple-100/80 shadow-md shadow-purple-500/5 flex flex-col gap-3 transition-all duration-300`}
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-600 animate-pulse" />
                  <h3 className="text-sm font-extrabold text-slate-900">
                    {period.toUpperCase()} 资金净流入/净流出{flowDimension === 'sector' ? '板块' : '个股'}排行榜
                  </h3>
                </div>
                <span className="text-xs text-slate-400 font-mono">
                  右侧红色: 资金净流入  |  左侧绿色: 资金净流出
                </span>
              </div>

              {chartViewMode === 'bar' ? (
                <CapitalFlowHorizontalBarChart
                  period={period}
                  dimension={flowDimension}
                  categoryMode={categoryMode}
                  height={flowDimension === 'sector' && categoryMode === 'shenwan' ? 780 : 560}
                  onItemClick={(item) => setSelectedFlowItem(item)}
                />
              ) : (
                <ShenwanHeatmapChart height={780} />
              )}
            </div>

            {/* 🎯 点击下钻卡片 Panel */}
            {selectedFlowItem && (
              <div className="lg:col-span-4 bg-white/95 backdrop-blur-md rounded-3xl p-5 border border-purple-100/80 shadow-md shadow-purple-500/5 flex flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
                <div className="flex items-center justify-between border-b border-purple-100 pb-3">
                  <div>
                    <h4 className="text-sm font-extrabold text-slate-900 flex items-center gap-2">
                      <span>{selectedFlowItem.name}</span>
                      {selectedFlowItem.symbol && (
                        <span className="text-xs font-mono text-purple-600 bg-purple-50 px-2 py-0.5 rounded-md border border-purple-200">
                          {selectedFlowItem.symbol}
                        </span>
                      )}
                    </h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">下钻资金流与主力动向拆解</p>
                  </div>
                  <button
                    onClick={() => setSelectedFlowItem(null)}
                    className="text-slate-400 hover:text-slate-700 text-xs font-bold px-2 py-1 bg-slate-100 rounded-lg"
                  >
                    关闭 ✕
                  </button>
                </div>

                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-purple-50/60 rounded-2xl p-3 border border-purple-100">
                      <span className="text-[11px] text-slate-500">区间累计净流入</span>
                      <div className={`text-base font-extrabold font-mono mt-1 ${selectedFlowItem.net_inflow >= 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                        {selectedFlowItem.net_inflow >= 0 ? '+' : ''}
                        {(selectedFlowItem.net_inflow / 100000000).toFixed(2)} 亿元
                      </div>
                    </div>

                    <div className="bg-purple-50/60 rounded-2xl p-3 border border-purple-100">
                      <span className="text-[11px] text-slate-500">主力净占比</span>
                      <div className="text-base font-extrabold font-mono text-purple-700 mt-1">
                        {selectedFlowItem.main_ratio}%
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 pt-2 border-t border-slate-100">
                    <span className="text-xs font-bold text-slate-700">筹码四分结构 (元):</span>
                    <div className="space-y-1.5 text-xs font-mono">
                      <div className="flex justify-between items-center bg-rose-50/80 px-3 py-1.5 rounded-xl border border-rose-100">
                        <span className="text-rose-700 font-bold">🔴 超大单 (主力)</span>
                        <span className="font-extrabold text-rose-800">
                          {(selectedFlowItem.super_large / 100000000).toFixed(2)} 亿
                        </span>
                      </div>
                      <div className="flex justify-between items-center bg-orange-50/80 px-3 py-1.5 rounded-xl border border-orange-100">
                        <span className="text-orange-700 font-bold">🟠 大单 (游资)</span>
                        <span className="font-extrabold text-orange-800">
                          {(selectedFlowItem.large / 100000000).toFixed(2)} 亿
                        </span>
                      </div>
                      <div className="flex justify-between items-center bg-amber-50/80 px-3 py-1.5 rounded-xl border border-amber-100">
                        <span className="text-amber-700 font-bold">🟡 中单</span>
                        <span className="font-extrabold text-amber-800">
                          {(selectedFlowItem.medium / 100000000).toFixed(2)} 亿
                        </span>
                      </div>
                      <div className="flex justify-between items-center bg-emerald-50/80 px-3 py-1.5 rounded-xl border border-emerald-100">
                        <span className="text-emerald-700 font-bold">🟢 小单 (散户)</span>
                        <span className="font-extrabold text-emerald-800">
                          {(selectedFlowItem.small / 100000000).toFixed(2)} 亿
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 原有其他页面内容维持完备 ── */}
      {activeTab === 'panorama' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
          <div className="lg:col-span-5 flex flex-col justify-between gap-4">
            <MarketBreadthCard />
            <div className="flex flex-col gap-2.5 bg-white/95 backdrop-blur-md rounded-3xl p-5 border border-purple-100/80 shadow-md shadow-purple-500/5">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-extrabold text-slate-800 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-purple-600" />
                  <span>主力资金净流入 Top 5 股票</span>
                </h3>
                <span
                  onClick={() => setActiveTab('stock-flow')}
                  className="text-[11px] text-purple-600 font-extrabold hover:underline cursor-pointer flex items-center"
                >
                  完整排行榜 ➔
                </span>
              </div>
              <StockMoneyFlowTable items={stockFlows.slice(0, 5)} isMini={true} />
            </div>
          </div>

          <div className="lg:col-span-7 bg-white/95 backdrop-blur-md rounded-3xl p-5 border border-purple-100/80 shadow-md shadow-purple-500/5 flex flex-col justify-between">
            <div className="flex items-center justify-between border-b border-purple-100/60 pb-3 mb-1">
              <h3 className="text-xs font-extrabold text-slate-900 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-purple-600" />
                <span>申万一级分类热力矩形图谱</span>
              </h3>
              <span className="text-[10px] text-slate-400 font-mono">市值权重 vs 涨跌幅</span>
            </div>
            <ShenwanHeatmapChart height={530} />
          </div>
        </div>
      )}

      {activeTab === 'money-flow' && (
        <div className="bg-white/90 backdrop-blur-md rounded-2xl p-5 border border-slate-200/80 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-extrabold text-slate-800 flex items-center gap-1.5">
              <Network className="w-3.5 h-3.5 text-purple-600" />
              <span>主力与散户资金流动全景桑基图 (Sankey Diagram)</span>
            </h3>
            <span className="text-xs text-slate-400">资金实时划转链条</span>
          </div>
          <CapitalFlowSankeyChart height={480} />
        </div>
      )}

      {activeTab === 'stock-flow' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-extrabold text-slate-800 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-purple-600" />
              <span>个股主力资金净流入排行榜</span>
            </h3>
            <span className="text-xs text-slate-400">包含超大单、大单、中单、小单拆解</span>
          </div>
          <StockMoneyFlowTable items={stockFlows} loading={loading} />
        </div>
      )}

      {activeTab === 'tag-lookup' && <TagLookupPanel />}
    </div>
  );
};


