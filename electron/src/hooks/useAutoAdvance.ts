/**
 * useAutoAdvance — 时光回放自动推进 hook（R5）
 *
 * 串行调 stepSession（不能并发，服务端有 409 防连点），4 档速度：
 * - 慢 2000ms
 * - 中 1000ms
 * - 快 300ms
 * - 极速 0（仅受 setTimeout 下限影响）
 *
 * 状态机：idle | running | paused | error | done
 * 错误：非 2xx 或 result.error 非空 → 立即停并标 error
 * 卸载：useRef 标记 abort，循环真正停止
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import type { ReplaySession, StepResult } from '../services/replayService';
import { stepSession, getSession } from '../services/replayService';

export type AutoAdvanceSpeed = 'slow' | 'medium' | 'fast' | 'instant';
export type AutoAdvanceState = 'idle' | 'running' | 'paused' | 'error' | 'done';

const SPEED_MS: Record<AutoAdvanceSpeed, number> = {
    slow: 2000,
    medium: 1000,
    fast: 300,
    instant: 0,
};

export interface DailyRecord {
    trade_date: string;
    fill_count: number;
    day_pnl: number;
    cum_pnl: number;
    rejected: number;
    error?: string;
}

export interface UseAutoAdvanceOptions {
    /** 初始速度 */
    speed?: AutoAdvanceSpeed;
    /** 逐日结果回调 */
    onDay?: (record: DailyRecord) => void;
    /** 全部完成回调 */
    onDone?: (records: DailyRecord[]) => void;
    /** 错误回调（用于 UI 提示） */
    onError?: (err: Error) => void;
}

export interface UseAutoAdvanceResult {
    state: AutoAdvanceState;
    speed: AutoAdvanceSpeed;
    setSpeed: (s: AutoAdvanceSpeed) => void;
    records: DailyRecord[];
    progress: { done: number; total: number };
    errorMessage: string | null;
    start: (session: ReplaySession) => void;
    pause: () => void;
    resume: () => void;
    stop: () => void;
}

export function useAutoAdvance(opts: UseAutoAdvanceOptions = {}): UseAutoAdvanceResult {
    const { onDay, onDone, onError, speed: initialSpeed = 'medium' } = opts;

    const [state, setState] = useState<AutoAdvanceState>('idle');
    const [speed, setSpeed] = useState<AutoAdvanceSpeed>(initialSpeed);
    const [records, setRecords] = useState<DailyRecord[]>([]);
    const [progress, setProgress] = useState({ done: 0, total: 0 });
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const sessionIdRef = useRef<string | null>(null);
    const abortRef = useRef(false);
    const pausedRef = useRef(false);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const recordsRef = useRef<DailyRecord[]>([]);
    const progressRef = useRef({ done: 0, total: 0 });

    const clearTimer = () => {
        if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
        }
    };

    const start = useCallback((session: ReplaySession) => {
        if (state === 'running') return;
        sessionIdRef.current = session.session_id;
        abortRef.current = false;
        pausedRef.current = false;
        const initialProgress = {
            done: session.sessions_done,
            total: session.sessions_total,
        };
        recordsRef.current = [];
        progressRef.current = initialProgress;
        setRecords([]);
        setProgress(initialProgress);
        setErrorMessage(null);
        setState('running');
    }, [state]);

    const pause = useCallback(() => {
        if (state !== 'running') return;
        pausedRef.current = true;
        setState('paused');
        clearTimer();
    }, [state]);

    const resume = useCallback(() => {
        if (state !== 'paused') return;
        pausedRef.current = false;
        setState('running');
    }, [state]);

    const stop = useCallback(() => {
        abortRef.current = true;
        clearTimer();
        setState('idle');
    }, []);

    // 自动推进主循环
    useEffect(() => {
        if (state !== 'running') return;
        const sessionId = sessionIdRef.current;
        if (!sessionId) return;

        let cancelled = false;

        const tick = async () => {
            if (cancelled || abortRef.current) return;
            if (pausedRef.current) return;

            try {
                const result: StepResult = await stepSession(sessionId);
                if (cancelled || abortRef.current) return;

                if (result.error) {
                    setErrorMessage(result.error);
                    setState('error');
                    onError?.(new Error(result.error));
                    return;
                }

                const record: DailyRecord = {
                    trade_date: result.trade_date,
                    fill_count: result.filled.length,
                    day_pnl: result.snapshot.day_pnl,
                    cum_pnl: result.snapshot.cum_pnl,
                    rejected: result.rejected.length,
                };
                setRecords([...recordsRef.current, record]);
                recordsRef.current = [...recordsRef.current, record];
                setProgress({
                    done: progressRef.current.done + 1,
                    total: progressRef.current.total,
                });
                progressRef.current = {
                    done: progressRef.current.done + 1,
                    total: progressRef.current.total,
                };
                onDay?.(record);

                // Refresh session for cursor / next_date
                try {
                    const updated = await getSession(sessionId);
                    if (cancelled || abortRef.current) return;
                    if (updated.next_date === null) {
                        setState('done');
                        onDone?.([...recordsRef.current, record]);
                        return;
                    }
                } catch (err: unknown) {
                    if (cancelled || abortRef.current) return;
                    const msg = err instanceof Error ? err.message : '刷新会话失败';
                    setErrorMessage(msg);
                    setState('error');
                    onError?.(err instanceof Error ? err : new Error(msg));
                    return;
                }

                if (abortRef.current) return;
                const delay = SPEED_MS[speed];
                timerRef.current = setTimeout(tick, delay);
            } catch (err: unknown) {
                if (cancelled || abortRef.current) return;
                const msg = err instanceof Error ? err.message : '推演失败';
                setErrorMessage(msg);
                setState('error');
                onError?.(err instanceof Error ? err : new Error(msg));
            }
        };

        tick();

        return () => {
            cancelled = true;
            clearTimer();
        };
    }, [state, speed, onDay, onDone, onError]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            abortRef.current = true;
            clearTimer();
        };
    }, []);

    return {
        state,
        speed,
        setSpeed,
        records,
        progress,
        errorMessage,
        start,
        pause,
        resume,
        stop,
    };
}
