import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { marketService, MarketOverviewResponse, type MarketId } from '../services/marketService';

export interface UseMarketDataOptions {
  autoRefresh?: boolean;
  refreshInterval?: number;
  mockData?: boolean;
  market?: MarketId;
  timeoutMs?: number;
}

export interface UseMarketDataReturn {
  data: MarketOverviewResponse | null;
  loading: boolean;
  error: string | null;
  lastUpdate: string | null;
  refresh: () => void;
  isConnected: boolean;
  timedOut: boolean;
}

export const useMarketData = (options: UseMarketDataOptions = {}): UseMarketDataReturn => {
  const {
    autoRefresh = true,
    refreshInterval = 5000, // 5秒
    mockData = false,
    market = 'CN',
    timeoutMs = 8000, // 默认 8 秒超时（匹配腾讯财经 REQUEST_TIMEOUT）
  } = options;

  const [timedOut, setTimedOut] = useState(false);

  const { data, error, isLoading, isError, refetch } = useQuery<MarketOverviewResponse, Error>({
    queryKey: ['marketData', market, mockData],
    queryFn: async () => {
      if (mockData) {
        return marketService.generateMarketMockData(market);
      }
      const response = await marketService.getMarketOverview(market);
      if (response.success && response.data) {
        return response.data;
      }
      throw new Error(response.error || '获取数据失败');
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
    refetchOnWindowFocus: true,
  });

  // 超时兜底：仅控制展示（首次加载超时显示 0 值占位），不丢弃进行中的请求。
  // 数据到达后 isLoading 变 false、timedOut 复位，避免「数据一会有一会变 0」。
  useEffect(() => {
    if (!isLoading) {
      setTimedOut(false);
      return;
    }
    const timer = setTimeout(() => setTimedOut(true), timeoutMs);
    return () => clearTimeout(timer);
  }, [isLoading, timeoutMs]);

  return {
    data: data || null,
    loading: isLoading,
    error: error ? error.message : null,
    lastUpdate: data ? new Date().toISOString() : null,
    refresh: refetch,
    isConnected: !isError,
    timedOut,
  };
};
