import axios, { AxiosInstance } from 'axios';
import { SERVICE_ENDPOINTS } from '../config/services';
import { authService } from '../features/auth/services/authService';

export interface FeatureDriverItem {
  name: string;
  category?: string;
  value?: number;
  impact: number;
  direction: 'positive' | 'negative';
}

export interface ModelConsensusItem {
  model_id: string;
  model_name: string;
  model_type: string;
  score: number;
  expected_return: number;
  rating: 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL';
  horizon: number;
}

export interface ForecastPoint {
  step: number;
  date: string;
  p10: number;
  p50: number;
  p90: number;
  predicted_price: number;
  upper_price: number;
  lower_price: number;
}

export interface SingleStockPredictionResponse {
  status: string;
  symbol: string;
  stock_name: string;
  model_id: string;
  model_name: string;
  model_type: string;
  as_of_date: string;
  current_price: number;
  horizon: number;
  predicted_score: number;
  expected_return: number;
  confidence: number;
  rating: 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL';
  p10_return: number;
  p50_return: number;
  p90_return: number;
  forecast_curve: ForecastPoint[];
  drivers: FeatureDriverItem[];
  consensus: ModelConsensusItem[];
  consensus_score: number;
  /** 'persisted'=真实持久化模型分数 | 'fallback'=无分数中性空态 | 'mock'=离线模拟 */
  data_source?: 'persisted' | 'fallback' | 'mock';
  error?: string | null;
}

export interface SingleStockPredictionRequest {
  symbol: string;
  model_id?: string;
  date?: string;
  horizon?: number;
  market?: string;
}

export interface KlineItem {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface AvailableModelOption {
  modelId: string;
  modelName: string;
  modelType: string;
  description?: string;
  accuracy?: number;
  isEnsemble?: boolean;
  hasInference?: boolean;
}

class InferenceCenterService {
  private get client(): AxiosInstance {
    const baseURL = (import.meta as any).env?.VITE_USER_API_URL || SERVICE_ENDPOINTS.API_GATEWAY || SERVICE_ENDPOINTS.USER_SERVICE;
    const client = axios.create({
      baseURL,
      timeout: 30000,
    });
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

  async getAvailableModels(market?: string): Promise<AvailableModelOption[]> {
    try {
      const params: Record<string, string> = {};
      if (market) params.market = market;
      const resp = await this.client.get('/research/models', { params });
      // 后端返回 {code:200, data:{models:[{modelId,name,framework,modelType,ic,hasInference}]}}
      const body = (resp.data ?? {}) as any;
      const items =
        body?.data?.models ??
        body?.data?.items ??
        body?.models ??
        body?.items ??
        [];
      return items.map((m: any) => ({
        modelId: m.modelId || m.model_id,
        modelName: m.name || m.modelName || m.model_name || m.modelId,
        modelType: m.modelType || m.model_type || '',
        description: m.description,
        accuracy: m.ic ?? m.accuracy ?? m.ic_value,
        hasInference: m.hasInference ?? m.has_inference ?? false,
      }));
    } catch (e) {
      console.warn('获取可用模型列表失败，使用默认列表:', e);
      return [
        { modelId: 'mdl_lightgbm_v2', modelName: 'LightGBM Alpha-158 增强模型', modelType: 'lightgbm', accuracy: 0.128 },
        { modelId: 'mdl_tft_v1', modelName: 'NativeTFT 时序融合变换器 (分位数)', modelType: 'nativetft', accuracy: 0.145 },
        { modelId: 'mdl_gru_ts_v1', modelName: 'Qlib GRU 循环神经网络', modelType: 'gru', accuracy: 0.115 },
        { modelId: 'mdl_stacking_ens', modelName: 'Stacking 异构多模型集成', modelType: 'stacking', accuracy: 0.158 },
      ];
    }
  }

  async getStockKline(symbol: string, days: number = 60): Promise<KlineItem[]> {
    try {
      const resp = await this.client.get<{ code: number; data: { items: KlineItem[] } }>(`/research/kline/${encodeURIComponent(symbol)}?days=${days}`);
      return resp.data?.data?.items || [];
    } catch (e) {
      console.warn('获取股票K线失败:', e);
      return [];
    }
  }

  async predictSingleStock(req: SingleStockPredictionRequest): Promise<SingleStockPredictionResponse> {
    const resp = await this.client.post<{ code?: number; data?: SingleStockPredictionResponse } | SingleStockPredictionResponse>('/research/predict-stock', req);
    if ((resp.data as any)?.data) {
      return (resp.data as any).data;
    }
    return resp.data as SingleStockPredictionResponse;
  }
}

export const inferenceCenterService = new InferenceCenterService();
