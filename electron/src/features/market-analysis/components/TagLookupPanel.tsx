import React, { useState, useEffect } from 'react';
import {
  Search,
  Tag as TagIcon,
  Sparkles,
  ArrowUpRight,
  TrendingUp,
  TrendingDown,
  Layers,
  Hash,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Table as TableIcon,
  ChevronRight
} from 'lucide-react';
import { Input, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';

interface HotTagItem {
  name: string;
  type: string;
  count: number;
}

interface SectorCardItem {
  code: string;
  name: string;
  type: string;
  count: number;
  stocks: { symbol: string; name: string }[];
}

export const TagLookupPanel: React.FC = () => {
  const [perspective, setPerspective] = useState<'stock' | 'sector'>('stock');
  const [sectorFilter, setSectorFilter] = useState<string>('全部');
  const [searchQuery, setSearchQuery] = useState('600000.SH');
  const [loading, setLoading] = useState(false);
  const [isHotTagsCollapsed, setIsHotTagsCollapsed] = useState(false);
  const [expandedSectorCode, setExpandedSectorCode] = useState<string | null>(null);

  const [tagToStocksData, setTagToStocksData] = useState<any[]>([]);
  const [stockToTagsData, setStockToTagsData] = useState<Record<string, string[]>>({});

  const sectorSubCategories = ['全部', '地区板块', '概念板块', '行业板块(一级)', '行业板块(二级)', '风格板块'];

  const hotTagsList: HotTagItem[] = [
    { name: '机器人概念', type: '概念板块', count: 1207 },
    { name: '专精特新', type: '概念板块', count: 1203 },
    { name: '连续亏损', type: '概念板块', count: 1078 },
    { name: '人工智能', type: '概念板块', count: 1067 },
    { name: '新能源车', type: '概念板块', count: 1064 },
    { name: '芯片', type: '概念板块', count: 910 },
    { name: '储能', type: '概念板块', count: 909 },
    { name: '一带一路', type: '概念板块', count: 775 },
    { name: 'DeepSeek概念', type: '概念板块', count: 775 },
    { name: '浙江板块', type: '地区板块', count: 750 },
    { name: '江苏板块', type: '地区板块', count: 734 },
    { name: '数据中心', type: '概念板块', count: 652 },
    { name: '锂电池概念', type: '概念板块', count: 611 },
    { name: '微小盘股', type: '概念板块', count: 600 },
    { name: '破发股价', type: '概念板块', count: 547 },
    { name: '业绩预升', type: '概念板块', count: 546 },
    { name: '国防军工', type: '概念板块', count: 532 },
    { name: '商业航天', type: '概念板块', count: 526 },
    { name: '光伏', type: '概念板块', count: 517 },
    { name: '物联网', type: '概念板块', count: 511 },
  ];

  // 模拟板块视角下的板块列表卡片数据 (完美复刻参考图 2)
  const sectorCardsList: SectorCardItem[] = [
    {
      code: '880081.SH',
      name: '轮动趋势',
      type: '风格板块',
      count: 2,
      stocks: [
        { symbol: '511010.SH', name: '国债现货' },
        { symbol: '511260.SH', name: '十年国债' },
      ],
    },
    {
      code: '880082.SH',
      name: '破净修复',
      type: '风格板块',
      count: 3,
      stocks: [
        { symbol: 'SH600036', name: '招商银行' },
        { symbol: 'SZ000001', name: '平安银行' },
        { symbol: 'SH601328', name: '交通银行' },
      ],
    },
    {
      code: '880083.SH',
      name: '机器人概念',
      type: '概念板块',
      count: 1207,
      stocks: [
        { symbol: 'SZ002085', name: '万丰奥威' },
        { symbol: 'SZ002475', name: '立讯精密' },
        { symbol: 'SZ002594', name: '比亚迪' },
      ],
    },
    {
      code: '880084.SH',
      name: '上海金融核心区',
      type: '地区板块',
      count: 15,
      stocks: [
        { symbol: 'SH600000', name: '浦发银行' },
        { symbol: 'SH600036', name: '招商银行' },
      ],
    },
  ];

  const handlePerspectiveChange = (newMode: 'stock' | 'sector') => {
    setPerspective(newMode);
    if (newMode === 'stock') {
      setSearchQuery('600000.SH');
      handleSearch('600000.SH');
    } else {
      setSearchQuery('880081.SH');
      handleSearch('880081.SH');
    }
  };

  useEffect(() => {
    handleSearch(searchQuery);
  }, []);

  const handleSearch = async (queryText: string) => {
    if (!queryText.trim()) return;
    setSearchQuery(queryText);
    setLoading(true);

    try {
      if (perspective === 'sector') {
        const res = await fetch(`/api/v1/market-analysis/tags/by-tag?tag=${encodeURIComponent(queryText)}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
        });
        if (res.ok) {
          const data = await res.json();
          setTagToStocksData(data.items || []);
        } else {
          fallbackTagToStocks(queryText);
        }
      } else {
        const res = await fetch(`/api/v1/market-analysis/tags/by-stock?symbol=${encodeURIComponent(queryText)}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
        });
        if (res.ok) {
          const data = await res.json();
          setStockToTagsData(data.tags || {});
        } else {
          fallbackStockToTags(queryText);
        }
      }
    } catch (e) {
      if (perspective === 'sector') fallbackTagToStocks(queryText);
      else fallbackStockToTags(queryText);
    }
    setLoading(false);
  };

  const fallbackTagToStocks = (tag: string) => {
    setTagToStocksData([
      { symbol: '511010.SH', name: '国债现货', close_price: 104.25, pct_change: 0.12, market_cap: 1250.4, net_inflow: 310000000 },
      { symbol: '511260.SH', name: '十年国债', close_price: 102.80, pct_change: 0.08, market_cap: 890.5, net_inflow: 180000000 },
      { symbol: 'SZ002085', name: '万丰奥威', close_price: 16.85, pct_change: 9.98, market_cap: 358.4, net_inflow: 310000000 },
      { symbol: 'SZ002475', name: '立讯精密', close_price: 38.50, pct_change: 4.12, market_cap: 2760.5, net_inflow: 280000000 },
      { symbol: 'SZ002594', name: '比亚迪', close_price: 248.50, pct_change: 3.12, market_cap: 7230.1, net_inflow: 415000000 },
      { symbol: 'SH600036', name: '招商银行', close_price: 35.80, pct_change: 2.45, market_cap: 9020.8, net_inflow: 482000000 },
    ]);
  };

  const fallbackStockToTags = (symbol: string) => {
    setStockToTagsData({
      '风格板块': ['轮动趋势 880081.SH', '破净修复 880082.SH', '高股息率 880083.SH'],
      '概念板块': ['沪深300', '上证50', 'MSCI中国', '富时罗素概念', 'ESG百强'],
      '行业板块(一级)': ['金融业', '非银金融'],
      '行业板块(二级)': ['股份制银行', '大金融集团'],
      '地区板块': ['上海板块', '陆家嘴金融区'],
    });
  };

  const columns: ColumnsType<any> = [
    {
      title: '序号',
      key: 'idx',
      width: 50,
      align: 'center',
      render: (_, __, i) => <span className="font-mono text-xs font-bold text-purple-600">{i + 1}</span>,
    },
    {
      title: '股票代码 / 名称',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 170,
      render: (symbol, r) => (
        <div className="flex items-center gap-2 whitespace-nowrap">
          <div className="w-7 h-7 rounded-xl bg-purple-50 text-purple-700 font-extrabold text-xs flex items-center justify-center border border-purple-100 shadow-inner">
            {r.name.substring(0, 1)}
          </div>
          <div>
            <div className="font-bold text-slate-800 text-xs flex items-center gap-1">
              <span>{r.name}</span>
              <ArrowUpRight className="w-3 h-3 text-slate-400" />
            </div>
            <div className="text-[10px] text-slate-400 font-mono">{symbol}</div>
          </div>
        </div>
      ),
    },
    {
      title: '最新价',
      dataIndex: 'close_price',
      key: 'close_price',
      align: 'right',
      width: 90,
      render: (v) => <span className="font-mono text-xs font-semibold text-slate-800">¥{v.toFixed(2)}</span>,
    },
    {
      title: '涨跌幅',
      dataIndex: 'pct_change',
      key: 'pct_change',
      align: 'right',
      width: 100,
      render: (v) => {
        const isPos = v >= 0;
        return (
          <span className={`font-mono text-xs font-bold flex items-center justify-end gap-0.5 ${isPos ? 'text-red-500' : 'text-emerald-500'}`}>
            {isPos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {isPos ? '+' : ''}{v.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: '总市值规模',
      dataIndex: 'market_cap',
      key: 'market_cap',
      align: 'right',
      width: 110,
      render: (v) => <span className="font-mono text-xs font-medium text-slate-600">¥{v} 亿</span>,
    },
    {
      title: '主力资金净流入',
      dataIndex: 'net_inflow',
      key: 'net_inflow',
      align: 'right',
      width: 140,
      render: (v) => {
        const isPos = v >= 0;
        return (
          <span className={`font-mono text-xs font-extrabold ${isPos ? 'text-red-500' : 'text-emerald-500'}`}>
            {isPos ? '+' : ''}{(v / 1e8).toFixed(2)} 亿
          </span>
        );
      },
    },
  ];

  return (
    <div className="w-full flex flex-col gap-5 bg-white/95 backdrop-blur-md rounded-3xl p-6 border border-purple-100/80 shadow-lg shadow-purple-500/5">
      {/* 🌟 1. 顶部 4 大统计数据卡片 (参考设计图) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 卡片 1: 总板块数 */}
        <div className="bg-gradient-to-br from-white to-blue-50/40 rounded-2xl p-4 border border-blue-100/80 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 font-bold mb-1">总板块数</div>
            <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">583</div>
            <div className="text-[10px] text-slate-400 font-medium mt-1">涵盖行业/概念/风格</div>
          </div>
          <div className="p-3 rounded-2xl bg-blue-100/70 text-blue-600 border border-blue-200/60 shadow-inner">
            <Layers className="w-6 h-6" />
          </div>
        </div>

        {/* 卡片 2: 覆盖股票 */}
        <div className="bg-gradient-to-br from-white to-emerald-50/40 rounded-2xl p-4 border border-emerald-100/80 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 font-bold mb-1">覆盖股票</div>
            <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">6,035</div>
            <div className="text-[10px] text-slate-400 font-medium mt-1">沪深京 A 股全量</div>
          </div>
          <div className="p-3 rounded-2xl bg-emerald-100/70 text-emerald-600 border border-emerald-200/60 shadow-inner">
            <Hash className="w-6 h-6" />
          </div>
        </div>

        {/* 卡片 3: 平均标签数 */}
        <div className="bg-gradient-to-br from-white to-amber-50/40 rounded-2xl p-4 border border-amber-100/80 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 font-bold mb-1">平均标签数</div>
            <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">13.5</div>
            <div className="text-[10px] text-slate-400 font-medium mt-1">最高单股 66 个</div>
          </div>
          <div className="p-3 rounded-2xl bg-amber-100/70 text-amber-600 border border-amber-200/60 shadow-inner">
            <BarChart3 className="w-6 h-6" />
          </div>
        </div>

        {/* 卡片 4: 总记录数 */}
        <div className="bg-gradient-to-br from-white to-purple-50/40 rounded-2xl p-4 border border-purple-100/80 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 font-bold mb-1">总记录数</div>
            <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">81,608</div>
            <div className="text-[10px] text-slate-400 font-medium mt-1">股票-板块映射关系</div>
          </div>
          <div className="p-3 rounded-2xl bg-purple-100/70 text-purple-600 border border-purple-200/60 shadow-inner">
            <TagIcon className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* 🌟 2. 视角切换与板块类别过滤 (参考设计图) */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pt-1">
        <div className="flex items-center gap-3">
          {/* 视角分段按钮 */}
          <div className="flex items-center p-1 rounded-2xl bg-slate-100 border border-slate-200/60 shadow-inner">
            <button
              onClick={() => handlePerspectiveChange('stock')}
              className={`px-5 py-2 rounded-xl text-xs font-extrabold transition-all duration-200 ${
                perspective === 'stock'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              股票视角
            </button>
            <button
              onClick={() => handlePerspectiveChange('sector')}
              className={`px-5 py-2 rounded-xl text-xs font-extrabold transition-all duration-200 ${
                perspective === 'sector'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              板块视角
            </button>
          </div>

          {/* 当在板块视角时，展示子分类 Pills */}
          {perspective === 'sector' && (
            <div className="flex items-center gap-1.5 overflow-x-auto">
              {sectorSubCategories.map((sc) => (
                <button
                  key={sc}
                  onClick={() => setSectorFilter(sc)}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
                    sectorFilter === sc
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80'
                  }`}
                >
                  {sc}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="text-xs text-slate-400 font-mono hidden lg:inline-block">
          探索 583 个板块与 6,035 只股票的多维关联
        </span>
      </div>

      {/* 🌟 3. 统一搜索输入框与“立即检索”按钮 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Input
            prefix={<Search className="w-4 h-4 text-slate-400 mr-2" />}
            placeholder={perspective === 'stock' ? '输入股票代码或名称，如 600000.SH / 招商银行' : '输入板块名称或代码，如 880081.SH / 轮动趋势 / 机器人概念'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
            className="rounded-2xl border border-slate-200 bg-white text-xs text-slate-800 placeholder-slate-400 py-3 px-4 shadow-xs hover:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-100 transition-all"
          />
        </div>
        <button
          onClick={() => handleSearch(searchQuery)}
          className="px-6 py-3 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white text-xs font-extrabold shadow-md shadow-blue-600/20 hover:shadow-lg transition-all flex items-center gap-2 flex-shrink-0"
        >
          <Search className="w-4 h-4" />
          <span>立即检索</span>
        </button>
      </div>

      {/* 🌟 4. 主内容渲染区 (根据视角精确区分渲染逻辑) */}
      {perspective === 'stock' ? (
        <div className="flex flex-col gap-3">
          <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-extrabold text-blue-600 font-mono">{searchQuery}</span>
                <span className="text-xs text-slate-400">包含 {Object.values(stockToTagsData).flat().length || 1} 个板块标签</span>
              </div>
            </div>

            <div className="flex flex-col gap-3 pt-1">
              {Object.entries(stockToTagsData).map(([groupTitle, tagList]) => (
                <div key={groupTitle} className="flex flex-col gap-2">
                  <div className="text-xs font-bold text-slate-500">{groupTitle}:</div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {tagList.map((t) => (
                      <span
                        key={t}
                        onClick={() => {
                          handlePerspectiveChange('sector');
                          handleSearch(t);
                        }}
                        className="px-3.5 py-1.5 rounded-full bg-emerald-50 text-emerald-700 font-extrabold text-xs border border-emerald-200/80 flex items-center gap-1.5 cursor-pointer hover:bg-emerald-600 hover:text-white transition-all shadow-2xs"
                      >
                        <TagIcon className="w-3 h-3 text-emerald-500" />
                        <span>{t}</span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* 🌟 板块视角 (完美复刻参考图 2：展示板块卡片及成分股 Pill) */
        <div className="flex flex-col gap-4">
          {sectorCardsList
            .filter((item) => sectorFilter === '全部' || item.type === sectorFilter)
            .map((sectorItem) => (
              <div key={sectorItem.code} className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex flex-col gap-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-extrabold text-blue-600 font-mono">{sectorItem.code}</span>
                    <span className="text-sm font-extrabold text-slate-900">{sectorItem.name}</span>
                    <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs font-bold border border-blue-100">
                      {sectorItem.count} 只成分股
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-600 text-xs font-bold border border-purple-100">
                      {sectorItem.type}
                    </span>
                  </div>

                  <button
                    onClick={() => setExpandedSectorCode(expandedSectorCode === sectorItem.code ? null : sectorItem.code)}
                    className="flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors"
                  >
                    <span>{expandedSectorCode === sectorItem.code ? '收起成分股列表' : '查看全量行情列表'}</span>
                    {expandedSectorCode === sectorItem.code ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {/* 板块包含的成分股 Pill 列表 */}
                <div className="flex items-center gap-2 flex-wrap pt-1">
                  {sectorItem.stocks.map((stk) => (
                    <span
                      key={stk.symbol}
                      onClick={() => {
                        handlePerspectiveChange('stock');
                        handleSearch(stk.symbol);
                      }}
                      className="px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 text-xs font-mono font-bold border border-slate-200/70 cursor-pointer transition-all flex items-center gap-1.5"
                    >
                      <span>{stk.symbol}</span>
                      <span className="text-slate-400 font-sans font-normal">({stk.name})</span>
                    </span>
                  ))}
                </div>

                {/* 若展开行情列表 */}
                {expandedSectorCode === sectorItem.code && (
                  <div className="mt-2 overflow-hidden rounded-xl border border-slate-200/80 animate-in fade-in duration-150">
                    <Table
                      columns={columns}
                      dataSource={tagToStocksData.map((d, i) => ({ ...d, key: i }))}
                      loading={loading}
                      pagination={{ pageSize: 5 }}
                      size="small"
                    />
                  </div>
                )}
              </div>
            ))}
        </div>
      )}

      {/* 🌟 5. 底部“热门板块 (按成分股数量排序)” (可折叠 Collapsible) */}
      <div className="bg-slate-50/80 rounded-2xl p-5 border border-slate-200/80 shadow-xs flex flex-col gap-3.5 transition-all">
        {/* 顶部标题 + 折叠开关 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-blue-600" />
            <h3 className="text-xs font-extrabold text-slate-900 tracking-tight">热门板块 (按成分股数量排序)</h3>
          </div>
          <button
            onClick={() => setIsHotTagsCollapsed(!isHotTagsCollapsed)}
            className="flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-blue-600 transition-colors px-2.5 py-1 rounded-lg hover:bg-slate-200/60"
          >
            <span>{isHotTagsCollapsed ? '展开热门板块' : '收起热门板块'}</span>
            {isHotTagsCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>

        {/* 标签列表区（可折叠） */}
        {!isHotTagsCollapsed && (
          <div className="flex items-center gap-2.5 flex-wrap pt-1 animate-in fade-in duration-200">
            {hotTagsList.map((tagItem) => (
              <div
                key={tagItem.name}
                onClick={() => {
                  handlePerspectiveChange('sector');
                  handleSearch(tagItem.name);
                }}
                className="group flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white hover:bg-blue-600 text-slate-700 hover:text-white border border-slate-200/80 hover:border-blue-600 cursor-pointer transition-all duration-200 shadow-2xs hover:shadow-sm"
              >
                <span className="text-xs font-bold">{tagItem.name}</span>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 group-hover:bg-blue-500 text-slate-500 group-hover:text-white text-[10px] font-medium border border-slate-200/60 group-hover:border-blue-400">
                  {tagItem.type}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-blue-50 group-hover:bg-blue-700 text-blue-600 group-hover:text-white text-[10px] font-mono font-extrabold">
                  {tagItem.count}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
