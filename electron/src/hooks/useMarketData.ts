import { useState } from 'react';
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
    timeoutMs = 1000, // 默认 1 秒超时
  } = options;

  const [timedOut, setTimedOut] = useState(false);

  const { data, error, isLoading, isError, refetch } = useQuery<MarketOverviewResponse, Error>({
    queryKey: ['marketData', market, mockData],
    queryFn: async () => {
      setTimedOut(false);
      return await new Promise<MarketOverviewResponse>((resolve) => {
        const timer = setTimeout(() => {
          setTimedOut(true);
          resolve({ indices: [], lastUpdate: '', count: 0, sourceUsed: 'timeout' });
        }, timeoutMs);

        const done = (result: MarketOverviewResponse) => {
          clearTimeout(timer);
          resolve(result);
        };

        if (mockData) {
          done(marketService.generateMarketMockData(market));
          return;
        }

        marketService
          .getMarketOverview(market)
          .then((response) => {
            if (response.success && response.data) {
              done(response.data);
            } else {
              done({ indices: [], lastUpdate: '', count: 0, sourceUsed: 'error' });
            }
          })
          .catch(() => {
            done({ indices: [], lastUpdate: '', count: 0, sourceUsed: 'error' });
          });
      });
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
    refetchOnWindowFocus: true,
  });

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
