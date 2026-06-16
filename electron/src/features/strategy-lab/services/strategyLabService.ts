/**
 * Strategy Lab API client.
 *
 * Endpoints (engine service):
 *   POST  /api/v1/strategy-lab/run            — sync run (blocking)
 *   POST  /api/v1/strategy-lab/run/async      — async submit
 *   GET   /api/v1/strategy-lab/run/{id}/status — SSE progress stream
 *   GET   /api/v1/strategy-lab/run/{id}/result — final RunResult
 */

import axios, { AxiosInstance } from 'axios';
import { SERVICE_URLS } from '../../../config/services';
import { authService } from '../../auth/services/authService';
import type {
  StrategyLabProgressEvent,
  StrategyLabRunRequest,
  StrategyLabRunResult,
} from '../types';

const resolveBaseUrl = () =>
  `${String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '')}/api/v1/strategy-lab`;

const client: AxiosInstance = axios.create({
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

client.interceptors.request.use((config) => {
  config.baseURL = resolveBaseUrl();
  const token = authService.getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (resp) => resp.data,
  (error) => Promise.reject(error),
);

export const strategyLabService = {
  async runSync(req: StrategyLabRunRequest): Promise<StrategyLabRunResult> {
    return (await client.post('/run', req)) as unknown as StrategyLabRunResult;
  },

  async submit(req: StrategyLabRunRequest): Promise<{ run_id: string; status: string }> {
    return (await client.post('/run/async', req)) as unknown as { run_id: string; status: string };
  },

  async fetchResult(runId: string): Promise<StrategyLabRunResult> {
    return (await client.get(`/run/${runId}/result`)) as unknown as StrategyLabRunResult;
  },

  /** Day 11-12: 4-gate overfit detection report. */
  async runOverfitCheck(code: string, params?: Record<string, unknown>): Promise<{
    gate1?: { passed: boolean; score: number; note: string };
    gate2?: { passed: boolean; score: number; note: string };
    gate3?: { passed: boolean; score: number; note: string };
    gate4?: { passed: boolean; score: number; note: string };
    total_score: number;
    warnings: string[];
  }> {
    return (await client.post('/overfit-check', { code, params: params || {} })) as any;
  },

  /** Day 15: Translate SDK script → strategy template; returns saved strategy_name + id. */
  async translateToTemplate(code: string): Promise<{
    strategy_name: string;
    strategy_id: string;
    template: Record<string, unknown>;
  }> {
    return (await client.post('/translate', { code })) as any;
  },

  /** Day 16: Watch list management. */
  async addWatch(code: string, name: string): Promise<{ script_sha: string; registered: boolean }> {
    return (await client.post('/watch', { code, name })) as any;
  },

  async listWatch(): Promise<{ items: Array<{ script_sha: string; name: string; registered_at: string }> }> {
    return (await client.get('/watch')) as any;
  },

  async removeWatch(scriptSha: string): Promise<{ script_sha: string; registered: boolean }> {
    return (await client.delete(`/watch/${scriptSha}`)) as any;
  },

  async fetchSignals(): Promise<{
    generated_at: string | null;
    signals: Array<{
      strategy: string;
      script_sha: string;
      symbol: string;
      direction: 'BUY' | 'SELL';
      price?: number;
      qty?: number;
      reason?: string;
      date: string;
    }>;
    summary?: { watched: number; ok: number; failed: number; with_signal: number };
  }> {
    return (await client.get('/signals')) as any;
  },

  async runScanNow(lookbackDays = 7): Promise<{ generated_at: string; signals: any[]; summary: any }> {
    return (await client.post('/scan/run-now', null, { params: { lookback_days: lookbackDays } })) as any;
  },

  // ---------------------------------------------------------------------------
  // Strategy CRUD — delegates to /api/v1/strategies on the engine service
  // ---------------------------------------------------------------------------

  /** List user's saved strategies. */
  async listStrategies(): Promise<Array<{
    id: string; name: string; description: string; code: string;
    tags: string[]; language: string; created_at?: string; updated_at?: string;
  }>> {
    const base = String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '');
    const resp = await client.get(`${base}/api/v1/strategies`);
    const data = (resp as any)?.data ?? resp;
    const items = Array.isArray(data?.strategies) ? data.strategies
      : Array.isArray(data?.items) ? data.items
      : Array.isArray(data) ? data : [];
    return items.map((s: any) => ({
      id: String(s.strategy_id ?? s.id ?? ''),
      name: s.name ?? '',
      description: s.description ?? '',
      code: s.code ?? '',
      tags: s.tags ?? [],
      language: s.language ?? 'python',
      created_at: s.created_at,
      updated_at: s.updated_at,
    }));
  },

  /** Load a single strategy by id (with code). */
  async loadStrategy(strategyId: string): Promise<{
    id: string; name: string; description: string; code: string; tags: string[];
  }> {
    const base = String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '');
    const resp = await client.get(`${base}/api/v1/strategies/${strategyId}`, {
      params: { resolve_code: true },
    });
    const data = (resp as any)?.data ?? resp;
    return {
      id: String(data?.strategy_id ?? data?.id ?? strategyId),
      name: data?.name ?? '',
      description: data?.description ?? '',
      code: data?.code ?? '',
      tags: data?.tags ?? [],
    };
  },

  /** Save a new strategy. */
  async saveStrategy(name: string, code: string, description = '', tags: string[] = []): Promise<{
    id: string; name: string;
  }> {
    const base = String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '');
    const resp = await client.post(`${base}/api/v1/strategies`, {
      name,
      code,
      description,
      category: 'strategy_lab',
      author: '用户',
      tags,
      parameters: {},
    });
    const data = (resp as any)?.data ?? resp;
    return {
      id: String(data?.strategy_id ?? data?.id ?? ''),
      name: data?.name ?? name,
    };
  },

  /** Update an existing strategy. */
  async updateStrategy(strategyId: string, updates: { name?: string; code?: string; description?: string }): Promise<void> {
    const base = String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '');
    await client.put(`${base}/api/v1/strategies/${strategyId}`, updates);
  },

  /** Delete a strategy. */
  async deleteStrategy(strategyId: string): Promise<void> {
    const base = String(SERVICE_URLS.ENGINE_SERVICE || '').replace(/\/+$/, '');
    await client.delete(`${base}/api/v1/strategies/${strategyId}`);
  },

  /**
   * SSE poller — Server-Sent Events with token auth via query param fallback.
   * Returns a cleanup function. The browser EventSource cannot set Authorization
   * headers, so we poll the result endpoint and merge progress with one HTTP read.
   *
   * For simplicity in the Day-3 cut, we poll /result every 1s once we have a
   * run_id; once it's terminal we stop. This avoids the EventSource auth issue.
   */
  pollProgress(
    runId: string,
    onProgress: (evt: StrategyLabProgressEvent) => void,
    onTerminal: (result: StrategyLabRunResult | null) => void,
    intervalMs = 1000,
  ): () => void {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (cancelled) return;
      try {
        const result = await strategyLabService.fetchResult(runId);
        if (cancelled) return;
        if (result && (result.status === 'success' || result.status === 'failed' || result.status === 'cancelled')) {
          onTerminal(result);
          return;
        }
        onProgress({
          run_id: runId,
          phase: 'backtest',
          pct: 50,
          message: 'running…',
          detail: {},
          ts: Date.now() / 1000,
        });
      } catch (err: any) {
        // 404 — result not yet stored, keep polling
        if (err?.response?.status !== 404) {
          if (cancelled) return;
          onTerminal(null);
          return;
        }
        onProgress({
          run_id: runId,
          phase: 'queued',
          pct: 5,
          message: 'queued…',
          detail: {},
          ts: Date.now() / 1000,
        });
      }
      if (!cancelled) {
        timer = setTimeout(tick, intervalMs);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  },
};
