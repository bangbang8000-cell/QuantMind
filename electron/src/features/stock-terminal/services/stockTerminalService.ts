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
    q?: string;
    page?: number;
    page_size?: number;
  }): Promise<StockListResponse> {
    const resp = await this.client.get('/stock-terminal/list', { params });
    return resp.data?.data ?? { total: 0, page: 1, page_size: 100, trade_date: '', items: [] };
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
}

export const stockTerminalService = new StockTerminalService();
