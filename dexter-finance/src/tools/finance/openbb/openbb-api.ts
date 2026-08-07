/**
 * OpenBB API 客户端
 *
 * 提供对 OpenBB 服务的 TypeScript 访问接口
 * 支持美股、加密货币、期权、宏观经济数据
 */

const OPENBB_API_URL = process.env.OPENBB_API_URL || 'http://localhost:8001';

/**
 * 标准 API 响应格式
 */
export interface OpenBBApiResponse {
  status: 'success' | 'error';
  service: 'openbb';
  data?: any;
  message?: string;
  error_type?: string;
  meta?: Record<string, any>;
  context?: Record<string, any>;
}

/**
 * 美股历史数据选项
 */
export interface EquityHistoricalOptions {
  startDate?: string;
  endDate?: string;
  interval?: '1d' | '1h' | '5m' | '15m' | '30m';
}

/**
 * 宏观经济数据选项
 */
export interface MacroOptions {
  country?: string;
  startDate?: string;
  endDate?: string;
}

/**
 * 加密货币历史数据选项
 */
export interface CryptoHistoricalOptions {
  startDate?: string;
  endDate?: string;
  interval?: '1d' | '1h' | '5m' | '15m' | '30m';
}

/**
 * 获取美股历史数据
 */
export async function getEquityHistorical(
  symbol: string,
  options?: EquityHistoricalOptions
): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/equity/historical/${symbol}`);

  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }
  if (options?.interval) {
    url.searchParams.append('interval', options.interval);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取美股实时报价
 */
export async function getEquityQuote(symbol: string): Promise<OpenBBApiResponse> {
  const url = `${OPENBB_API_URL}/equity/quote/${symbol}`;
  const response = await fetch(url);
  return response.json();
}

/**
 * 获取公司基本信息
 */
export async function getEquityProfile(symbol: string): Promise<OpenBBApiResponse> {
  const url = `${OPENBB_API_URL}/equity/profile/${symbol}`;
  const response = await fetch(url);
  return response.json();
}

/**
 * 搜索美股股票
 */
export async function searchEquity(
  query: string,
  limit: number = 10
): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/equity/search`);
  url.searchParams.append('query', query);
  url.searchParams.append('limit', limit.toString());

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取 GDP 数据
 */
export async function getGDP(options?: MacroOptions): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/macro/gdp`);

  if (options?.country) {
    url.searchParams.append('country', options.country);
  }
  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取 CPI 数据
 */
export async function getCPI(options?: MacroOptions): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/macro/cpi`);

  if (options?.country) {
    url.searchParams.append('country', options.country);
  }
  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取失业率数据
 */
export async function getUnemployment(options?: MacroOptions): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/macro/unemployment`);

  if (options?.country) {
    url.searchParams.append('country', options.country);
  }
  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取利率数据
 */
export async function getInterestRate(options?: MacroOptions): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/macro/interest-rate`);

  if (options?.country) {
    url.searchParams.append('country', options.country);
  }
  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取加密货币历史数据
 */
export async function getCryptoHistorical(
  symbol: string,
  options?: CryptoHistoricalOptions
): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/crypto/historical/${symbol}`);

  if (options?.startDate) {
    url.searchParams.append('start_date', options.startDate);
  }
  if (options?.endDate) {
    url.searchParams.append('end_date', options.endDate);
  }
  if (options?.interval) {
    url.searchParams.append('interval', options.interval);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取加密货币实时报价
 */
export async function getCryptoQuote(symbol: string): Promise<OpenBBApiResponse> {
  const url = `${OPENBB_API_URL}/crypto/quote/${symbol}`;
  const response = await fetch(url);
  return response.json();
}

/**
 * 获取期权链数据
 */
export async function getOptionsChains(
  symbol: string,
  expiration?: string
): Promise<OpenBBApiResponse> {
  const url = new URL(`${OPENBB_API_URL}/options/chains/${symbol}`);

  if (expiration) {
    url.searchParams.append('expiration', expiration);
  }

  const response = await fetch(url.toString());
  return response.json();
}

/**
 * 获取期权到期日列表
 */
export async function getOptionsExpirations(symbol: string): Promise<OpenBBApiResponse> {
  const url = `${OPENBB_API_URL}/options/expirations/${symbol}`;
  const response = await fetch(url);
  return response.json();
}

/**
 * 格式化工具结果为可读字符串
 */
export function formatToolResult(data: any, fields?: string[]): string {
  if (!data || data.length === 0) {
    return '未找到数据';
  }

  // 如果数据是数组，格式化为表格
  if (Array.isArray(data)) {
    const sample = data.slice(0, 5); // 只显示前5条
    const hasMore = data.length > 5;

    const formatted = sample.map((item: any) => {
      if (fields) {
        const filtered: any = {};
        fields.forEach(field => {
          if (field in item) {
            filtered[field] = item[field];
          }
        });
        return JSON.stringify(filtered, null, 2);
      }
      return JSON.stringify(item, null, 2);
    }).join('\n---\n');

    const suffix = hasMore ? `\n\n... 共 ${data.length} 条记录` : '';
    return formatted + suffix;
  }

  return JSON.stringify(data, null, 2);
}
