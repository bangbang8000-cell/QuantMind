/**
 * 跨市场分析工具
 *
 * 结合 AkShare（中国市场）和 OpenBB（全球市场）数据
 * 提供跨市场对比、相关性分析、联动分析等功能
 */

import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';

// 导入 AkShare API
import { getStockDaily as getCNStockDaily } from '../cn-market/akshare-api';

// 导入 OpenBB API
import { getEquityHistorical as getUSStockHistorical } from '../openbb/openbb-api';

/**
 * 计算两个数据序列的相关系数（简化版皮尔逊相关系数）
 */
function calculateCorrelation(data1: any[], data2: any[]): number {
  // 对齐日期并提取收盘价
  const aligned = alignDataByDate(data1, data2);

  if (aligned.length < 2) {
    return 0;
  }

  const values1 = aligned.map((item) => item.value1);
  const values2 = aligned.map((item) => item.value2);

  // 计算均值
  const mean1 = values1.reduce((a, b) => a + b, 0) / values1.length;
  const mean2 = values2.reduce((a, b) => a + b, 0) / values2.length;

  // 计算协方差和标准差
  let covariance = 0;
  let variance1 = 0;
  let variance2 = 0;

  for (let i = 0; i < values1.length; i++) {
    const diff1 = values1[i] - mean1;
    const diff2 = values2[i] - mean2;
    covariance += diff1 * diff2;
    variance1 += diff1 * diff1;
    variance2 += diff2 * diff2;
  }

  const stdDev1 = Math.sqrt(variance1);
  const stdDev2 = Math.sqrt(variance2);

  if (stdDev1 === 0 || stdDev2 === 0) {
    return 0;
  }

  return covariance / (stdDev1 * stdDev2);
}

/**
 * 按日期对齐两个数据集
 */
function alignDataByDate(
  data1: any[],
  data2: any[]
): Array<{ date: string; value1: number; value2: number }> {
  const map1 = new Map();
  const map2 = new Map();

  // 构建日期到收盘价的映射
  data1.forEach((item) => {
    const date = item.date || item['日期'] || item.Date;
    const close = item.close || item['收盘'] || item.Close;
    if (date && close) {
      map1.set(date, parseFloat(close));
    }
  });

  data2.forEach((item) => {
    const date = item.date || item['日期'] || item.Date;
    const close = item.close || item['收盘'] || item.Close;
    if (date && close) {
      map2.set(date, parseFloat(close));
    }
  });

  // 找到共同的日期
  const aligned: Array<{ date: string; value1: number; value2: number }> = [];
  map1.forEach((value1, date) => {
    if (map2.has(date)) {
      aligned.push({
        date,
        value1,
        value2: map2.get(date),
      });
    }
  });

  return aligned.sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * 计算涨跌幅
 */
function calculateReturns(data: any[]): number {
  if (data.length < 2) return 0;

  const firstClose = parseFloat(data[0].close || data[0]['收盘'] || data[0].Close);
  const lastClose = parseFloat(
    data[data.length - 1].close ||
      data[data.length - 1]['收盘'] ||
      data[data.length - 1].Close
  );

  return ((lastClose - firstClose) / firstClose) * 100;
}

/**
 * 工具 1: 中美股市对比分析
 */
export const compareCNUSMarketsTool = new DynamicStructuredTool({
  name: 'compare_cn_us_markets',
  description: `对比中国 A股和美股的走势和相关性，分析跨市场联动。

  适用场景：
  - 分析中美股市关联度
  - 研究跨市场投资机会
  - 评估全球市场风险
  - 对比同行业公司表现（如茅台 vs 帝亚吉欧）

  示例：
  - 对比贵州茅台（600519）和可口可乐（KO）
  - 对比宁德时代（300750）和特斯拉（TSLA）
  - 对比招商银行（600036）和摩根大通（JPM）`,
  schema: z.object({
    cnSymbol: z.string().describe('A股代码，如 600519（贵州茅台）'),
    usSymbol: z.string().describe('美股代码，如 AAPL, TSLA'),
    days: z
      .number()
      .default(30)
      .describe('对比天数，默认30天，建议30-90天'),
  }),
  func: async (input) => {
    try {
      // 计算日期范围
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - input.days);

      const cnStartDate = formatDate(startDate, 'cn');
      const cnEndDate = formatDate(endDate, 'cn');
      const usStartDate = formatDate(startDate, 'us');
      const usEndDate = formatDate(endDate, 'us');

      // 并行获取中美股票数据
      const [cnResult, usResult] = await Promise.all([
        getCNStockDaily(input.cnSymbol, {
          startDate: cnStartDate,
          endDate: cnEndDate,
        }),
        getUSStockHistorical(input.usSymbol, {
          startDate: usStartDate,
          endDate: usEndDate,
        }),
      ]);

      // 检查错误
      if (cnResult.status === 'error') {
        return `获取A股数据失败：${cnResult.message}`;
      }
      if (usResult.status === 'error') {
        return `获取美股数据失败：${usResult.message}`;
      }

      const cnData = cnResult.data;
      const usData = usResult.data;

      // 计算相关性
      const correlation = calculateCorrelation(cnData, usData);

      // 计算涨跌幅
      const cnReturn = calculateReturns(cnData);
      const usReturn = calculateReturns(usData);

      // 对齐数据
      const aligned = alignDataByDate(cnData, usData);

      // 生成分析报告
      const analysis = {
        summary: {
          cn_symbol: input.cnSymbol,
          us_symbol: input.usSymbol,
          period: `${input.days}天`,
          correlation: correlation.toFixed(4),
          correlation_strength: getCorrelationStrength(correlation),
        },
        performance: {
          cn_return: `${cnReturn.toFixed(2)}%`,
          us_return: `${usReturn.toFixed(2)}%`,
          relative_performance:
            cnReturn > usReturn ? 'A股表现更好' : '美股表现更好',
        },
        data_points: {
          cn_data_points: cnData.length,
          us_data_points: usData.length,
          aligned_points: aligned.length,
        },
        interpretation: generateInterpretation(correlation, cnReturn, usReturn),
      };

      return `## 中美股市对比分析

**标的对比**
- 🇨🇳 A股：${input.cnSymbol}
- 🇺🇸 美股：${input.usSymbol}
- 📅 周期：${input.days} 天

**相关性分析**
- 相关系数：${correlation.toFixed(4)}
- 相关性强度：${getCorrelationStrength(correlation)}

**表现对比**
- A股涨跌幅：${cnReturn.toFixed(2)}%
- 美股涨跌幅：${usReturn.toFixed(2)}%
- 相对表现：${cnReturn > usReturn ? 'A股表现更好' : '美股表现更好'}

**数据质量**
- A股数据点：${cnData.length}
- 美股数据点：${usData.length}
- 对齐数据点：${aligned.length}

**分析解读**
${generateInterpretation(correlation, cnReturn, usReturn)}

---
数据来源：AkShare（A股）+ OpenBB（美股）`;
    } catch (error: any) {
      return `分析失败：${error.message}`;
    }
  },
});

