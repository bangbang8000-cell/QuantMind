import React from 'react';
import { Wallet, Wifi, Activity, TrendingUp, DollarSign, PieChart, ShieldAlert } from 'lucide-react';

interface AccountInfo {
    total_asset: number;
    initial_equity: number;
    day_open_equity: number;
    month_open_equity: number;
    cash: number;
    market_value: number;
    frozen: number;
    daily_pnl: number;
    daily_pnl_percent: number;
    floating_pnl: number;
    floating_pnl_percent: number;
    total_pnl: number;
    total_pnl_percent: number;
    position_ratio: number;
    position_count: number;
}

interface TopBarProps {
    accountInfo?: AccountInfo;
    isConnected: boolean;
    strategyStatus: 'running' | 'starting' | 'stopped';
    tradingMode?: 'real' | 'simulation';
    runMode?: 'REAL' | 'SHADOW' | 'SIMULATION';
    orchestrationMode?: 'docker' | 'k8s';
}

const TopBar: React.FC<TopBarProps> = ({ accountInfo, isConnected, strategyStatus, tradingMode, runMode, orchestrationMode }) => {
    const formatMoney = (val: number | undefined) => {
        if (val === undefined || (!accountInfo && val === 0)) return '0.00';
        return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    const formatPercent = (val: number | undefined) => {
        if (val === undefined || (!accountInfo && val === 0)) return '0.00%';
        return `${(val * 100).toFixed(2)}%`;
    };

    const info = accountInfo;

    const getPnLColor = (val: number) => val > 0 ? 'text-red-600' : val < 0 ? 'text-emerald-600' : 'text-slate-800';
    const getPnLTagClass = (val: number) => val > 0
        ? 'bg-red-50 text-red-600 border-red-200'
        : (val < 0 ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-slate-100 text-slate-700 border-slate-200');

    const modeLabel = tradingMode === 'real' ? '实盘' : '模拟盘';
    const runModeLabel = runMode === 'SHADOW'
        ? '影子运行'
        : (runMode === 'REAL' ? '实盘运行' : (runMode === 'SIMULATION' ? '模拟运行' : '未启动'));
    const runModeTone = runMode === 'SHADOW' ? 'bg-purple-50 text-purple-700 border-purple-200'
        : (runMode === 'REAL' ? 'bg-blue-50 text-blue-700 border-blue-200'
            : (runMode === 'SIMULATION' ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-slate-100 text-slate-500 border-slate-200'));

    const deployChannelLabel = runMode === 'SIMULATION'
        ? '本地沙箱'
        : (runMode === 'REAL' || runMode === 'SHADOW'
            ? (orchestrationMode === 'docker' ? 'Docker 容器' : (orchestrationMode === 'k8s' ? 'K8s 集群' : '容器节点'))
            : '待部署');
    const deployChannelTone = runMode === 'SHADOW' ? 'bg-purple-50/60 text-purple-600 border-purple-200'
        : (runMode === 'REAL' ? 'bg-blue-50/60 text-blue-600 border-blue-200'
            : (runMode === 'SIMULATION' ? 'bg-amber-50/60 text-amber-600 border-amber-200' : 'bg-slate-50 text-slate-400 border-slate-200'));

    const strategyStatusLabel = strategyStatus === 'running' ? '策略运行中' : (strategyStatus === 'starting' ? '正在启动' : '策略已停止');
    const strategyStatusColor = strategyStatus === 'running' ? 'text-emerald-500' : (strategyStatus === 'starting' ? 'text-amber-500' : 'text-slate-400');

    return (
        <div className="flex flex-col gap-2.5 p-4 px-6 bg-white">
            {/* Header: Title, Tags, and Status Indicators */}
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                    <div className="p-1.5 bg-blue-50 text-blue-600 rounded-xl">
                        <Wallet size={18} />
                    </div>
                    <div className="flex items-baseline gap-2">
                        <span className="text-base font-bold text-slate-800 tracking-tight">资产概览</span>
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">
                            {modeLabel}
                        </span>
                    </div>
                    <span className={`px-2 py-0.5 rounded-md text-xs font-medium border ${runModeTone}`}>
                        {runModeLabel}
                    </span>
                    <span className={`px-2 py-0.5 rounded-md text-xs font-medium border ${deployChannelTone}`}>
                        {deployChannelLabel}
                    </span>
                </div>

                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-full text-xs text-slate-600 font-medium">
                        <Wifi size={13} className={isConnected ? 'text-emerald-500 animate-pulse' : 'text-slate-300'} />
                        <span>{isConnected ? '行情已连接' : '未连接'}</span>
                    </div>
                    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-full text-xs text-slate-600 font-medium">
                        <Activity size={13} className={strategyStatusColor} />
                        <span>{strategyStatusLabel}</span>
                    </div>
                </div>
            </div>

            {/* Metric Containers Grid: Compact & Refined Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
                {/* 1. 总资产 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-gradient-to-br from-blue-50/80 via-indigo-50/40 to-white border border-blue-100 hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">总资产 (CNY)</span>
                        <div className="absolute right-0 top-0 text-blue-500/70">
                            <DollarSign size={14} />
                        </div>
                    </div>
                    <div className="text-lg font-black text-slate-900 tracking-tight font-mono my-0.5">
                        {formatMoney(info?.total_asset)}
                    </div>
                    <div className="text-[11px] font-medium text-slate-500">
                        初始: {formatMoney(info?.initial_equity)}
                    </div>
                </div>

                {/* 2. 可用资金 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-slate-50/80 border border-slate-200 hover:bg-white hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">可用资金</span>
                        <div className="absolute right-0 top-0 text-slate-400">
                            <Wallet size={14} />
                        </div>
                    </div>
                    <div className="text-lg font-black text-slate-900 tracking-tight font-mono my-0.5">
                        {formatMoney(info?.cash)}
                    </div>
                    <div className="text-[11px] font-medium text-slate-500">
                        冻结: {formatMoney(info?.frozen)}
                    </div>
                </div>

                {/* 3. 今日盈亏 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-slate-50/80 border border-slate-200 hover:bg-white hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">今日盈亏</span>
                        <div className="absolute right-0 top-0">
                            <TrendingUp size={14} className={getPnLColor(info?.daily_pnl || 0)} />
                        </div>
                    </div>
                    <div className={`text-lg font-black font-mono my-0.5 ${getPnLColor(info?.daily_pnl || 0)}`}>
                        {(info?.daily_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.daily_pnl)}
                    </div>
                    <div className="flex items-center justify-center">
                        <span className={`px-1.5 py-0.5 rounded text-[11px] font-bold border ${getPnLTagClass(info?.daily_pnl || 0)}`}>
                            {(info?.daily_pnl || 0) > 0 ? '+' : ''}{formatPercent(info?.daily_pnl_percent)}
                        </span>
                    </div>
                </div>

                {/* 4. 累计总盈亏 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-slate-50/80 border border-slate-200 hover:bg-white hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">累计总盈亏</span>
                        <div className="absolute right-0 top-0">
                            <TrendingUp size={14} className={getPnLColor(info?.total_pnl || 0)} />
                        </div>
                    </div>
                    <div className={`text-lg font-black font-mono my-0.5 ${getPnLColor(info?.total_pnl || 0)}`}>
                        {(info?.total_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.total_pnl)}
                    </div>
                    <div className="flex items-center justify-center">
                        <span className={`px-1.5 py-0.5 rounded text-[11px] font-bold border ${getPnLTagClass(info?.total_pnl || 0)}`}>
                            {(info?.total_pnl || 0) > 0 ? '+' : ''}{formatPercent(info?.total_pnl_percent)}
                        </span>
                    </div>
                </div>

                {/* 5. 持仓市值 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-slate-50/80 border border-slate-200 hover:bg-white hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">持仓市值</span>
                        <div className="absolute right-0 top-0 text-slate-400">
                            <PieChart size={14} />
                        </div>
                    </div>
                    <div className="text-lg font-black text-slate-900 tracking-tight font-mono my-0.5">
                        {formatMoney(info?.market_value)}
                    </div>
                    <div className="text-[11px] font-medium text-slate-500">
                        仓位占比: <span className="font-semibold text-slate-700">{formatPercent(info?.position_ratio)}</span>
                    </div>
                </div>

                {/* 6. 持仓标的数 */}
                <div className="relative flex flex-col items-center justify-between p-2.5 rounded-2xl bg-slate-50/80 border border-slate-200 hover:bg-white hover:shadow-xs transition-all text-center">
                    <div className="w-full relative flex items-center justify-center mb-0.5">
                        <span className="text-[11px] font-bold text-slate-600 tracking-wide">持仓标的</span>
                        <div className="absolute right-0 top-0">
                            <span className="text-[10px] font-bold text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">
                                {info?.position_count || 0} 只
                            </span>
                        </div>
                    </div>
                    <div className="text-lg font-black text-slate-900 tracking-tight font-mono my-0.5">
                        {info?.position_count || 0} <span className="text-xs font-semibold text-slate-500">只股票</span>
                    </div>
                    <div className="text-[11px] font-medium text-slate-500">
                        浮动: <span className={`font-semibold ${(info?.floating_pnl || 0) > 0 ? 'text-red-600' : (info?.floating_pnl || 0) < 0 ? 'text-emerald-600' : 'text-slate-700'}`}>{(info?.floating_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.floating_pnl)}</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default TopBar;
