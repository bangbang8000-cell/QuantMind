/**
 * OpenBB LangChain 工具集
 *
 * 为 Dexter AI 代理提供全球金融市场数据访问能力
 * 包括美股、加密货币、期权、宏观经济数据
 */

import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import {
  getEquityHistorical,
  getEquityQuote,
  getEquityProfile,
  searchEquity,
  getGDP,
  getCPI,
  getUnemployment,
  getInterestRate,
  getCryptoHistorical,
  getCryptoQuote,
  getOptionsChains,
  getOptionsExpirations,
  formatToolResult,
} from './openbb-api';

/**
 * 工具 1: 获取美股历史数据
 */
export const getUSStockHistoricalTool = new DynamicStructuredTool({
  name: 'get_us_stock_historical',
  description: `获取美股历史价格数据，支持纽交所（NYSE）、纳斯达克（NASDAQ）等美国市场股票。

  适用场景：
  - 分析美股价格走势
  - 获取历史 OHLCV 数据（开盘价、最高价、最低价、收盘价、成交量）
  - 技术分析和回测

  常用股票代码示例：
  - AAPL: 苹果公司
  - TSLA: 特斯拉
  - MSFT: 微软
  - GOOGL: 谷歌
  - AMZN: 亚马逊
  - NVDA: 英伟达`,
  schema: z.object({
    symbol: z.string().describe('美股代码，如 AAPL, TSLA, MSFT'),
    startDate: z
      .string()
      .optional()
      .describe('开始日期，格式：YYYY-MM-DD，默认为30天前'),
    endDate: z
      .string()
      .optional()
      .describe('结束日期，格式：YYYY-MM-DD，默认为今天'),
    interval: z
      .enum(['1d', '1h', '5m', '15m', '30m'])
      .default('1d')
      .describe('数据间隔：1d(日线), 1h(小时), 5m(5分钟)'),
  }),
  func: async (input) => {
    const result = await getEquityHistorical(input.symbol, {
      startDate: input.startDate,
      endDate: input.endDate,
      interval: input.interval,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data, [
      'date',
      'open',
      'high',
      'low',
      'close',
      'volume',
    ]);
  },
});

/**
 * 工具 2: 获取美股实时报价
 */
export const getUSStockQuoteTool = new DynamicStructuredTool({
  name: 'get_us_stock_quote',
  description: `获取美股实时报价，包括最新价格、涨跌幅、成交量、市值等信息。

  适用场景：
  - 获取当前股价
  - 查看实时涨跌幅
  - 了解市值和交易量`,
  schema: z.object({
    symbol: z.string().describe('美股代码，如 AAPL, TSLA'),
  }),
  func: async (input) => {
    const result = await getEquityQuote(input.symbol);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 3: 获取公司基本信息
 */
export const getCompanyProfileTool = new DynamicStructuredTool({
  name: 'get_company_profile',
  description: `获取美国上市公司的基本信息，包括公司名称、行业、市值、员工数、公司描述等。

  适用场景：
  - 了解公司基本情况
  - 研究公司所在行业
  - 获取公司规模信息`,
  schema: z.object({
    symbol: z.string().describe('美股代码'),
  }),
  func: async (input) => {
    const result = await getEquityProfile(input.symbol);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 4: 搜索美股股票
 */
export const searchUSStockTool = new DynamicStructuredTool({
  name: 'search_us_stock',
  description: `根据公司名称或股票代码搜索美股股票，返回匹配的股票列表。

  适用场景：
  - 不知道股票代码，通过公司名称查找
  - 模糊搜索股票
  - 发现相关公司`,
  schema: z.object({
    query: z.string().describe('搜索关键词，如公司名称或股票代码'),
    limit: z.number().default(10).describe('返回结果数量，默认10'),
  }),
  func: async (input) => {
    const result = await searchEquity(input.query, input.limit);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data, ['symbol', 'name', 'exchange']);
  },
});

/**
 * 工具 5: 获取 GDP 数据
 */
export const getGDPTool = new DynamicStructuredTool({
  name: 'get_gdp',
  description: `获取国家 GDP（国内生产总值）数据，支持美国及全球主要国家。

  适用场景：
  - 分析经济增长趋势
  - 比较不同国家经济规模
  - 宏观经济研究

  支持国家：
  - united_states: 美国
  - china: 中国
  - japan: 日本
  - germany: 德国
  - 等`,
  schema: z.object({
    country: z
      .string()
      .default('united_states')
      .describe('国家代码，默认美国'),
    startDate: z.string().optional().describe('开始日期，格式：YYYY-MM-DD'),
    endDate: z.string().optional().describe('结束日期，格式：YYYY-MM-DD'),
  }),
  func: async (input) => {
    const result = await getGDP({
      country: input.country,
      startDate: input.startDate,
      endDate: input.endDate,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 6: 获取 CPI 数据
 */
export const getCPITool = new DynamicStructuredTool({
  name: 'get_cpi',
  description: `获取 CPI（消费者价格指数）数据，用于衡量通货膨胀水平。

  适用场景：
  - 分析通货膨胀趋势
  - 评估货币购买力变化
  - 宏观经济研究`,
  schema: z.object({
    country: z
      .string()
      .default('united_states')
      .describe('国家代码，默认美国'),
    startDate: z.string().optional().describe('开始日期'),
    endDate: z.string().optional().describe('结束日期'),
  }),
  func: async (input) => {
    const result = await getCPI({
      country: input.country,
      startDate: input.startDate,
      endDate: input.endDate,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 7: 获取失业率数据
 */
export const getUnemploymentTool = new DynamicStructuredTool({
  name: 'get_unemployment',
  description: `获取失业率数据，反映劳动力市场健康状况。

  适用场景：
  - 评估就业市场状况
  - 预测经济周期
  - 分析劳动力趋势`,
  schema: z.object({
    country: z
      .string()
      .default('united_states')
      .describe('国家代码，默认美国'),
    startDate: z.string().optional().describe('开始日期'),
    endDate: z.string().optional().describe('结束日期'),
  }),
  func: async (input) => {
    const result = await getUnemployment({
      country: input.country,
      startDate: input.startDate,
      endDate: input.endDate,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 8: 获取利率数据
 */
export const getInterestRateTool = new DynamicStructuredTool({
  name: 'get_interest_rate',
  description: `获取基准利率数据，包括美联储利率等。

  适用场景：
  - 分析货币政策
  - 预测利率走势
  - 评估融资成本`,
  schema: z.object({
    country: z
      .string()
      .default('united_states')
      .describe('国家代码，默认美国'),
    startDate: z.string().optional().describe('开始日期'),
    endDate: z.string().optional().describe('结束日期'),
  }),
  func: async (input) => {
    const result = await getInterestRate({
      country: input.country,
      startDate: input.startDate,
      endDate: input.endDate,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 9: 获取加密货币历史数据
 */
export const getCryptoHistoricalTool = new DynamicStructuredTool({
  name: 'get_crypto_historical',
  description: `获取加密货币历史价格数据。

  支持币种：
  - BTC: 比特币
  - ETH: 以太坊
  - BNB: 币安币
  - SOL: Solana
  - XRP: 瑞波币

  适用场景：
  - 分析加密货币价格走势
  - 技术分析
  - 市场研究`,
  schema: z.object({
    symbol: z.string().describe('加密货币代码，如 BTC, ETH'),
    startDate: z.string().optional().describe('开始日期'),
    endDate: z.string().optional().describe('结束日期'),
    interval: z
      .enum(['1d', '1h', '5m', '15m', '30m'])
      .default('1d')
      .describe('数据间隔'),
  }),
  func: async (input) => {
    const result = await getCryptoHistorical(input.symbol, {
      startDate: input.startDate,
      endDate: input.endDate,
      interval: input.interval,
    });

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data, [
      'date',
      'open',
      'high',
      'low',
      'close',
      'volume',
    ]);
  },
});

/**
 * 工具 10: 获取加密货币实时报价
 */
export const getCryptoQuoteTool = new DynamicStructuredTool({
  name: 'get_crypto_quote',
  description: `获取加密货币实时报价，包括当前价格、24小时涨跌幅、成交量等。

  适用场景：
  - 查看实时币价
  - 了解短期波动
  - 市场情绪分析`,
  schema: z.object({
    symbol: z.string().describe('加密货币代码，如 BTC, ETH'),
  }),
  func: async (input) => {
    const result = await getCryptoQuote(input.symbol);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 11: 获取期权链数据
 */
export const getOptionsChainsTool = new DynamicStructuredTool({
  name: 'get_options_chains',
  description: `获取美股期权链数据，包括看涨和看跌期权的执行价格、权利金、隐含波动率等。

  适用场景：
  - 期权交易策略分析
  - 隐含波动率分析
  - 市场情绪评估`,
  schema: z.object({
    symbol: z.string().describe('美股代码'),
    expiration: z
      .string()
      .optional()
      .describe('到期日，格式：YYYY-MM-DD，不填则返回最近到期日'),
  }),
  func: async (input) => {
    const result = await getOptionsChains(input.symbol, input.expiration);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 工具 12: 获取期权到期日列表
 */
export const getOptionsExpirationsTool = new DynamicStructuredTool({
  name: 'get_options_expirations',
  description: `获取指定股票所有可交易的期权到期日列表。

  适用场景：
  - 查看可用的期权合约
  - 选择合适的到期日
  - 期权策略规划`,
  schema: z.object({
    symbol: z.string().describe('美股代码'),
  }),
  func: async (input) => {
    const result = await getOptionsExpirations(input.symbol);

    if (result.status === 'error') {
      return `错误：${result.message}`;
    }

    return formatToolResult(result.data);
  },
});

/**
 * 导出所有 OpenBB 工具
 */
export const openbbTools = [
  getUSStockHistoricalTool,
  getUSStockQuoteTool,
  getCompanyProfileTool,
  searchUSStockTool,
  getGDPTool,
  getCPITool,
  getUnemploymentTool,
  getInterestRateTool,
  getCryptoHistoricalTool,
  getCryptoQuoteTool,
  getOptionsChainsTool,
  getOptionsExpirationsTool,
];
