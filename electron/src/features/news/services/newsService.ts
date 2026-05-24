/**
 * 资讯源服务 — 调用 QuantMind 后端的 /api/v1/news 代理
 * 后端再代理到 Huntly (lcomplete/huntly:latest)
 */

import axios from 'axios';
import { SERVICE_ENDPOINTS } from '../../../config/services';
import { authService } from '../../auth/services/authService';

const apiClient = axios.create({ timeout: 30000 });

apiClient.interceptors.request.use((config) => {
  config.baseURL = SERVICE_ENDPOINTS.USER_SERVICE;
  const token = authService.getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface NewsSource {
  source_id: number;
  source_name: string;
  subscribe_url?: string;
  type?: string;
  folder_id: number;
  folder_name: string;
  site_avatar_url?: string;
  unread_count?: number;
}

export interface NewsFolder {
  folder_id: number;
  folder_name: string;
  source_count: number;
  unread_count: number;
}

export interface NewsArticle {
  id: number;
  title: string;
  summary?: string;
  url?: string;
  source_id?: number;
  source_name?: string;
  folder_id?: number;
  published_at?: string;
  read: boolean;
  starred: boolean;
  is_financial_event: boolean;
  thumbnail?: string;
}

export interface NewsArticleDetail extends NewsArticle {
  content?: string;
  content_html?: string;
}

export interface NewsHealthInfo {
  huntly_status: 'up' | 'down' | 'unreachable';
  huntly_http_code?: number;
  huntly_base_url: string;
  error?: string;
}

class NewsService {
  async health(): Promise<NewsHealthInfo> {
    const r = await apiClient.get<NewsHealthInfo>('/news/health');
    return (r as any).data ?? (r as any);
  }

  async listSources(): Promise<{ sources: NewsSource[]; folders: NewsFolder[] }> {
    const r = await apiClient.get<{ sources: NewsSource[]; folders: NewsFolder[] }>('/news/sources');
    const body = (r as any).data ?? (r as any);
    return { sources: body.sources ?? [], folders: body.folders ?? [] };
  }

  async refreshSource(source_id: number): Promise<void> {
    await apiClient.post(`/news/sources/${source_id}/refresh`);
  }

  async listArticles(params: {
    source_id?: number;
    folder_id?: number;
    keyword?: string;
    only_financial_event?: boolean;
    page?: number;
    page_size?: number;
  } = {}): Promise<{
    articles: NewsArticle[];
    total: number;
    page: number;
    page_size: number;
    latest_published_at?: string;
    server_time?: string;
  }> {
    const r = await apiClient.get('/news/articles', { params });
    return (r as any).data ?? (r as any);
  }

  async getArticle(id: number): Promise<NewsArticleDetail> {
    const r = await apiClient.get<NewsArticleDetail>(`/news/articles/${id}`);
    return (r as any).data ?? (r as any);
  }

  async toggleStar(id: number, starred: boolean): Promise<void> {
    await apiClient.post(`/news/articles/${id}/star`, null, { params: { starred } });
  }

  async markRead(id: number, read: boolean): Promise<void> {
    await apiClient.post(`/news/articles/${id}/read`, null, { params: { read } });
  }
}

export const newsService = new NewsService();
