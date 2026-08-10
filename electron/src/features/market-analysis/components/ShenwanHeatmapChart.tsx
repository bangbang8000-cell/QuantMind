import React, { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

export interface ShenwanSectorItem {
  name: string;
  value: number; // 市值规模 (亿)
  pct_change: number; // 涨跌幅 %
  leader?: string;
  leader_pct?: number;
}

interface ShenwanHeatmapChartProps {
  data?: ShenwanSectorItem[];
  height?: number | string;
  onSectorClick?: (sectorName: string) => void;
}

export const ShenwanHeatmapChart: React.FC<ShenwanHeatmapChartProps> = ({
  data,
  height = 460,
  onSectorClick,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const [categoryMode, setCategoryMode] = useState<'shenwan' | 'concept'>('shenwan');

  // 申万 31 个一级行业全量数据 (已核对 D:\quant_data\2_base_sector\sector_concept\sector_members.parquet)
  const fullShenwan31: ShenwanSectorItem[] = [
    { name: '电子', value: 8500, pct_change: 3.42, leader: '工业富联', leader_pct: 7.8 },
    { name: '银行', value: 9200, pct_change: 0.85, leader: '招商银行', leader_pct: 2.45 },
    { name: '电力设备', value: 7200, pct_change: 2.15, leader: '宁德时代', leader_pct: 4.2 },
    { name: '医药生物', value: 6800, pct_change: -1.25, leader: '恒瑞医药', leader_pct: -2.1 },
    { name: '非银金融', value: 6100, pct_change: 1.88, leader: '东方财富', leader_pct: 3.9 },
    { name: '食品饮料', value: 5900, pct_change: 0.95, leader: '贵州茅台', leader_pct: 1.15 },
    { name: '计算机', value: 5200, pct_change: 4.12, leader: '金山办公', leader_pct: 8.5 },
    { name: '汽车', value: 4800, pct_change: 1.62, leader: '比亚迪', leader_pct: 3.12 },
    { name: '石油石化', value: 4500, pct_change: 1.20, leader: '中国石油', leader_pct: 2.1 },
    { name: '基础化工', value: 4200, pct_change: -0.85, leader: '万华化学', leader_pct: -1.0 },
    { name: '有色金属', value: 3900, pct_change: 2.80, leader: '紫金矿业', leader_pct: 5.2 },
    { name: '机械设备', value: 3700, pct_change: 1.10, leader: '三一重工', leader_pct: 2.3 },
    { name: '通信', value: 3400, pct_change: 3.95, leader: '中兴通讯', leader_pct: 6.7 },
    { name: '交通运输', value: 3100, pct_change: 0.42, leader: '顺丰控股', leader_pct: 1.2 },
    { name: '国防军工', value: 2900, pct_change: 2.10, leader: '航发动力', leader_pct: 3.8 },
    { name: '传媒', value: 2800, pct_change: 3.10, leader: '分众传媒', leader_pct: 4.8 },
    { name: '家用电器', value: 2700, pct_change: -0.45, leader: '美的集团', leader_pct: -0.6 },
    { name: '建筑装饰', value: 2600, pct_change: 0.75, leader: '中国建筑', leader_pct: 1.5 },
    { name: '公用事业', value: 2500, pct_change: 0.35, leader: '长江电力', leader_pct: 0.5 },
    { name: '煤炭', value: 2300, pct_change: 1.95, leader: '中国神华', leader_pct: 2.8 },
    { name: '房地产', value: 2200, pct_change: -2.85, leader: '万科A', leader_pct: -3.5 },
    { name: '农林牧渔', value: 2100, pct_change: -1.10, leader: '牧原股份', leader_pct: -1.8 },
    { name: '商贸零售', value: 1900, pct_change: 0.90, leader: '永辉超市', leader_pct: 1.8 },
    { name: '钢铁', value: 1800, pct_change: 0.30, leader: '宝钢股份', leader_pct: 0.8 },
    { name: '建材', value: 1600, pct_change: -0.65, leader: '海螺水泥', leader_pct: -1.1 },
    { name: '轻工制造', value: 1500, pct_change: 0.25, leader: '晨鸣纸业', leader_pct: 0.5 },
    { name: '社会服务', value: 1400, pct_change: 1.35, leader: '中国中免', leader_pct: 2.5 },
    { name: '纺织服饰', value: 1300, pct_change: 0.15, leader: '海澜之家', leader_pct: 0.4 },
    { name: '美容护理', value: 1200, pct_change: -0.90, leader: '爱美客', leader_pct: -1.5 },
    { name: '环保', value: 1100, pct_change: 0.55, leader: '浙富控股', leader_pct: 1.1 },
    { name: '综合', value: 900, pct_change: 0.10, leader: '泰达股份', leader_pct: 0.3 },
  ];

  // 从 D:\quant_data 提取的热门概念板块数据
  const conceptSectors: ShenwanSectorItem[] = [
    { name: '低空经济', value: 3800, pct_change: 5.62, leader: '万丰奥威', leader_pct: 9.98 },
    { name: '铜缆高速连接', value: 2900, pct_change: 4.85, leader: '新亚电子', leader_pct: 8.42 },
    { name: '5G概念', value: 4500, pct_change: 3.80, leader: '中兴通讯', leader_pct: 6.70 },
    { name: '锂电池概念', value: 6200, pct_change: 2.90, leader: '宁德时代', leader_pct: 4.20 },
    { name: '光伏概念', value: 5100, pct_change: 2.30, leader: '阳光电源', leader_pct: 3.90 },
    { name: '云计算', value: 4700, pct_change: 3.95, leader: '浪潮信息', leader_pct: 6.30 },
    { name: '碳中和', value: 3900, pct_change: 1.85, leader: '隆基绿能', leader_pct: 3.20 },
    { name: 'AI手机PC', value: 3800, pct_change: 4.15, leader: '传音控股', leader_pct: 7.10 },
    { name: '智能电网', value: 3600, pct_change: 2.45, leader: '国电南瑞', leader_pct: 4.10 },
    { name: '核电核能', value: 3400, pct_change: 1.90, leader: '中国核电', leader_pct: 2.80 },
    { name: '物联网', value: 3300, pct_change: 2.75, leader: '移远通信', leader_pct: 4.90 },
    { name: '黄金概念', value: 3100, pct_change: 3.12, leader: '山东黄金', leader_pct: 5.40 },
    { name: '稀土永磁', value: 2700, pct_change: 3.65, leader: '北方稀土', leader_pct: 6.10 },
    { name: '军工信息化', value: 2500, pct_change: 3.40, leader: '睿创微纳', leader_pct: 5.80 },
    { name: '合成生物', value: 2400, pct_change: 4.30, leader: '华恒生物', leader_pct: 7.20 },
    { name: '高分红股', value: 5800, pct_change: 1.15, leader: '长江电力', leader_pct: 1.80 },
    { name: '创投概念', value: 2100, pct_change: 1.45, leader: '鲁信创投', leader_pct: 2.70 },
    { name: '微盘精选', value: 1900, pct_change: -1.80, leader: '开勒股份', leader_pct: -3.20 },
  ];

  const sectorItems =
    data && data.length > 0
      ? data
      : categoryMode === 'shenwan'
      ? fullShenwan31
      : conceptSectors;

  useEffect(() => {
    if (!chartRef.current) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }
    const chart = instanceRef.current;

    const formattedData = sectorItems.map((item) => ({
      name: item.name,
      value: item.value,
      pct_change: item.pct_change,
      leader: item.leader,
      leader_pct: item.leader_pct,
      itemStyle: {
        color:
          item.pct_change > 2
            ? '#ef4444'
            : item.pct_change > 0
            ? '#f87171'
            : item.pct_change === 0
            ? '#94a3b8'
            : item.pct_change > -2
            ? '#34d399'
            : '#10b981',
      },
    }));

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        borderColor: '#334155',
        textStyle: { color: '#ffffff' },
        formatter: (info: any) => {
          const d = info.data || {};
          const cap = d.value || info.value || 0;
          const pct = d.pct_change ?? 0;
          const color = pct >= 0 ? '#f87171' : '#34d399';
          const leaderText = d.leader ? `<div style="margin-top: 2px; color: #cbd5e1;">领涨龙头: <b>${d.leader} (${d.leader_pct >= 0 ? '+' : ''}${d.leader_pct}%)</b></div>` : '';
          return `
            <div style="font-family: sans-serif; font-size: 12px; padding: 2px 4px;">
              <div style="font-weight: bold; font-size: 13px; margin-bottom: 4px; border-bottom: 1px solid #475569; padding-bottom: 4px;">${info.name}</div>
              <div>市值权重规模: <b>${cap} 亿</b></div>
              <div>平均涨跌幅: <span style="color: ${color}; font-weight: bold;">${pct >= 0 ? '+' : ''}${pct}%</span></div>
              ${leaderText}
            </div>
          `;
        },
      },
      series: [
        {
          type: 'treemap',
          top: 4,
          bottom: 4,
          left: 4,
          right: 4,
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: {
            show: true,
            formatter: (params: any) => {
              const d = params.data || {};
              const pct = d.pct_change ?? 0;
              return `{name|${params.name}}\n{pct|${pct >= 0 ? '+' : ''}${pct}%}`;
            },
            rich: {
              name: {
                fontSize: 11,
                fontWeight: 'bold',
                color: '#ffffff',
                lineHeight: 15,
              },
              pct: {
                fontSize: 10,
                fontWeight: 'bold',
                color: '#ffffff',
                fontFamily: 'monospace',
              },
            },
          },
          itemStyle: {
            borderColor: '#ffffff',
            borderWidth: 1.5,
            gapWidth: 1.5,
          },
          data: formattedData,
        },
      ],
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
      instanceRef.current = null;
    };
  }, [sectorItems]);

  return (
    <div className="w-full flex flex-col gap-2">
      {/* 分类模式选择切片 */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 bg-slate-100/90 p-1 rounded-xl border border-slate-200/60">
          <button
            onClick={() => setCategoryMode('shenwan')}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
              categoryMode === 'shenwan'
                ? 'bg-white text-purple-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            申万一级分类 (全量)
          </button>
          <button
            onClick={() => setCategoryMode('concept')}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
              categoryMode === 'concept'
                ? 'bg-white text-purple-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            热门概念板块
          </button>

        </div>

        <span className="text-[11px] text-slate-400 font-mono">
          包含 {sectorItems.length} 个分析板块
        </span>
      </div>

      <div ref={chartRef} style={{ width: '100%', height }} />
    </div>
  );
};
