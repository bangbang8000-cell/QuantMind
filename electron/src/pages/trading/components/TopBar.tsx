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

    const getPnLColor = (val: number) => val > 0 ? 'text-red-500' : val < 0 ? 'text-emerald-500' : 'text-slate-700';
    const getPnLTagClass = (val: number) => val > 0
        ? 'bg-red-50 text-red-600 border-red-100'
        : (val < 0 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 'bg-slate-100 text-slate-600 border-slate-200');

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
        <div className="flex flex-col gap-3 p-4 bg-white/90 backdrop-blur-md">
            {/* Header: Title, Tags, and Status Indicators */}
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                    <div className="p-1.5 bg-blue-50 text-blue-600 rounded-xl">
                        <Wallet size={18} />
                    </div>
                    <div className="flex items-baseline gap-2">
                        <span className="text-base font-bold text-slate-800 tracking-tight">资产概览</span>
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 border border-slate-200">
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

            {/* Metric Containers Grid: Enlarged 6 Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                {/* 1. 总资产 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-gradient-to-br from-blue-50/70 to-indigo-50/40 border border-blue-100/80 hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">总资产 (CNY)</span>
                        <DollarSign size={14} className="text-blue-500/70" />
                    </div>
                    <div className="text-xl font-extrabold text-slate-900 tracking-tight font-mono">
                        {formatMoney(info?.total_asset)}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                        初始: {formatMoney(info?.initial_equity)}
                    </div>
                </div>

                {/* 2. 可用资金 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-white hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">可用资金</span>
                        <Wallet size={14} className="text-slate-400" />
                    </div>
                    <div className="text-xl font-bold text-slate-800 tracking-tight font-mono">
                        {formatMoney(info?.cash)}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                        冻结: {formatMoney(info?.frozen)}
                    </div>
                </div>

                {/* 3. 今日盈亏 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-white hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">今日盈亏</span>
                        <TrendingUp size={14} className={getPnLColor(info?.daily_pnl || 0)} />
                    </div>
                    <div className={`text-xl font-bold font-mono ${getPnLColor(info?.daily_pnl || 0)}`}>
                        {(info?.daily_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.daily_pnl)}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                        <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border ${getPnLTagClass(info?.daily_pnl || 0)}`}>
                            {(info?.daily_pnl || 0) > 0 ? '+' : ''}{formatPercent(info?.daily_pnl_percent)}
                        </span>
                    </div>
                </div>

                {/* 4. 累计总盈亏 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-white hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">累计总盈亏</span>
                        <TrendingUp size={14} className={getPnLColor(info?.total_pnl || 0)} />
                    </div>
                    <div className={`text-xl font-bold font-mono ${getPnLColor(info?.total_pnl || 0)}`}>
                        {(info?.total_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.total_pnl)}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                        <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border ${getPnLTagClass(info?.total_pnl || 0)}`}>
                            {(info?.total_pnl || 0) > 0 ? '+' : ''}{formatPercent(info?.total_pnl_percent)}
                        </span>
                    </div>
                </div>

                {/* 5. 持仓市值 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-white hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">持仓市值</span>
                        <PieChart size={14} className="text-slate-400" />
                    </div>
                    <div className="text-xl font-bold text-slate-800 tracking-tight font-mono">
                        {formatMoney(info?.market_value)}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                        仓位占比: {formatPercent(info?.position_ratio)}
                    </div>
                </div>

                {/* 6. 持仓标的数 */}
                <div className="flex flex-col justify-between p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-white hover:shadow-xs transition-all">
                    <div className="flex items-center justify-between text-slate-500 mb-1">
                        <span className="text-xs font-medium">持仓标的</span>
                        <span className="text-[11px] font-semibold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                            {info?.position_count || 0} 只
                        </span>
                    </div>
                    <div className="text-xl font-bold text-slate-800 tracking-tight font-mono">
                        {info?.position_count || 0} <span className="text-xs font-normal text-slate-500">只股票</span>
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                        浮动盈亏: {(info?.floating_pnl || 0) > 0 ? '+' : ''}{formatMoney(info?.floating_pnl)}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default TopBar;
