/**
 * ReplayPage.tsx — 时光回放最小可用页
 *
 * 功能：
 * - 创建回放会话（选择日期区间、初始资金）
 * - 轮询信号生成进度
 * - 单步推演（执行下一个交易日）
 * - 展示当前账户状态和成交记录
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Clock, Play, Trash2, Plus, Loader2, AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import type { ReplaySession, StepResult, CreateSessionParams } from '../../../services/replayService';
import { listSessions, createSession, getSession, stepSession, deleteSession } from '../../../services/replayService';

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_MAP: Record<ReplaySession['status'], { label: string; color: string }> = {
    creating:   { label: '创建中', color: 'bg-gray-100 text-gray-600' },
    generating: { label: '生成信号', color: 'bg-blue-50 text-blue-600' },
    ready:      { label: '就绪', color: 'bg-green-50 text-green-700' },
    stepping:   { label: '执行中', color: 'bg-yellow-50 text-yellow-700' },
    finished:   { label: '已完成', color: 'bg-gray-100 text-gray-500' },
    failed:     { label: '失败', color: 'bg-red-50 text-red-600' },
    discarded:  { label: '已丢弃', color: 'bg-gray-100 text-gray-400' },
};

function StatusBadge({ status }: { status: ReplaySession['status'] }) {
    const { label, color } = STATUS_MAP[status] || STATUS_MAP.creating;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{label}</span>;
}

// ---------------------------------------------------------------------------
// Create form
// ---------------------------------------------------------------------------

function CreateSessionForm({ onCreate }: { onCreate: (s: ReplaySession) => void }) {
    const [startDate, setStartDate] = useState('2024-03-04');
    const [endDate, setEndDate] = useState('2024-03-15');
    const [initialCash, setInitialCash] = useState('1000000');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async () => {
        setLoading(true);
        setError(null);
        try {
            const params: CreateSessionParams = {
                name: `${startDate} ~ ${endDate}`,
                start_date: startDate,
                end_date: endDate,
                initial_cash: parseFloat(initialCash),
                auto_trade: true,
            };
            const session = await createSession(params);
            onCreate(session);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '创建失败';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">起始日</label>
                    <input
                        type="date"
                        value={startDate}
                        onChange={e => setStartDate(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                    />
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">结束日</label>
                    <input
                        type="date"
                        value={endDate}
                        onChange={e => setEndDate(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                    />
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">初始资金</label>
                    <input
                        type="number"
                        value={initialCash}
                        onChange={e => setInitialCash(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                    />
                </div>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
            <button
                onClick={handleSubmit}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                创建回放
            </button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------

function SessionCard({
    session,
    onStep,
    onDelete,
}: {
    session: ReplaySession;
    onStep: (id: string) => Promise<StepResult | null>;
    onDelete: (id: string) => void;
}) {
    const [stepping, setStepping] = useState(false);
    const [lastResult, setLastResult] = useState<StepResult | null>(null);
    const [stepError, setStepError] = useState<string | null>(null);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Poll for signal generation progress
    useEffect(() => {
        if (session.status !== 'generating') {
            if (pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
            }
            return;
        }

        pollRef.current = setInterval(async () => {
            try {
                const updated = await getSession(session.session_id);
                // Force re-render by updating session status
                Object.assign(session, updated);
                if (updated.status !== 'generating') {
                    if (pollRef.current) {
                        clearInterval(pollRef.current);
                        pollRef.current = null;
                    }
                }
            } catch {
                // ignore polling errors
            }
        }, 2000);

        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [session.status, session.session_id]);

    const handleStep = async () => {
        setStepping(true);
        setStepError(null);
        try {
            const result = await onStep(session.session_id);
            if (result) setLastResult(result);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '推演失败';
            setStepError(msg);
        } finally {
            setStepping(false);
        }
    };

    const canStep = session.status === 'ready' && session.next_date !== null;
    const progress = session.signal_progress;
    const pnl = lastResult?.snapshot?.cum_pnl ?? 0;

    return (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50/50 border-b border-gray-100">
                <div className="flex items-center gap-3">
                    <Clock size={16} className="text-gray-400" />
                    <span className="text-sm font-medium text-gray-800">{session.name || '回放会话'}</span>
                    <StatusBadge status={session.status} />
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleStep}
                        disabled={!canStep || stepping}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                        {stepping ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                        {session.next_date ? `推演 ${session.next_date}` : '已完成'}
                    </button>
                    <button
                        onClick={() => onDelete(session.session_id)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            </div>

            {/* Body */}
            <div className="px-4 py-3 space-y-3">
                {/* Progress bar (generating) */}
                {session.status === 'generating' && progress && (
                    <div className="space-y-1">
                        <div className="flex justify-between text-xs text-gray-500">
                            <span>信号生成中…</span>
                            <span>{progress.done ?? 0} / {progress.total ?? '?'}</span>
                        </div>
                        <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-blue-400 rounded-full transition-all duration-300"
                                style={{ width: `${progress.total ? ((progress.done ?? 0) / progress.total) * 100 : 0}%` }}
                            />
                        </div>
                        {progress.total_signals !== undefined && (
                            <p className="text-xs text-gray-400">{progress.total_signals} 条信号</p>
                        )}
                    </div>
                )}

                {/* Session info */}
                <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                        <span className="text-xs text-gray-400">区间</span>
                        <p className="font-medium">{session.start_date} ~ {session.end_date}</p>
                    </div>
                    <div>
                        <span className="text-xs text-gray-400">进度</span>
                        <p className="font-medium">{session.sessions_done} / {session.sessions_total} 天</p>
                    </div>
                    <div>
                        <span className="text-xs text-gray-400">游标</span>
                        <p className="font-medium">{session.cursor_date ?? '—'}</p>
                    </div>
                    <div>
                        <span className="text-xs text-gray-400">累计盈亏</span>
                        <p className={`font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {pnl >= 0 ? '+' : ''}{pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                    </div>
                </div>

                {/* Error */}
                {(session.error_message || stepError) && (
                    <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-100">
                        <AlertTriangle size={14} className="text-red-500 shrink-0 mt-0.5" />
                        <p className="text-xs text-red-700">{session.error_message || stepError}</p>
                    </div>
                )}

                {/* Last step result */}
                {lastResult && (
                    <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                            {lastResult.trade_date} 成交
                        </h4>
                        <div className="grid gap-1.5 max-h-40 overflow-y-auto">
                            {lastResult.filled.map((f, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-gray-50 text-xs">
                                    <span className="font-mono">{f.symbol}</span>
                                    <span className={f.side === 'BUY' ? 'text-red-600' : 'text-green-600'}>
                                        {f.side === 'BUY' ? '买入' : '卖出'} {f.quantity}@{f.price.toFixed(2)}
                                    </span>
                                    <span className="text-gray-400">费 {f.total_fee.toFixed(2)}</span>
                                </div>
                            ))}
                        </div>
                        {/* Snapshot */}
                        <div className="grid grid-cols-4 gap-3 text-xs text-gray-600">
                            <div>
                                <span className="text-gray-400">现金</span>
                                <p className="font-medium">{lastResult.snapshot.cash.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
                            </div>
                            <div>
                                <span className="text-gray-400">市值</span>
                                <p className="font-medium">{lastResult.snapshot.market_value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
                            </div>
                            <div>
                                <span className="text-gray-400">总资产</span>
                                <p className="font-medium">{lastResult.snapshot.total_asset.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
                            </div>
                            <div>
                                <span className="text-gray-400">日盈亏</span>
                                <p className={`font-medium ${lastResult.snapshot.day_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {lastResult.snapshot.day_pnl >= 0 ? '+' : ''}{lastResult.snapshot.day_pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const ReplayPage: React.FC = () => {
    const [sessions, setSessions] = useState<ReplaySession[]>([]);
    const [loading, setLoading] = useState(true);

    const loadSessions = useCallback(async () => {
        try {
            const list = await listSessions();
            setSessions(list);
        } catch {
            // ignore
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadSessions(); }, [loadSessions]);

    const handleCreate = (_session: ReplaySession) => {
        loadSessions();
    };

    const handleStep = async (sessionId: string): Promise<StepResult | null> => {
        try {
            const result = await stepSession(sessionId);
            // Refresh session list after step
            await loadSessions();
            return result;
        } catch {
            return null;
        }
    };

    const handleDelete = async (sessionId: string) => {
        try {
            await deleteSession(sessionId);
            const remaining = sessions.filter(s => s.session_id !== sessionId);
            setSessions(remaining);
        } catch {
            // ignore
        }
    };

    return (
        <div className="h-full overflow-y-auto p-4 space-y-4">
            {/* Create form */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <Plus size={16} className="text-blue-500" />
                    新建回放
                </h3>
                <CreateSessionForm onCreate={handleCreate} />
            </div>

            {/* Session list */}
            <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    <Clock size={16} className="text-gray-400" />
                    回放会话
                </h3>

                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 size={24} className="animate-spin text-gray-300" />
                    </div>
                ) : sessions.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-8">暂无回放会话</p>
                ) : (
                    sessions.map(s => (
                        <SessionCard
                            key={s.session_id}
                            session={s}
                            onStep={handleStep}
                            onDelete={handleDelete}
                        />
                    ))
                )}
            </div>
        </div>
    );
};

export default ReplayPage;
