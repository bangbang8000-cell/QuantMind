import axios, { AxiosInstance } from 'axios';
import { authService } from '../features/auth/services/authService';
import { SERVICE_ENDPOINTS } from '../config/services';

export interface HubModelItem {
  id: string;
  author_username: string;
  name: string;
  description: string;
  market: string;
  algorithm: string;
  target_horizon: string;
  target_mode: string;
  test_ic: number;
  rank_ic: number;
  sharpe_ratio: number;
  annual_return: number;
  max_drawdown: number;
  calmar_ratio: number;
  psi: number;
  equity_curve?: Array<{ date: string; value: number; benchmark?: number }>;
  factors_summary?: string[] | { count: number; items?: string[] };
  file_size_bytes: number;
  visibility: string;
  status: string;
  is_verified: boolean;
  downloads_count: number;
  likes_count: number;
  created_at: string;
  updated_at: string;
}

export interface HubModelListResponse {
  total: number;
  page: number;
  page_size: number;
  items: HubModelItem[];
}

export interface CreateUploadTicketPayload {
  name: string;
  description?: string;
  market?: string;
  algorithm: string;
  target_horizon?: string;
  target_mode?: string;
  test_ic?: number;
  rank_ic?: number;
  sharpe_ratio?: number;
  annual_return?: number;
  max_drawdown?: number;
  calmar_ratio?: number;
  psi?: number;
  equity_curve?: any;
  factors_summary?: any;
  extra_metrics?: any;
  file_size_bytes?: number;
  visibility?: string;
}

export interface UploadTicketResponse {
  model_id: string;
  upload_url: string;
  cos_key: string;
  expire_in: number;
}

export interface DownloadTicketResponse {
  model_id: string;
  download_url: string;
  expire_in: number;
  file_size_bytes: number;
}

class ModelHubService {
  private axiosInstance: AxiosInstance;
  private readonly defaultQuantDBHost = 'https://quantdb.quantmind.cloud';

  constructor() {
    this.axiosInstance = axios.create({
      baseURL: this.getQuantDBApiHost(),
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' },
    });

    this.axiosInstance.interceptors.request.use((config) => {
      // 优先从 localStorage 提取用户配置的 QuantDB API Key
      const quantdbApiKey = localStorage.getItem('quantdb_api_key') || localStorage.getItem('quantdb_key');
      if (quantdbApiKey) {
        config.headers['X-API-Key'] = quantdbApiKey.trim();
      }

      // 如果未配置 QuantDB API Key，透传当前平台的 Bearer Token
      const token = authService.getAccessToken();
      if (token && !config.headers['Authorization']) {
        config.headers['Authorization'] = `Bearer ${token}`;
      }
      return config;
    });
  }

  private getQuantDBApiHost(): string {
    if (typeof window !== 'undefined') {
      const customHost = localStorage.getItem('quantdb_api_host');
      if (customHost && customHost.startsWith('http')) {
        return customHost.trim();
      }
    }
    return (import.meta as any).env?.VITE_QUANTDB_API_HOST || this.defaultQuantDBHost;
  }

  /**
   * 获取广场模型列表
   */
  async listModels(params: {
    market?: string;
    algorithm?: string;
    sort_by?: string;
    query?: string;
    author?: string;
    page?: number;
    page_size?: number;
  }): Promise<HubModelListResponse> {
    try {
      const resp = await this.axiosInstance.get('/api/v1/hub/models', {
        params: {
          market: params.market && params.market !== 'ALL' ? params.market : undefined,
          algorithm: params.algorithm && params.algorithm !== 'ALL' ? params.algorithm : undefined,
          sort_by: params.sort_by || 'sharpe',
          q: params.query || undefined,
          author: params.author || undefined,
          page: params.page || 1,
          page_size: params.page_size || 20,
        },
      });
      return resp.data;
    } catch (err: any) {
      console.warn('请求 QuantDB 模型广场失败，尝试使用本地网关回退:', err);
      // 回退使用统一网关
      const fallbackUrl = `${SERVICE_ENDPOINTS.API_GATEWAY}/api/v1/hub/models`;
      const fallbackResp = await axios.get(fallbackUrl, {
        params,
        headers: {
          Authorization: `Bearer ${authService.getAccessToken() || ''}`,
        },
      }).catch(() => null);

      if (fallbackResp?.data) {
        return fallbackResp.data;
      }
      throw err;
    }
  }

  /**
   * 获取单个模型详情（含净值曲线与特征列表）
   */
  async getModelDetail(modelId: string): Promise<HubModelItem> {
    const resp = await this.axiosInstance.get(`/api/v1/hub/models/${modelId}`);
    return resp.data;
  }

  /**
   * 申请上传直传凭证
   */
  async createUploadTicket(payload: CreateUploadTicketPayload): Promise<UploadTicketResponse> {
    const resp = await this.axiosInstance.post('/api/v1/hub/models/upload-ticket', payload);
    return resp.data;
  }

  /**
   * 确认上传完成并激活模型
   */
  async publishModel(modelId: string): Promise<{ message: string; model_id: string }> {
    const resp = await this.axiosInstance.post(`/api/v1/hub/models/${modelId}/publish`);
    return resp.data;
  }

  /**
   * 获取下载直链
   */
  async getDownloadTicket(modelId: string): Promise<DownloadTicketResponse> {
    const resp = await this.axiosInstance.get(`/api/v1/hub/models/${modelId}/download-ticket`);
    return resp.data;
  }

  /**
   * 为模型点赞
   */
  async likeModel(modelId: string): Promise<{ message: string; model_id: string }> {
    const resp = await this.axiosInstance.post(`/api/v1/hub/models/${modelId}/like`);
    return resp.data;
  }

  /**
   * 下架或删除模型
   */
  async deleteModel(modelId: string): Promise<{ message: string; model_id: string }> {
    const resp = await this.axiosInstance.delete(`/api/v1/hub/models/${modelId}`);
    return resp.data;
  }
}

export const modelHubService = new ModelHubService();
