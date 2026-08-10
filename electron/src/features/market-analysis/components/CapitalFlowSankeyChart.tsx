import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface SankeyNode {
  name: string;
}

interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

interface CapitalFlowSankeyChartProps {
  nodes?: SankeyNode[];
  links?: SankeyLink[];
  height?: number;
}

export const CapitalFlowSankeyChart: React.FC<CapitalFlowSankeyChartProps> = ({
  nodes,
  links,
  height = 380,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  const defaultNodes = [
    { name: '主力资金 (Mainforce)' },
    { name: '散户资金 (Retail)' },
    { name: '超大单 (Super Large)' },
    { name: '大单 (Large)' },
    { name: '中单 (Medium)' },
    { name: '小单 (Small)' },
    { name: '电子信息' },
    { name: '电力设备' },
    { name: '医药生物' },
    { name: '非银金融' },
  ];

  const defaultLinks = [
    { source: '主力资金 (Mainforce)', target: '超大单 (Super Large)', value: 1500 },
    { source: '主力资金 (Mainforce)', target: '大单 (Large)', value: 900 },
    { source: '散户资金 (Retail)', target: '中单 (Medium)', value: 600 },
    { source: '散户资金 (Retail)', target: '小单 (Small)', value: 1200 },
    { source: '超大单 (Super Large)', target: '电子信息', value: 850 },
    { source: '超大单 (Super Large)', target: '电力设备', value: 650 },
    { source: '大单 (Large)', target: '医药生物', value: 450 },
    { source: '大单 (Large)', target: '非银金融', value: 450 },
  ];

  const sankeyNodes = nodes && nodes.length > 0 ? nodes : defaultNodes;
  const sankeyLinks = links && links.length > 0 ? links : defaultLinks;

  useEffect(() => {
    if (!chartRef.current) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }
    const chart = instanceRef.current;

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'item',
        triggerOn: 'mousemove',
      },
      series: [
        {
          type: 'sankey',
          data: sankeyNodes,
          links: sankeyLinks,
          emphasis: { focus: 'adjacency' },
          lineStyle: {
            color: 'gradient',
            curveness: 0.5,
            opacity: 0.45,
          },
          label: {
            fontSize: 12,
            fontWeight: 'bold',
            color: '#334155',
          },
          itemStyle: {
            borderWidth: 1,
            borderColor: '#cbd5e1',
          },
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
  }, [sankeyNodes, sankeyLinks]);

  return <div ref={chartRef} style={{ width: '100%', height }} />;
};
