import React, { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

export interface FlowItem {
  id: string;
  name: string;
  symbol?: string;
  pct_change: number;
  net_inflow: number; // 单位：元
  main_ratio: number; // 主力占比 %
  super_large: number;
  large: number;
  medium: number;
  small: number;
  trend_20d?: number[];
}

interface CapitalFlowHorizontalBarChartProps {
  period?: '1d' | '3d' | '5d' | '10d' | '20d';
  dimension?: 'sector' | 'stock';
  categoryMode?: 'shenwan' | 'concept';
  height?: number | string;
  onItemClick?: (item: FlowItem) => void;
}

export const CapitalFlowHorizontalBarChart: React.FC<CapitalFlowHorizontalBarChartProps> = ({
  period = '5d',
  dimension = 'sector',
  categoryMode = 'shenwan',
  height = 540,
  onItemClick,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const [data, setData] = useState<FlowItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [tradeDate, setTradeDate] = useState<string>('');
  const [isMock, setIsMock] = useState(false);

  // 1. 数据请求与 Mock 保底
  useEffect(() => {
    fetchData();
  }, [period, dimension, categoryMode]);

  const fetchData = async () => {
    setLoading(true);
    setData([]);
    setTradeDate('');
    setIsMock(false);
    try {
      const token = localStorage.getItem('access_token') || '';
      const res = await fetch(
        `/api/v1/market-analysis/money-flow/period?period=${period}&dimension=${dimension}&category=${categoryMode}&limit=25`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const json = await res.json();
        if (json.trade_date) {
          setTradeDate(json.trade_date);
        }
        if (json.items && json.items.length > 0) {
          setData(json.items);
          setLoading(false);
          return;
        }
      }
    } catch (e) {
      console.warn('后端接口未就绪，使用本地全量多周期模拟数据');
    }

    // 保底丰富数据
    const mult = { '1d': 1, '3d': 2.4, '5d': 3.8, '10d': 6.5, '20d': 11.2 }[period] || 1;

    let items: FlowItem[] = [];
    if (dimension === 'sector') {
      const baseSectors = [
        { id: 'SW_ELE', name: '电子', pct: 3.42, base: 48.5, main: 15.2 },
        { id: 'SW_BANK', name: '银行', pct: 0.85, base: 32.1, main: 8.4 },
        { id: 'SW_POWER', name: '电力设备', pct: 2.15, base: 28.6, main: 12.1 },
        { id: 'SW_COMP', name: '计算机', pct: 4.12, base: 25.4, main: 18.5 },
        { id: 'SW_COMM', name: '通信', pct: 3.95, base: 21.8, main: 16.8 },
        { id: 'SW_AUTO', name: '汽车', pct: 1.62, base: 18.2, main: 11.0 },
        { id: 'SW_NONBANK', name: '非银金融', pct: 1.88, base: 15.9, main: 9.6 },
        { id: 'SW_METAL', name: '有色金属', pct: 2.8, base: 14.2, main: 14.1 },
        { id: 'SW_MACH', name: '机械设备', pct: 1.1, base: 12.8, main: 10.5 },
        { id: 'SW_DEFENSE', name: '国防军工', pct: 2.1, base: 11.5, main: 13.2 },
        { id: 'SW_MEDIA', name: '传媒', pct: 3.1, base: 9.8, main: 12.0 },
        { id: 'SW_FOOD', name: '食品饮料', pct: 0.95, base: 6.5, main: 5.2 },
        { id: 'SW_PETRO', name: '石油石化', pct: 1.2, base: 4.2, main: 6.1 },
        { id: 'SW_TRANS', name: '交通运输', pct: 0.42, base: 3.1, main: 4.8 },
        { id: 'SW_ARCH', name: '建筑装饰', pct: 0.75, base: 2.6, main: 3.9 },
        { id: 'SW_UTIL', name: '公用事业', pct: 0.35, base: 2.1, main: 3.2 },
        { id: 'SW_COAL', name: '煤炭', pct: 1.95, base: 1.9, main: 4.1 },
        { id: 'SW_RETAIL', name: '商贸零售', pct: 0.9, base: 1.5, main: 2.8 },
        { id: 'SW_STEEL', name: '钢铁', pct: 0.3, base: 0.8, main: 1.5 },
        { id: 'SW_LIGHT', name: '轻工制造', pct: 0.25, base: 0.4, main: 1.1 },
        { id: 'SW_SOC', name: '社会服务', pct: 1.35, base: 0.2, main: 2.0 },
        { id: 'SW_TEX', name: '纺织服饰', pct: 0.15, base: -0.3, main: -0.8 },
        { id: 'SW_MISC', name: '综合', pct: 0.1, base: -0.6, main: -1.2 },
        { id: 'SW_ENV', name: '环保', pct: 0.55, base: -1.2, main: -1.8 },
        { id: 'SW_BEAUTY', name: '美容护理', pct: -0.9, base: -3.5, main: -2.4 },
        { id: 'SW_HOME', name: '家用电器', pct: -0.45, base: -6.2, main: -4.1 },
        { id: 'SW_BUILD', name: '建材', pct: -0.65, base: -8.4, main: -5.3 },
        { id: 'SW_CHEM', name: '基础化工', pct: -0.85, base: -11.5, main: -7.2 },
        { id: 'SW_AGRI', name: '农林牧渔', pct: -1.1, base: -14.0, main: -8.8 },
        { id: 'SW_MED', name: '医药生物', pct: -1.25, base: -18.6, main: -9.5 },
        { id: 'SW_REAL', name: '房地产', pct: -2.85, base: -28.2, main: -15.4 },
      ];
      items = baseSectors.map((s) => {
        const net = s.base * mult * 100000000;
        return {
          id: s.id,
          name: s.name,
          pct_change: Number((s.pct * (1 + (mult - 1) * 0.25)).toFixed(2)),
          net_inflow: net,
          main_ratio: s.main,
          super_large: net * 0.55,
          large: net * 0.3,
          medium: -net * 0.3,
          small: -net * 0.55,
          trend_20d: Array.from({ length: 20 }, (_, i) => Number((s.base * (0.8 + 0.1 * (i % 5))).toFixed(1))),
        };
      });
    } else {
      const baseStocks = [
        { id: 'SH600036', name: '招商银行', symbol: 'SH600036', pct: 2.45, base: 4.82, main: 12.8 },
        { id: 'SZ002594', name: '比亚迪', symbol: 'SZ002594', pct: 3.12, base: 4.15, main: 15.4 },
        { id: 'SH600519', name: '贵州茅台', symbol: 'SH600519', pct: 1.15, base: 3.89, main: 9.2 },
        { id: 'SZ002085', name: '万丰奥威', symbol: 'SZ002085', pct: 9.98, base: 3.1, main: 22.4 },
        { id: 'SZ002475', name: '立讯精密', symbol: 'SZ002475', pct: 4.12, base: 2.8, main: 16.2 },
        { id: 'SH688041', name: '海光信息', symbol: 'SH688041', pct: 5.78, base: 1.95, main: 19.1 },
        { id: 'SH688330', name: '宏力达', symbol: 'SH688330', pct: 6.78, base: 1.28, main: 18.5 },
        { id: 'SZ000001', name: '平安银行', symbol: 'SZ000001', pct: 1.87, base: 0.96, main: 8.4 },
        { id: 'SH601318', name: '中国平安', symbol: 'SH601318', pct: -0.85, base: -2.1, main: -8.1 },
        { id: 'SZ000002', name: '万科A', symbol: 'SZ000002', pct: -3.5, base: -3.45, main: -14.2 },
      ];
      items = baseStocks.map((st) => {
        const net = st.base * mult * 100000000;
        return {
          id: st.id,
          name: st.name,
          symbol: st.symbol,
          pct_change: Number((st.pct * (1 + (mult - 1) * 0.2)).toFixed(2)),
          net_inflow: net,
          main_ratio: st.main,
          super_large: net * 0.6,
          large: net * 0.25,
          medium: -net * 0.35,
          small: -net * 0.5,
          trend_20d: Array.from({ length: 20 }, (_, i) => Number((st.base * (0.7 + 0.15 * (i % 6))).toFixed(1))),
        };
      });
    }

    setData(items);
    setIsMock(true);
    setLoading(false);
  };

  // 2. 渲染 ECharts 横向柱状图
  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }
    const chart = instanceRef.current;

    // 按资金净流入升序排列，使得流入最大的显示在横轴最上方
    const sortedData = [...data].sort((a, b) => a.net_inflow - b.net_inflow);

    const categories = sortedData.map((d) => d.name);
    const valuesInYi = sortedData.map((d) => Number((d.net_inflow / 100000000).toFixed(2)));

    // 🎯 关键技术实现: 计算最大绝对值，设置 symmetrically 0-centered min/max 确保中线绝对居中
    const maxAbs = Math.max(...valuesInYi.map((v) => Math.abs(v)), 1) * 1.25;

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        borderColor: 'rgba(139, 92, 246, 0.4)',
        borderWidth: 1,
        textStyle: { color: '#f8fafc', fontSize: 12 },
        formatter: (params: any) => {
          if (!params || !params.length) return '';
          const p = params[0];
          const item = sortedData[p.dataIndex];
          if (!item) return '';

          const netYi = (item.net_inflow / 100000000).toFixed(2);
          const isNetPos = item.net_inflow >= 0;
          const netColor = isNetPos ? '#f43f5e' : '#10b981';

          const superYi = (item.super_large / 100000000).toFixed(2);
          const largeYi = (item.large / 100000000).toFixed(2);
          const medYi = (item.medium / 100000000).toFixed(2);
          const smYi = (item.small / 100000000).toFixed(2);

          return `
            <div style="padding: 4px 6px; font-family: system-ui, sans-serif; min-width: 210px;">
              <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.12); padding-bottom:6px; margin-bottom:8px;">
                <span style="font-weight:800; font-size:13px; color:#fff;">${item.name} ${item.symbol ? `(${item.symbol})` : ''}</span>
                <span style="font-size:11px; font-weight:700; color:${item.pct_change >= 0 ? '#f43f5e' : '#10b981'}; bg-color:rgba(255,255,255,0.1); padding:1px 6px; border-radius:4px;">
                  ${item.pct_change >= 0 ? '+' : ''}${item.pct_change}%
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:12px;">
                <span style="color:#94a3b8;">${period.toUpperCase()} 资金净流向:</span>
                <span style="font-weight:800; color:${netColor}; font-family:monospace;">${isNetPos ? '+' : ''}${netYi} 亿</span>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:11px;">
                <span style="color:#94a3b8;">主力资金净占比:</span>
                <span style="font-weight:700; color:#c084fc;">${item.main_ratio}%</span>
              </div>
              
              <div style="border-top:1px dashed rgba(255,255,255,0.1); pt:6px; font-size:11px;">
                <div style="color:#cbd5e1; margin-bottom:4px; font-weight:700;">筹码单细分拆解:</div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:4px; font-size:10px;">
                  <span style="color:#ef4444;">🔴 超大单: ${superYi}亿</span>
                  <span style="color:#f97316;">🟠 大单: ${largeYi}亿</span>
                  <span style="color:#eab308;">🟡 中单: ${medYi}亿</span>
                  <span style="color:#10b981;">🟢 小单: ${smYi}亿</span>
                </div>
              </div>
              <div style="margin-top:8px; font-size:10px; color:#64748b; text-align:right;">点击可下钻详细数据</div>
            </div>
          `;
        },
      },
      grid: {
        top: 30,
        bottom: 30,
        left: 95,
        right: 95,
        containLabel: false,
      },
      xAxis: {
        type: 'value',
        name: '资金净流向 (亿元)',
        nameTextStyle: { color: '#64748b', fontSize: 11, fontWeight: 'bold' },
        min: -maxAbs, // 🎯 强制左右对称，0 点锁定绝对居中
        max: maxAbs,  // 🎯 强制左右对称
        axisLine: { show: true, lineStyle: { color: '#94a3b8', width: 1.5 } },
        axisTick: { show: true },
        splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
        axisLabel: {
          color: '#64748b',
          fontSize: 11,
          fontFamily: 'monospace',
          formatter: (val: number) => {
            if (val === 0) return '0 轴 (居中)';
            return `${val > 0 ? '+' : ''}${val}亿`;
          },
        },
      },
      yAxis: {
        type: 'category',
        data: categories,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#334155',
          fontSize: 12,
          fontWeight: 700,
          margin: 12,
        },
      },
      series: [
        {
          name: '资金净流入',
          type: 'bar',
          barWidth: categories.length > 20 ? 14 : 18,
          data: valuesInYi.map((val) => {
            const isPos = val >= 0;
            return {
              value: val,
              itemStyle: {
                borderRadius: isPos ? [0, 8, 8, 0] : [8, 0, 0, 8],
                color: isPos
                  ? new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                      { offset: 0, color: '#f43f5e' },
                      { offset: 1, color: '#8b5cf6' },
                    ])
                  : new echarts.graphic.LinearGradient(1, 0, 0, 0, [
                      { offset: 0, color: '#10b981' },
                      { offset: 1, color: '#059669' },
                    ]),
              },
            };
          }),
          label: {
            show: true,
            position: 'outside',
            color: '#475569',
            fontSize: 11,
            fontWeight: 800,
            fontFamily: 'monospace',
            formatter: (p: any) => {
              const val = p.value as number;
              const original = sortedData[p.dataIndex];
              const pct = original ? original.pct_change : 0;
              const pctStr = `${pct >= 0 ? '+' : ''}${pct}%`;
              return `${val > 0 ? '+' : ''}${val}亿  (${pctStr})`;
            },
          },
          markLine: {
            symbol: 'none',
            silent: true,
            data: [
              {
                xAxis: 0,
                lineStyle: {
                  color: '#8b5cf6',
                  width: 2,
                  type: 'solid',
                },
                label: {
                  show: true,
                  formatter: '0 轴居中',
                  position: 'end',
                  color: '#7c3aed',
                  fontSize: 10,
                  fontWeight: 'bold',
                },
              },
            ],
          },
        },
      ],
    };

    chart.setOption(option, true);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    chart.off('click');
    chart.on('click', (params: any) => {
      if (params.dataIndex !== undefined && sortedData[params.dataIndex]) {
        onItemClick?.(sortedData[params.dataIndex]);
      }
    });

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [data, period]);

  return (
    <div className="relative w-full flex flex-col items-center justify-center">
      <div ref={chartRef} style={{ width: '100%', height: typeof height === 'number' ? `${height}px` : height }} />
      {loading && (
        <div className="absolute inset-0 bg-white/60 backdrop-blur-xs flex items-center justify-center rounded-2xl">
          <span className="text-xs text-purple-600 font-bold animate-pulse">数据加载中...</span>
        </div>
      )}
      {!loading && tradeDate && !isMock && (
        <div className="mt-1 text-[11px] text-slate-400 font-medium">
          资金流数据截至 <span className="font-extrabold text-slate-500">{formatTradeDate(tradeDate)}</span>
          （L2 资金流厂商数据已停更，仅作历史参考）
        </div>
      )}
      {!loading && isMock && (
        <div className="mt-1 text-[11px] text-amber-600 font-bold">
          ⚠️ 后端接口异常，当前为 Mock 数据（非真实资金流）
        </div>
      )}
    </div>
  );
};

function formatTradeDate(d: string): string {
  if (/^\d{8}$/.test(d)) {
    return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  }
  return d;
}
