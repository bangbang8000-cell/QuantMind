/** 个股终端 API 服务 */

import axios, { AxiosInstance } from 'axios';
import { SERVICE_ENDPOINTS } from '../../../config/services';
import { authService } from '../../auth/services/authService';
import { KlineBar, StockListResponse, StockProfile } from '../types';

class StockTerminalService {
  private get client(): AxiosInstance {
    const baseURL = (import.meta as any).env?.VITE_USER_API_URL || SERVICE_ENDPOINTS.API_GATEWAY || SERVICE_ENDPOINTS.USER_SERVICE;
    const client = axios.create({ baseURL, timeout: 30000 });
    client.interceptors.request.use((config) => {
      const token = authService.getAccessToken();
      if (token) {
        if (config.headers && typeof config.headers.set === 'function') {
          config.headers.set('Authorization', `Bearer ${token}`);
        } else if (config.headers) {
          config.headers['Authorization'] = `Bearer ${token}`;
        }
      }
      return config;
    });
    return client;
  }

  async getStockList(params: {
    market?: string;
    industry?: string;
    concept?: string;
    q?: string;
    date?: string;
    score_min?: number;
    model?: string;
    page?: number;
    page_size?: number;
  }): Promise<StockListResponse> {
    const resp = await this.client.get('/stock-terminal/list', { params });
    return resp.data?.data ?? { total: 0, page: 1, page_size: 100, trade_date: '', items: [] };
  }

  async getConcepts(): Promise<string[]> {
    try {
      const resp = await this.client.get('/stock-terminal/concepts');
      return resp.data?.data?.concepts ?? [];
    } catch {
      return [];
    }
  }

  async getIndustries(): Promise<string[]> {
    const resp = await this.client.get('/stock-terminal/industries');
    return resp.data?.data?.industries ?? [];
  }

  async getProfile(symbol: string): Promise<StockProfile | null> {
    try {
      const resp = await this.client.get('/stock-terminal/profile', { params: { symbol } });
      return resp.data?.data ?? null;
    } catch {
      return null;
    }
  }

  async getDailyKline(symbol: string, days = 500): Promise<KlineBar[]> {
    try {
      const resp = await this.client.get('/market/kline', {
        params: { symbol, market: 'A', days },
      });
      const items = resp.data?.data?.items ?? [];
      return items.map((it: any) => ({
        date: String(it.date ?? '').slice(0, 10),
        open: Number(it.open),
        high: Number(it.high),
        low: Number(it.low),
        close: Number(it.close),
        volume: it.volume != null ? Number(it.volume) : null,
        amount: it.amount != null ? Number(it.amount) : null,
      })).filter((b: KlineBar) => b.date && Number.isFinite(b.close));
    } catch {
      return [];
    }
  }

  async getIndexKline(symbol: string, days = 500): Promise<{ date: string; close: number }[]> {
    try {
      const resp = await this.client.get('/market/index-kline', {
        params: { symbol, days },
      });
      const data = resp.data?.data ?? {};
      const dates: string[] = data.dates ?? [];
      const closes: number[] = data.close ?? [];
      return dates.map((d, i) => ({ date: String(d).slice(0, 10), close: Number(closes[i]) }))
        .filter(x => x.date && Number.isFinite(x.close));
    } catch {
      return [];
    }
  }

  async getMinuteKline(symbol: string, freq: 'min5' | 'min1', days = 10): Promise<{ items: KlineBar[]; available: boolean }> {
    try {
      const resp = await this.client.get('/stock-terminal/minute', { params: { symbol, freq, days } });
      const data = resp.data?.data ?? {};
      const items = (data.items ?? []).map((it: any) => ({
        date: String(it.date ?? ''),
        open: Number(it.open),
        high: Number(it.high),
        low: Number(it.low),
        close: Number(it.close),
        volume: it.volume != null ? Number(it.volume) : null,
        amount: it.amount != null ? Number(it.amount) : null,
      }));
      return { items, available: !!data.available };
    } catch {
      return { items: [], available: false };
    }
  }

  async getFinancials(symbol: string, limit = 8): Promise<FinancialsResponse> {
    try {
      const resp = await this.client.get('/stock-terminal/financials', { params: { symbol, limit } });
      return resp.data?.data ?? { symbol, periods: [], income: [], balance: [], cashflow: [], per_share: [] };
    } catch {
      return { symbol, periods: [], income: [], balance: [], cashflow: [], per_share: [] };
    }
  }

  async getSeries(symbol: string, group: string, years = 3): Promise<SeriesResponse> {
    try {
      const resp = await this.client.get('/stock-terminal/series', { params: { symbol, group, years } });
      return resp.data?.data ?? { dates: [], columns: {} };
    } catch {
      return { dates: [], columns: {} };
    }
  }

  async getNews(symbol: string): Promise<{ items: any[]; available: boolean }> {
    try {
      const resp = await this.client.get('/stock-terminal/news', { params: { symbol } });
      return resp.data?.data ?? { items: [], available: false };
    } catch {
      return { items: [], available: false };
    }
  }

  async getAiBacktest(symbol: string, hint = ''): Promise<any> {
    const resp = await this.client.get('/stock-terminal/ai-backtest', { params: { symbol, hint }, timeout: 60000 });
    return resp.data?.data;
  }

  async getChartBacktest(symbol: string, buyExpr: string, sellExpr: string, days = 500): Promise<any> {
    const resp = await this.client.get('/stock-terminal/chart-backtest', {
      params: { symbol, buy_expr: buyExpr, sell_expr: sellExpr, days },
      timeout: 60000,
    });
    return resp.data?.data;
  }

  async getSignalOverlay(symbol: string, days = 250): Promise<Record<string, { date: string; fusion: number | null; side: string }[]>> {
    try {
      const resp = await this.client.get('/stock-terminal/signal-overlay', { params: { symbol, days } });
      return resp.data?.data?.series ?? {};
    } catch {
      return {};
    }
  }

  async getTags(symbol: string): Promise<{ tags: any[]; presets: any[] }> {
    try {
      const resp = await this.client.get('/stock-terminal/tags', { params: { symbol }, timeout: 30000 });
      return resp.data?.data ?? { tags: [], presets: [] };
    } catch {
      return { tags: [], presets: [] };
    }
  }

  async getTagStocks(tagId: string, limit = 30): Promise<any[]> {
    try {
      const resp = await this.client.get(`/stock-terminal/tags/${tagId}/stocks`, { params: { limit }, timeout: 30000 });
      return resp.data?.data?.items ?? [];
    } catch {
      return [];
    }
  }

  async getDividends(symbol: string): Promise<DividendItem[]> {
    try {
      const resp = await this.client.get('/stock-terminal/dividends', { params: { symbol } });
      return resp.data?.data?.items ?? [];
    } catch {
      return [];
    }
  }
}

export interface FinRecord { period: string; items: Record<string, number | null>; }
export interface FinancialsResponse {
  symbol: string;
  periods: string[];
  income: FinRecord[];
  balance: FinRecord[];
  cashflow: FinRecord[];
  per_share: FinRecord[];
}
export interface SeriesResponse { dates: string[]; columns: Record<string, (number | null)[]>; }
export interface DividendItem {
  date: string; interest: number | null; stock_bonus: number | null;
  stock_gift: number | null; gugai: number | null; dr: number | null;
}

export const stockTerminalService = new StockTerminalService();
