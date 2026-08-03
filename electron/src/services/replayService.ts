/**
 * replayService.ts — 时光回放 API 客户端
 *
 * 沿用 realTradingService.ts 的约定：
 * - axios + authService token 注入
 * - SERVICE_URLS.TRADING 基础路径
 */

import axios from 'axios';
import { SERVICE_ENDPOINTS } from '../config/services';
import { authService } from '../features/auth/services/authService';

// SERVICE_ENDPOINTS.API_GATEWAY 已含 /api/v1，后端路由前缀为 /api/v1/replay
const BASE = `${SERVICE_ENDPOINTS.API_GATEWAY}/replay`;

function getHeaders() {
    const token = authService.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ReplaySession {
    session_id: string;
    name: string;
    status: 'creating' | 'generating' | 'ready' | 'stepping' | 'finished' | 'failed' | 'discarded';
    model_id: string | null;
    initial_cash: number;
    start_date: string;
    end_date: string;
    cursor_date: string | null;
    next_date: string | null;
    sessions_total: number;
    sessions_done: number;
    auto_trade: boolean;
    stop_loss_pct: number | null;
    signal_progress: {
        done?: number;
        total?: number;
        total_signals?: number;
        current?: string;
    };
    error_message: string | null;
}

export interface StepResult {
    trade_date: string;
    signal_count: number;
    filled: Array<{
        symbol: string;
        side: string;
        quantity: number;
        price: number;
        total_fee: number;
        reason: string;
    }>;
    rejected: Array<{
        symbol: string;
        side: string;
        reason: string;
    }>;
    stop_loss_fills: Array<{
        symbol: string;
        quantity: number;
        price: number;
        stop_price: number;
        total_fee: number;
        gap_down: boolean;
    }>;
    account: {
        cash: number;
        market_value: number;
        total_asset: number;
        positions: Record<string, {
            volume: number;
            price: number;
            cost: number;
            market_value: number;
            available_volume: number;
        }>;
    };
    snapshot: {
        trade_date: string;
        cash: number;
        market_value: number;
        total_asset: number;
        day_pnl: number;
        cum_pnl: number;
        position_count: number;
    };
    error: string | null;
}

export interface CreateSessionParams {
    name?: string;
    model_id?: string;
    strategy_params?: Record<string, unknown>;
    initial_cash?: number;
    start_date: string;
    end_date: string;
    auto_trade?: boolean;
    stop_loss_pct?: number | null;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export async function listSessions(): Promise<ReplaySession[]> {
    const { data } = await axios.get(BASE + '/sessions', { headers: getHeaders() });
    return data;
}

export async function getSession(sessionId: string): Promise<ReplaySession> {
    const { data } = await axios.get(`${BASE}/sessions/${sessionId}`, { headers: getHeaders() });
    return data;
}

export async function createSession(params: CreateSessionParams): Promise<ReplaySession> {
    const { data } = await axios.post(BASE + '/sessions', params, { headers: getHeaders() });
    return data;
}

export async function stepSession(sessionId: string): Promise<StepResult> {
    const { data } = await axios.post(`${BASE}/sessions/${sessionId}/step`, {}, { headers: getHeaders() });
    return data;
}

export async function deleteSession(sessionId: string): Promise<void> {
    await axios.delete(`${BASE}/sessions/${sessionId}`, { headers: getHeaders() });
}
