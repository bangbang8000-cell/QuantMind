import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { KlineItem, ForecastPoint } from '../../../services/inferenceCenterService';

interface StockForecastChartProps {
  kline: KlineItem[];
  forecast: ForecastPoint[];
  symbol: string;
  stockName: string;
  currentPrice: number;
  modelName?: string;
  asOfDate?: string;
}

export const StockForecastChart: React.FC<StockForecastChartProps> = ({
  kline,
  forecast,
  symbol,
  stockName,
  currentPrice,
  modelName,
  asOfDate,
}) => {
  const option = useMemo(() => {
    // 1. 历史 K 线数据
    const historyDates = kline.map(k => k.date);
    const klineData = kline.map(k => [k.open, k.close, k.low, k.high]); // ECharts Candlestick: [open, close, lowest, highest]

    // 2. 预测部分数据对齐
    const forecastDates = forecast.map(f => f.date);
    const allDates = [...historyDates, ...forecastDates];

    const lastKlineIndex = historyDates.length - 1;
    const lastClose = kline.length > 0 ? kline[kline.length - 1].close : currentPrice;

    // 历史部分在预测曲线上填充 null，在最后一根 K 线处连接
    const p50SeriesData: (number | null)[] = new Array(historyDates.length).fill(null);
    const p90SeriesData: (number | null)[] = new Array(historyDates.length).fill(null);
    const p10SeriesData: (number | null)[] = new Array(historyDates.length).fill(null);

    if (lastKlineIndex >= 0) {
      p50SeriesData[lastKlineIndex] = lastClose;
      p90SeriesData[lastKlineIndex] = lastClose;
      p10SeriesData[lastKlineIndex] = lastClose;
    }

    forecast.forEach(f => {
      p50SeriesData.push(f.predicted_price);
      p90SeriesData.push(f.upper_price);
      p10SeriesData.push(f.lower_price);
    });

    return {
      backgroundColor: 'transparent',
      animation: true,
      animationDuration: 800,
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          lineStyle: { color: '#94a3b8', width: 1, type: 'dashed' },
        },
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e2e8f0',
        borderWidth: 1,
        textStyle: { color: '#1e293b', fontSize: 12 },
        padding: [10, 14],
        extraCssText: 'box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); border-radius: 12px;',
        formatter: (params: any[]) => {
          if (!params || params.length === 0) return '';
          const date = params[0].axisValue;
          let html = `<div style="font-weight: 700; margin-bottom: 6px; color: #0f172a;">${date}</div>`;
          
          params.forEach((item: any) => {
            if (item.seriesType === 'candlestick') {
              const [, close, low, high] = item.data;
              html += `
                <div style="display: flex; justify-content: space-between; gap: 12px; font-size: 11px; margin: 2px 0;">
                  <span style="color: #64748b;">K线收盘:</span>
                  <span style="font-weight: 600; font-family: monospace;">¥${close?.toFixed(2)}</span>
                </div>
              `;
            } else if (item.value !== null && item.value !== undefined) {
              const color = item.color;
              html += `
                <div style="display: flex; justify-content: space-between; gap: 12px; font-size: 11px; margin: 2px 0;">
                  <span style="color: ${color}; font-weight: 500;">${item.seriesName}:</span>
                  <span style="font-weight: 600; font-family: monospace; color: #0f172a;">¥${Number(item.value).toFixed(2)}</span>
                </div>
              `;
            }
          });
          return html;
        },
      },
      legend: {
        data: ['日K线', 'P50 基准中枢 (50%)', 'P90 乐观上界 (90%)', 'P10 悲观下界 (10%)'],
        bottom: 8,
        itemGap: 18,
        textStyle: { color: '#64748b', fontSize: 11, fontWeight: 500 },
      },
      grid: {
        left: '4%',
        right: '4%',
        top: '12%',
        bottom: '14%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: allDates,
        scale: true,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          formatter: (val: string) => val ? val.slice(5) : '',
        },
        splitLine: { show: false },
      },
      yAxis: {
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          formatter: (v: number) => `¥${v.toFixed(1)}`,
        },
        splitLine: {
          lineStyle: { color: 'rgba(226, 232, 240, 0.6)', type: 'dashed' },
        },
      },
      series: [
        {
          name: '日K线',
          type: 'candlestick',
          data: klineData,
          itemStyle: {
            color: '#ef4444',
            color0: '#10b981',
            borderColor: '#ef4444',
            borderColor0: '#10b981',
          },
          markLine: lastKlineIndex >= 0 ? {
            symbol: ['none', 'none'],
            data: [
              {
                xAxis: historyDates[lastKlineIndex],
                lineStyle: { color: '#3b82f6', type: 'dashed', width: 1.5 },
                label: {
                  show: true,
                  formatter: 'T 当前基准日',
                  position: 'top',
                  color: '#2563eb',
                  fontSize: 10,
                  fontWeight: 700,
                },
              },
            ],
          } : undefined,
        },
        {
          name: 'P90 乐观上界 (90%)',
          type: 'line',
          data: p90SeriesData,
          smooth: 0.3,
          lineStyle: { color: '#ef4444', width: 2, type: 'dashed' },
          itemStyle: { color: '#ef4444' },
          symbol: 'circle',
          symbolSize: 4,
          z: 3,
        },
        {
          name: 'P50 基准中枢 (50%)',
          type: 'line',
          data: p50SeriesData,
          smooth: 0.3,
          lineStyle: { color: '#2563eb', width: 3 },
          itemStyle: { color: '#2563eb' },
          symbol: 'circle',
          symbolSize: 6,
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(37, 99, 235, 0.16)' },
                { offset: 1, color: 'rgba(37, 99, 235, 0.02)' },
              ],
            },
          },
          z: 4,
        },
        {
          name: 'P10 悲观下界 (10%)',
          type: 'line',
          data: p10SeriesData,
          smooth: 0.3,
          lineStyle: { color: '#10b981', width: 2, type: 'dashed' },
          itemStyle: { color: '#10b981' },
          symbol: 'circle',
          symbolSize: 4,
          z: 3,
        },
      ],
    };
  }, [kline, forecast, symbol, currentPrice]);

  return (
    <div className="w-full h-full relative flex flex-col">
      <div className="flex items-center justify-between px-6 pt-4 pb-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-black text-slate-800 tracking-tight">
            历史 K 线走势 + 未来 10%-50%-90% 分位数走势预测带 (Fan Chart)
          </span>
          {asOfDate && (
            <span className="text-[11px] text-slate-400 font-mono">
              · 基准日: {asOfDate}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {modelName && (
            <span className="text-xs text-slate-500 font-medium bg-slate-50 border border-slate-100 px-2.5 py-0.5 rounded-md">
              模型: <strong className="text-slate-700">{modelName}</strong>
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            实时计算
          </span>
        </div>
      </div>
      <div className="flex-1 min-h-0 w-full">
        <ReactECharts
          option={option}
          style={{ width: '100%', height: '100%' }}
          opts={{ renderer: 'canvas' }}
        />
      </div>
    </div>
  );
};
