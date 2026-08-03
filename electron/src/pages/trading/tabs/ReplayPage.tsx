/**
 * ReplayPage.tsx — 时光回放页
 *
 * 功能：
 * - 创建回放会话（选择日期区间、初始资金、自动/手动模式）
 * - 轮询信号生成进度
 * - 自动模式：单步推演 / 自动推进
 * - 手动模式：生成提案 → 勾选/改数量 → 确认执行 / 跳过今日
 * - 自动推进完成后跳转报告页
 * - 展示当前账户状态和成交记录
 */

import React, { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import {
    Clock, Play, Trash2, Plus, Loader2, AlertTriangle,
    SkipForward, CheckSquare, Square, Shield, ChevronDown, ChevronUp,
    FastForward, Pause, RotateCcw, BarChart3,
} from 'lucide-react';
import type {
    ReplaySession, StepResult, CreateSessionParams,
    ProposalItem, ProposalResponse, ConfirmedOrder,
} from '../../../services/replayService';
import {
    listSessions, createSession, getSession,
    stepSession, deleteSession, proposeSession,
} from '../../../services/replayService';
import { useAutoAdvance, type AutoAdvanceSpeed, type DailyRecord } from '../../../hooks/useAutoAdvance';
import ReplayReportPage from './ReplayReportPage';

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_MAP: Record<ReplaySession['status'], { label: string; color: string }> = {
    creating:          { label: '创建中',     color: 'bg-gray-100 text-gray-600' },
    generating:        { label: '生成信号',   color: 'bg-blue-50 text-blue-600' },
    ready:             { label: '就绪',       color: 'bg-green-50 text-green-700' },
    stepping:          { label: '执行中',     color: 'bg-yellow-50 text-yellow-700' },
    awaiting_confirm:  { label: '待确认',     color: 'bg-amber-50 text-amber-700' },
    finished:          { label: '已完成',     color: 'bg-gray-100 text-gray-500' },
    failed:            { label: '失败',       color: 'bg-red-50 text-red-600' },
    discarded:         { label: '已丢弃',     color: 'bg-gray-100 text-gray-400' },
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
    const [autoTrade, setAutoTrade] = useState(true);
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
                auto_trade: autoTrade,
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
            <div className="grid grid-cols-4 gap-3">
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
                <div>
                    <label className="block text-xs text-gray-500 mb-1">模式</label>
                    <select
                        value={autoTrade ? 'auto' : 'manual'}
                        onChange={e => setAutoTrade(e.target.value === 'auto')}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                    >
                        <option value="auto">自动执行</option>
                        <option value="manual">手动确认</option>
                    </select>
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
// Proposal table (manual mode)
// ---------------------------------------------------------------------------

interface ProposalRowState {
    checked: boolean;
    quantity: number;
    rejectReason: string | null;
}

type RowAction =
    | { type: 'RESET'; proposals: ProposalItem[] }
    | { type: 'TOGGLE'; idx: number; cancellable: boolean }
    | { type: 'SET_QTY'; idx: number; raw: string; proposal: ProposalItem; lotSize: number }
    | { type: 'TOGGLE_ALL'; proposals: ProposalItem[] }
    | { type: 'SET_REJECT'; idx: number; reason: string | null };

function initRows(proposals: ProposalItem[]): ProposalRowState[] {
    return proposals.map(p => ({
        checked: true,
        quantity: p.quantity,
        rejectReason: null,
    }));
}

function rowReducer(state: ProposalRowState[], action: RowAction): ProposalRowState[] {
    switch (action.type) {
        case 'RESET':
            return initRows(action.proposals);
        case 'TOGGLE': {
            if (!action.cancellable) return state;
            const next = [...state];
            next[action.idx] = { ...next[action.idx], checked: !next[action.idx].checked };
            return next;
        }
        case 'SET_QTY': {
            const val = parseInt(action.raw, 10);
            if (isNaN(val) || val < 0) return state;
            const p = action.proposal;
            const capped = Math.min(val, p.quantity);
            const finalQty = p.side === 'BUY' && action.lotSize > 0
                ? Math.floor(capped / action.lotSize) * action.lotSize
                : capped;
            const next = [...state];
            next[action.idx] = { ...next[action.idx], quantity: finalQty, rejectReason: null };
            return next;
        }
        case 'TOGGLE_ALL': {
            const allChecked = state.every((r, i) => r.checked || !action.proposals[i].cancellable);
            return state.map((r, i) => ({
                ...r,
                checked: action.proposals[i].cancellable ? !allChecked : true,
            }));
        }
        case 'SET_REJECT': {
            const next = [...state];
            next[action.idx] = { ...next[action.idx], rejectReason: action.reason };
            return next;
        }
    }
}

function ProposalTable({
    proposals,
    lotSize,
    onConfirm,
    onSkip,
    loading,
}: {
    proposals: ProposalItem[];
    lotSize: number;
    onConfirm: (confirmed: ConfirmedOrder[]) => void;
    onSkip: () => void;
    loading: boolean;
}) {
    const [rows, dispatch] = useReducer(rowReducer, proposals, initRows);

    // Sync when proposals change
    useEffect(() => {
        dispatch({ type: 'RESET', proposals });
    }, [proposals]);

    const toggleRow = (idx: number) => {
        dispatch({ type: 'TOGGLE', idx, cancellable: proposals[idx].cancellable });
    };

    const updateQuantity = (idx: number, raw: string) => {
        dispatch({ type: 'SET_QTY', idx, raw, proposal: proposals[idx], lotSize });
    };

    const toggleAll = () => {
        dispatch({ type: 'TOGGLE_ALL', proposals });
    };

    const handleConfirm = () => {
        const confirmed: ConfirmedOrder[] = [];

        rows.forEach((r, i) => {
            const p = proposals[i];
            if (!r.checked && p.cancellable) return; // unchecked non-stop-loss → skip
            if (r.quantity <= 0) {
                dispatch({ type: 'SET_REJECT', idx: i, reason: 'INVALID_QUANTITY' });
                return;
            }
            if (r.quantity > p.quantity) {
                dispatch({ type: 'SET_REJECT', idx: i, reason: `EXCEED_PROPOSED_QTY:${p.quantity}` });
                return;
            }
            confirmed.push({ symbol: p.symbol, side: p.side, quantity: r.quantity });
        });

        // Only send if there are valid items (stop-loss forced by server anyway)
        if (confirmed.length > 0) {
            onConfirm(confirmed);
        }
    };

    const allChecked = rows.every((r, i) => r.checked || !proposals[i].cancellable);
    const checkedCount = rows.filter((r, i) => r.checked || !proposals[i].cancellable).length;
    const totalEstAmount = rows.reduce((sum, r, i) => {
        if (!r.checked && proposals[i].cancellable) return sum;
        return sum + r.quantity * proposals[i].est_price;
    }, 0);

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    调仓提案
                </h4>
                <button
                    onClick={toggleAll}
                    className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-600"
                >
                    {allChecked ? <CheckSquare size={14} /> : <Square size={14} />}
                    {allChecked ? '全不选' : '全选'}
                </button>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="border-b border-gray-100 text-gray-400">
                            <th className="py-1.5 px-2 text-left w-8"></th>
                            <th className="py-1.5 px-2 text-left">标的</th>
                            <th className="py-1.5 px-2 text-left">方向</th>
                            <th className="py-1.5 px-2 text-right">数量</th>
                            <th className="py-1.5 px-2 text-right">预估价</th>
                            <th className="py-1.5 px-2 text-right">预估金额</th>
                            <th className="py-1.5 px-2 text-right">成本/盈亏</th>
                            <th className="py-1.5 px-2 text-left">来源</th>
                        </tr>
                    </thead>
                    <tbody>
                        {proposals.map((p, i) => {
                            const r = rows[i];
                            const isStopLoss = !p.cancellable;
                            const isBuy = p.side === 'BUY';
                            return (
                                <tr
                                    key={`${p.symbol}-${p.side}`}
                                    className={`border-b border-gray-50 ${isStopLoss ? 'bg-amber-50/50' : ''}`}
                                >
                                    <td className="py-1.5 px-2">
                                        {isStopLoss ? (
                                            <span className="inline-flex items-center gap-1 text-amber-600" title="风控·不可取消">
                                                <Shield size={12} />
                                            </span>
                                        ) : (
                                            <button onClick={() => toggleRow(i)} className="text-gray-400 hover:text-blue-500">
                                                {r.checked ? <CheckSquare size={14} className="text-blue-500" /> : <Square size={14} />}
                                            </button>
                                        )}
                                    </td>
                                    <td className="py-1.5 px-2 font-mono font-medium">{p.symbol}</td>
                                    <td className="py-1.5 px-2">
                                        <span className={isBuy ? 'text-red-600' : 'text-green-600'}>
                                            {isBuy ? '买入' : '卖出'}
                                        </span>
                                    </td>
                                    <td className="py-1.5 px-2 text-right">
                                        {isStopLoss ? (
                                            <span className="font-mono">{p.quantity}</span>
                                        ) : (
                                            <input
                                                type="number"
                                                value={r.quantity}
                                                onChange={e => updateQuantity(i, e.target.value)}
                                                step={isBuy ? lotSize : 1}
                                                min={0}
                                                max={p.quantity}
                                                className="w-20 px-1.5 py-0.5 text-right font-mono rounded border border-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-200"
                                            />
                                        )}
                                    </td>
                                    <td className="py-1.5 px-2 text-right font-mono">{p.est_price.toFixed(2)}</td>
                                    <td className="py-1.5 px-2 text-right font-mono">
                                        {((r.checked || isStopLoss) ? r.quantity * p.est_price : 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                                    </td>
                                    <td className="py-1.5 px-2 text-right">
                                        {isBuy ? (
                                            <span className="text-gray-400">—</span>
                                        ) : p.avg_cost != null && p.est_pnl != null ? (
                                            <span className={p.est_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                                                {p.est_pnl >= 0 ? '+' : ''}{p.est_pnl.toFixed(0)}
                                            </span>
                                        ) : (
                                            <span className="text-gray-400">—</span>
                                        )}
                                    </td>
                                    <td className="py-1.5 px-2">
                                        {isStopLoss ? (
                                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-medium">
                                                <Shield size={10} />
                                                风控·强制
                                            </span>
                                        ) : p.origin === 'signal' ? (
                                            <span className="text-gray-400">信号</span>
                                        ) : (
                                            <span className="text-gray-400">{p.origin}</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Rejection reasons */}
            {rows.some(r => r.rejectReason) && (
                <div className="space-y-1">
                    {rows.map((r, i) => r.rejectReason && (
                        <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-50 border border-red-100 text-xs text-red-700">
                            <AlertTriangle size={12} />
                            <span className="font-mono">{proposals[i].symbol}</span>
                            <span>{r.rejectReason}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <span className="text-xs text-gray-500">
                    已选 {checkedCount} / {proposals.length} 笔 · 预计动用 {totalEstAmount.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                </span>
                <div className="flex items-center gap-2">
                    <button
                        onClick={onSkip}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 text-xs font-medium hover:bg-gray-50 disabled:opacity-40 transition-colors"
                    >
                        <SkipForward size={14} />
                        跳过今日
                    </button>
                    <button
                        onClick={handleConfirm}
                        disabled={loading || checkedCount === 0}
                        className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-40 transition-colors"
                    >
                        {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                        确认执行 {checkedCount} 笔
                    </button>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------

function SessionCard({
    session: initialSession,
    onStep,
    onDelete,
    onRefresh,
    onViewReport,
}: {
    session: ReplaySession;
    onStep: (id: string, params?: { confirmed?: ConfirmedOrder[]; skip?: boolean }) => Promise<StepResult | null>;
    onDelete: (id: string) => void;
    onRefresh: () => void;
    onViewReport: (sessionId: string) => void;
}) {
    const [session, setSession] = useState(initialSession);
    const [stepping, setStepping] = useState(false);
    const [proposing, setProposing] = useState(false);
    const [proposal, setProposal] = useState<ProposalResponse | null>(null);
    const [lastResult, setLastResult] = useState<StepResult | null>(null);
    const [stepError, setStepError] = useState<string | null>(null);
    const [showTrades, setShowTrades] = useState(false);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Auto-advance hook (R5)
    const autoAdvance = useAutoAdvance({
        onDay: () => { onRefresh(); },
        onDone: () => {
            onRefresh();
        },
    });

    // Sync from parent
    useEffect(() => {
        setSession(initialSession);
    }, [initialSession]);

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
                setSession(updated);
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

    // Auto mode step
    const handleAutoStep = async () => {
        setStepping(true);
        setStepError(null);
        try {
            const result = await onStep(session.session_id);
            if (result) {
                setLastResult(result);
                onRefresh();
            }
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '推演失败';
            setStepError(msg);
        } finally {
            setStepping(false);
        }
    };

    // Manual mode: propose
    const handlePropose = async () => {
        setProposing(true);
        setStepError(null);
        try {
            const resp = await proposeSession(session.session_id);
            setProposal(resp);
            onRefresh();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '生成提案失败';
            setStepError(msg);
        } finally {
            setProposing(false);
        }
    };

    // Manual mode: confirm
    const handleConfirm = async (confirmed: ConfirmedOrder[]) => {
        setStepping(true);
        setStepError(null);
        try {
            const result = await onStep(session.session_id, { confirmed });
            if (result) {
                setLastResult(result);
                setProposal(null);
                onRefresh();
            }
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '执行失败';
            setStepError(msg);
        } finally {
            setStepping(false);
        }
    };

    // Manual mode: skip
    const handleSkip = async () => {
        setStepping(true);
        setStepError(null);
        try {
            const result = await onStep(session.session_id, { skip: true });
            if (result) {
                setLastResult(result);
                setProposal(null);
                onRefresh();
            }
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '跳过失败';
            setStepError(msg);
        } finally {
            setStepping(false);
        }
    };

    const isManual = !session.auto_trade;
    const canStep = session.status === 'ready' && session.next_date !== null;
    const canPropose = isManual && (session.status === 'ready' || session.status === 'awaiting_confirm') && session.next_date !== null;
    const progress = session.signal_progress;
    const pnl = lastResult?.snapshot?.cum_pnl ?? 0;
    const lotSize = Number((session.strategy_params as Record<string, unknown>)?.lot_size) || 100;

    return (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50/50 border-b border-gray-100">
                <div className="flex items-center gap-3">
                    <Clock size={16} className="text-gray-400" />
                    <span className="text-sm font-medium text-gray-800">{session.name || '回放会话'}</span>
                    <StatusBadge status={session.status} />
                    {isManual && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 text-[10px] font-medium">
                            手动
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {/* Report button (when finished or has data) */}
                    {(session.status === 'finished' || session.sessions_done > 0) && (
                        <button
                            onClick={() => onViewReport(session.session_id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 text-xs font-medium hover:bg-gray-50 transition-colors"
                        >
                            <BarChart3 size={14} />
                            报告
                        </button>
                    )}
                    {/* Auto mode: step button */}
                    {!isManual && autoAdvance.state === 'idle' && (
                        <button
                            onClick={handleAutoStep}
                            disabled={!canStep || stepping}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            {stepping ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                            {session.next_date ? `推演 ${session.next_date}` : '已完成'}
                        </button>
                    )}
                    {/* Auto mode: auto-advance controls */}
                    {!isManual && canStep && autoAdvance.state !== 'running' && autoAdvance.state !== 'paused' && (
                        <button
                            onClick={() => autoAdvance.start(session)}
                            disabled={!canStep}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500 text-white text-xs font-medium hover:bg-green-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            <FastForward size={14} />
                            自动推进
                        </button>
                    )}
                    {!isManual && autoAdvance.state === 'running' && (
                        <button
                            onClick={autoAdvance.pause}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 text-white text-xs font-medium hover:bg-amber-600 transition-colors"
                        >
                            <Pause size={14} />
                            暂停
                        </button>
                    )}
                    {!isManual && autoAdvance.state === 'paused' && (
                        <button
                            onClick={autoAdvance.resume}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500 text-white text-xs font-medium hover:bg-green-600 transition-colors"
                        >
                            <Play size={14} />
                            继续
                        </button>
                    )}
                    {!isManual && (autoAdvance.state === 'running' || autoAdvance.state === 'paused') && (
                        <button
                            onClick={autoAdvance.stop}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                        >
                            <RotateCcw size={14} />
                        </button>
                    )}
                    {/* Speed selector */}
                    {!isManual && (autoAdvance.state === 'running' || autoAdvance.state === 'paused') && (
                        <select
                            value={autoAdvance.speed}
                            onChange={e => autoAdvance.setSpeed(e.target.value as AutoAdvanceSpeed)}
                            className="px-2 py-1 rounded border border-gray-200 text-xs"
                        >
                            <option value="slow">慢 (2s)</option>
                            <option value="medium">中 (1s)</option>
                            <option value="fast">快 (0.3s)</option>
                            <option value="instant">极速</option>
                        </select>
                    )}
                    {/* Manual mode: propose button */}
                    {isManual && !proposal && (
                        <button
                            onClick={handlePropose}
                            disabled={!canPropose || proposing}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500 text-white text-xs font-medium hover:bg-purple-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            {proposing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                            {session.status === 'awaiting_confirm' ? '查看提案' : `生成提案 ${session.next_date ?? ''}`}
                        </button>
                    )}
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

                {/* Auto-advance progress bar */}
                {autoAdvance.state !== 'idle' && (
                    <div className="space-y-1">
                        <div className="flex justify-between text-xs text-gray-500">
                            <span>
                                {autoAdvance.state === 'running' && '自动推进中…'}
                                {autoAdvance.state === 'paused' && '已暂停'}
                                {autoAdvance.state === 'done' && '已完成'}
                                {autoAdvance.state === 'error' && '推进出错'}
                            </span>
                            <span>{autoAdvance.progress.done} / {autoAdvance.progress.total} 天</span>
                        </div>
                        <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-300 ${
                                    autoAdvance.state === 'error' ? 'bg-red-400' :
                                    autoAdvance.state === 'done' ? 'bg-green-400' : 'bg-blue-400'
                                }`}
                                style={{ width: `${autoAdvance.progress.total ? (autoAdvance.progress.done / autoAdvance.progress.total) * 100 : 0}%` }}
                            />
                        </div>
                        {/* Auto-advance error */}
                        {autoAdvance.errorMessage && (
                            <p className="text-xs text-red-500">{autoAdvance.errorMessage}</p>
                        )}
                        {/* Daily results */}
                        {autoAdvance.records.length > 0 && (
                            <div className="max-h-32 overflow-y-auto space-y-0.5">
                                {autoAdvance.records.map((r, i) => (
                                    <div
                                        key={i}
                                        className={`flex items-center justify-between px-2 py-1 rounded text-xs ${
                                            i === autoAdvance.records.length - 1 && autoAdvance.state === 'running'
                                                ? 'bg-blue-50 animate-pulse'
                                                : ''
                                        }`}
                                    >
                                        <span className="font-mono text-gray-600">{r.trade_date}</span>
                                        <span className="text-gray-400">{r.fill_count} 笔</span>
                                        <span className={r.day_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                                            {r.day_pnl >= 0 ? '+' : ''}{r.day_pnl.toFixed(0)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                        {/* Done: link to report */}
                        {autoAdvance.state === 'done' && (
                            <button
                                onClick={() => onViewReport(session.session_id)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 transition-colors"
                            >
                                <BarChart3 size={14} />
                                查看报告
                            </button>
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

                {/* Proposal table (manual mode) */}
                {isManual && proposal && (
                    <ProposalTable
                        proposals={proposal.proposals}
                        lotSize={lotSize}
                        onConfirm={handleConfirm}
                        onSkip={handleSkip}
                        loading={stepping}
                    />
                )}

                {/* Last step result */}
                {lastResult && (
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                {lastResult.trade_date} 成交
                            </h4>
                            <button
                                onClick={() => setShowTrades(!showTrades)}
                                className="text-xs text-gray-400 hover:text-gray-600"
                            >
                                {showTrades ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </button>
                        </div>

                        {showTrades && (
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
                                {lastResult.rejected.length > 0 && lastResult.rejected.map((r, i) => (
                                    <div key={`r-${i}`} className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-red-50 text-xs text-red-600">
                                        <span className="font-mono">{r.symbol}</span>
                                        <span>{r.side === 'BUY' ? '买入' : '卖出'}</span>
                                        <span>{r.reason}</span>
                                    </div>
                                ))}
                            </div>
                        )}

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
    const [reportSessionId, setReportSessionId] = useState<string | null>(null);

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

    // If viewing report, show ReplayReportPage
    if (reportSessionId) {
        return (
            <ReplayReportPage
                sessionId={reportSessionId}
                onBack={() => setReportSessionId(null)}
            />
        );
    }

    const handleCreate = (_session: ReplaySession) => {
        loadSessions();
    };

    const handleStep = async (
        sessionId: string,
        params?: { confirmed?: ConfirmedOrder[]; skip?: boolean },
    ): Promise<StepResult | null> => {
        try {
            const result = await stepSession(sessionId, params);
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
                            onRefresh={loadSessions}
                            onViewReport={setReportSessionId}
                        />
                    ))
                )}
            </div>
        </div>
    );
};

export default ReplayPage;
