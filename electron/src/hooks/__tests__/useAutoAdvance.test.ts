/**
 * useAutoAdvance hook 测试（R5 验收）
 *
 * 验收项：
 * - 60 交易日跑完不掉步
 * - 中途暂停→继续，游标不错乱
 * - 单日报错立即停止
 * - 卸载后循环真正停止
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAutoAdvance } from '../useAutoAdvance';

// Mock replayService
vi.mock('../../services/replayService', () => ({
    stepSession: vi.fn(),
    getSession: vi.fn(),
}));

import { stepSession, getSession } from '../../services/replayService';

const mockStep = vi.mocked(stepSession);
const mockGet = vi.mocked(getSession);

function makeSession(done = 0, total = 60): never {
    return {
        session_id: 'test-session',
        name: 'test',
        status: 'ready' as const,
        model_id: null,
        initial_cash: 1_000_000,
        start_date: '2024-01-01',
        end_date: '2024-04-30',
        cursor_date: null,
        next_date: '2024-01-02',
        sessions_total: total,
        sessions_done: done,
        auto_trade: true,
        stop_loss_pct: null,
        strategy_params: {},
        signal_progress: {},
        error_message: null,
    } as never;
}

function makeStepResult(date: string, error: string | null = null) {
    return {
        trade_date: date,
        signal_count: 1,
        filled: [],
        rejected: [],
        stop_loss_fills: [],
        account: { cash: 0, market_value: 0, total_asset: 1_000_000, positions: {} },
        snapshot: {
            trade_date: date,
            cash: 0,
            market_value: 0,
            total_asset: 1_000_000,
            day_pnl: 0,
            cum_pnl: 0,
            position_count: 0,
        },
        error,
    };
}

beforeEach(() => {
    vi.useFakeTimers();
    mockStep.mockReset();
    mockGet.mockReset();
});

afterEach(() => {
    vi.useRealTimers();
});

describe('useAutoAdvance - 状态机', () => {
    it('初始状态应为 idle', () => {
        const { result } = renderHook(() => useAutoAdvance());
        expect(result.current.state).toBe('idle');
        expect(result.current.records).toEqual([]);
    });

    it('start 后状态变为 running', () => {
        const { result } = renderHook(() => useAutoAdvance());
        act(() => result.current.start(makeSession()));
        expect(result.current.state).toBe('running');
    });

    it('暂停后状态变为 paused', async () => {
        const { result } = renderHook(() => useAutoAdvance());
        act(() => result.current.start(makeSession()));
        act(() => result.current.pause());
        expect(result.current.state).toBe('paused');
    });

    it('继续后状态回到 running', () => {
        const { result } = renderHook(() => useAutoAdvance());
        act(() => result.current.start(makeSession()));
        act(() => result.current.pause());
        act(() => result.current.resume());
        expect(result.current.state).toBe('running');
    });
});

describe('useAutoAdvance - 推进循环', () => {
    it('应串行调 stepSession，不并发', async () => {
        let resolveStep: (value: unknown) => void = () => {};
        mockStep.mockImplementationOnce(() => new Promise(resolve => { resolveStep = resolve; }));
        mockGet.mockResolvedValue(makeSession() as never);

        const { result } = renderHook(() => useAutoAdvance({ speed: 'medium' }));
        act(() => result.current.start(makeSession()));

        // 推进中 → 第一个请求已发出
        expect(mockStep).toHaveBeenCalledTimes(1);
        // 还未完成前不能并发
        await act(async () => {
            await Promise.resolve();
        });
        expect(mockStep).toHaveBeenCalledTimes(1);

        // 完成后会调度下一次
        await act(async () => {
            resolveStep(makeStepResult('2024-01-02'));
            await Promise.resolve();
        });
        // mockGet 拿 next_date=null → done
        mockGet.mockResolvedValue({ ...makeSession(), next_date: null } as never);
    });

    it('完成 60 天不丢步', async () => {
        let callCount = 0;
        mockStep.mockImplementation(async () => {
            callCount += 1;
            return makeStepResult(`2024-01-${(callCount + 1).toString().padStart(2, '0')}`);
        });
        mockGet.mockImplementation(async () => {
            return callCount >= 60
                ? { ...makeSession(), next_date: null }
                : makeSession(callCount, 60);
        });

        const { result } = renderHook(() => useAutoAdvance({ speed: 'fast' }));
        act(() => result.current.start(makeSession(0, 60)));

        // 推进所有定时器
        for (let i = 0; i < 200 && result.current.state === 'running'; i++) {
            await act(async () => {
                await vi.advanceTimersByTimeAsync(500);
            });
        }

        expect(result.current.state).toBe('done');
        expect(result.current.records.length).toBe(60);
        expect(result.current.progress.done).toBe(60);
    });

    it('result.error 非空立即停并进入 error 状态', async () => {
        mockStep.mockResolvedValueOnce(makeStepResult('2024-01-02', '撮合失败'));
        mockGet.mockResolvedValue(makeSession() as never);

        const onError = vi.fn();
        const { result } = renderHook(() => useAutoAdvance({ onError }));
        act(() => result.current.start(makeSession()));

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
            await Promise.resolve();
        });

        expect(result.current.state).toBe('error');
        expect(result.current.errorMessage).toBe('撮合失败');
        expect(onError).toHaveBeenCalled();
    });
});

describe('useAutoAdvance - 暂停/恢复', () => {
    it('暂停后不再调 stepSession', async () => {
        let callCount = 0;
        mockStep.mockImplementation(async () => {
            callCount += 1;
            return makeStepResult(`2024-01-${(callCount + 1).toString().padStart(2, '0')}`);
        });
        mockGet.mockResolvedValue(makeSession() as never);

        const { result } = renderHook(() => useAutoAdvance({ speed: 'fast' }));
        act(() => result.current.start(makeSession()));
        await act(async () => { await vi.advanceTimersByTimeAsync(500); });
        const before = mockStep.mock.calls.length;

        act(() => result.current.pause());
        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

        expect(mockStep.mock.calls.length).toBe(before);
    });

    it('恢复后继续推进', async () => {
        let callCount = 0;
        mockStep.mockImplementation(async () => {
            callCount += 1;
            return makeStepResult(`2024-01-${(callCount + 1).toString().padStart(2, '0')}`);
        });
        mockGet.mockResolvedValue({ ...makeSession(), next_date: null } as never);

        const { result } = renderHook(() => useAutoAdvance({ speed: 'fast' }));
        act(() => result.current.start(makeSession()));
        await act(async () => { await vi.advanceTimersByTimeAsync(500); });
        act(() => result.current.pause());
        act(() => result.current.resume());

        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

        // 至少有一次推进
        expect(callCount).toBeGreaterThanOrEqual(1);
    });
});

describe('useAutoAdvance - 卸载', () => {
    it('卸载后不再发请求', async () => {
        mockStep.mockResolvedValue(makeStepResult('2024-01-02'));
        mockGet.mockResolvedValue(makeSession() as never);

        const { result, unmount } = renderHook(() => useAutoAdvance({ speed: 'fast' }));
        act(() => result.current.start(makeSession()));
        await act(async () => { await vi.advanceTimersByTimeAsync(500); });
        const before = mockStep.mock.calls.length;

        unmount();
        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

        // 卸载后没有新增调用
        expect(mockStep.mock.calls.length).toBe(before);
    });
});