/**
 * 工具 2: 中美宏观经济对比
 */
export const compareCNUSMacroTool = new DynamicStructuredTool({
  name: 'compare_cn_us_macro',
  description: `对比中美宏观经济指标，分析两国经济走势差异。

  可对比指标：
  - GDP：经济增长
  - CPI：通货膨胀
  - 利率：货币政策
  - 失业率：就业市场

  适用场景：
  - 评估全球经济形势
  - 研究货币政策差异
  - 分析通胀趋势
  - 预测汇率走向`,
  schema: z.object({
    indicator: z
      .enum(['gdp', 'cpi', 'unemployment', 'interest_rate'])
      .describe('指标类型：gdp, cpi, unemployment, interest_rate'),
    years: z.number().default(5).describe('对比年数，默认5年'),
  }),
  func: async (input) => {
    // 这里需要同时调用 AkShare 和 OpenBB 的宏观数据接口
    // 简化版本，返回框架
    return `## 中美宏观经济对比

**对比指标**：${input.indicator.toUpperCase()}
**对比周期**：${input.years} 年

此功能需要同时集成：
- AkShare 宏观数据接口（中国数据）
- OpenBB 宏观数据接口（美国数据）

建议实现步骤：
1. 调用 AkShare 获取中国${input.indicator}数据
2. 调用 OpenBB 获取美国${input.indicator}数据
3. 按时间对齐数据
4. 计算差异和趋势
5. 生成对比图表

---
提示：可以使用已有的 getCPI, getGDP 等工具分别获取数据后手动对比`;
  },
});

/**
 * 辅助函数：格式化日期
 */
function formatDate(date: Date, format: 'cn' | 'us'): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  if (format === 'cn') {
    return `${year}${month}${day}`; // AkShare 格式：20260101
  } else {
    return `${year}-${month}-${day}`; // OpenBB 格式：2026-01-01
  }
}

/**
 * 辅助函数：评估相关性强度
 */
function getCorrelationStrength(correlation: number): string {
  const abs = Math.abs(correlation);
  if (abs >= 0.7) return '强相关';
  if (abs >= 0.4) return '中等相关';
  if (abs >= 0.2) return '弱相关';
  return '几乎无关';
}

/**
 * 辅助函数：生成解读
 */
function generateInterpretation(
  correlation: number,
  cnReturn: number,
  usReturn: number
): string {
  const lines: string[] = [];

  // 相关性解读
  if (Math.abs(correlation) >= 0.7) {
    lines.push(
      `✅ 两个标的呈现强相关性（${correlation > 0 ? '正相关' : '负相关'}），走势高度联动。`
    );
  } else if (Math.abs(correlation) >= 0.4) {
    lines.push(
      `⚠️ 两个标的呈现中等相关性，存在一定联动但不完全同步。`
    );
  } else {
    lines.push(
      `ℹ️ 两个标的相关性较弱，走势相对独立，可能受不同因素驱动。`
    );
  }

  // 表现对比解读
  const returnDiff = Math.abs(cnReturn - usReturn);
  if (returnDiff > 10) {
    lines.push(
      `📊 两个标的表现差异显著（相差${returnDiff.toFixed(2)}个百分点），可能存在套利或配置机会。`
    );
  } else if (returnDiff > 5) {
    lines.push(`📊 两个标的表现有一定差异，建议关注驱动因素。`);
  } else {
    lines.push(`📊 两个标的表现相近，可能受相似市场因素影响。`);
  }

  // 投资建议
  if (correlation > 0.7 && returnDiff < 5) {
    lines.push(
      `💡 建议：两个标的高度联动且表现相似，可作为分散投资的互补配置。`
    );
  } else if (correlation < 0.3) {
    lines.push(
      `💡 建议：两个标的相关性低，适合用于组合分散风险。`
    );
  }

  return lines.join('\n');
}

/**
 * 导出所有跨市场分析工具
 */
export const crossMarketTools = [compareCNUSMarketsTool, compareCNUSMacroTool];
