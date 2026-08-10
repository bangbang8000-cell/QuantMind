import React from 'react';
import {
    Button,
    Card,
    Col,
    Divider,
    Empty,
    Progress,
    Space,
    Spin,
    Table,
    Tag,
    Typography,
    message,
} from 'antd';
import {
    CheckCircleFilled,
    CloudDownloadOutlined,
    CloudSyncOutlined,
    InfoCircleOutlined,
    LineChartOutlined,
    ReloadOutlined,
    StockOutlined,
    SyncOutlined,
    ThunderboltOutlined,
    WarningFilled,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { dataPlatformService } from '../../services/dataPlatformService';
import {
    AdminFeatureSnapshotsOlderSample,
    AdminFeatureSnapshotsInvalidSample,
} from '../../types';

const { Text, Title } = Typography;

interface SyncStatusProps {
    syncStatus: any;
    syncStatusLoading: boolean;
    onReload: () => void;
}

const SyncStatusCard: React.FC<SyncStatusProps> = ({
    syncStatus,
    syncStatusLoading,
    onReload,
}) => (
    <Card
        className="rounded-[2.5rem] border-none shadow-xl shadow-slate-200/40 bg-white"
        styles={{ body: { padding: '32px' } }}
    >
        <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center">
                    <SyncOutlined className="text-emerald-600 text-xl" />
                </div>
                <span className="text-slate-800 font-black text-xl uppercase tracking-tight">
                    同步状态
                </span>
            </div>
            <Button
                type="text"
                size="small"
                icon={<ReloadOutlined spin={syncStatusLoading} />}
                onClick={onReload}
                className="text-slate-400"
            />
        </div>

        {syncStatus ? (
            <div className="space-y-4">
                {syncStatus.last_sync && (
                    <div className="grid grid-cols-2 gap-4">
                        <div className="p-3 rounded-xl bg-slate-50">
                            <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1">
                                最后同步
                            </Text>
                            <Text className="text-sm font-black text-slate-700">
                                {syncStatus.last_sync.time
                                    ? dayjs(syncStatus.last_sync.time).format('MM-DD HH:mm')
                                    : '—'}
                            </Text>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-50">
                            <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1">
                                模式
                            </Text>
                            <Tag
                                color={
                                    syncStatus.last_sync.mode === 'incremental'
                                        ? 'green'
                                        : 'blue'
                                }
                                className="m-0 border-none font-bold rounded-lg"
                            >
                                {syncStatus.last_sync.mode === 'incremental' ? '增量' : '全量'}
                            </Tag>
                        </div>
                    </div>
                )}

                {syncStatus.last_sync?.sources && (
                    <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                        <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">
                            数据源同步结果
                        </Text>
                        <div className="grid grid-cols-2 gap-3">
                            {Object.entries(syncStatus.last_sync.sources).map(
                                ([name, count]: [string, any]) => (
                                    <div
                                        key={name}
                                        className="flex items-center justify-between p-2 bg-white rounded-lg"
                                    >
                                        <Text className="text-xs font-bold text-slate-600">
                                            {name}
                                        </Text>
                                        <Tag
                                            color={count > 0 ? 'green' : 'default'}
                                            className="m-0 border-none text-[10px] font-bold rounded-md"
                                        >
                                            {count} 条
                                        </Tag>
                                    </div>
                                ),
                            )}
                        </div>
                    </div>
                )}

                {syncStatus.stock_daily_latest && (
                    <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                        <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">
                            stock_daily_latest 表
                        </Text>
                        <div className="grid grid-cols-3 gap-3">
                            <div>
                                <Text className="text-[10px] text-slate-400 block">最新日期</Text>
                                <Text className="text-sm font-black text-slate-700">
                                    {syncStatus.stock_daily_latest.max_date || '—'}
                                </Text>
                            </div>
                            <div>
                                <Text className="text-[10px] text-slate-400 block">总行数</Text>
                                <Text className="text-sm font-black text-indigo-600">
                                    {(
                                        syncStatus.stock_daily_latest.total_rows || 0
                                    ).toLocaleString()}
                                </Text>
                            </div>
                            <div>
                                <Text className="text-[10px] text-slate-400 block">股票数</Text>
                                <Text className="text-sm font-black text-emerald-600">
                                    {syncStatus.stock_daily_latest.symbol_count || '—'}
                                </Text>
                            </div>
                        </div>
                    </div>
                )}

                {syncStatus.qlib_data && (
                    <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                        <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">
                            Qlib 数据
                        </Text>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Text className="text-[10px] text-slate-400 block">
                                    日历最后日期
                                </Text>
                                <Text className="text-sm font-black text-slate-700">
                                    {syncStatus.qlib_data.calendar_last_date || '—'}
                                </Text>
                            </div>
                            <div>
                                <Text className="text-[10px] text-slate-400 block">标的数</Text>
                                <Text className="text-sm font-black text-indigo-600">
                                    {syncStatus.qlib_data.instruments_count || '—'}
                                </Text>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        ) : (
            <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                    <Text className="text-slate-400 text-xs">
                        {syncStatusLoading
                            ? '加载中...'
                            : '暂无同步记录，点击上方按钮开始同步'}
                    </Text>
                }
            />
        )}
    </Card>
);

interface MaintenancePanelProps {
    selectedMarket: string;
    currentMarketCfg: {
        label: string;
        gradient: string;
        color: string;
    };
    currentMarket: any;
    dailySyncLoading: boolean;
    syncLoading: boolean;
    parquetLoading: boolean;
    fundamentalsLoading: boolean;
    marketSyncing: string | null;
    syncTaskId: string | null;
    syncTaskProgress: string;
    syncStepProgress: {
        step: string;
        detail: string;
        pct: number;
        current: number;
        total: number;
    } | null;
    parquetResult: any;
    fundamentalsResult: any;
    onDailySync: (incremental: boolean) => void;
    onSyncOfficialData: () => void;
    onUpdateFeatureParquet: (rebuild: boolean) => void;
    onUpdateMarketFeatures: (market: string, rebuild: boolean) => void;
    onSyncFundamentals: (market: string) => void;
    onSyncMarket: (marketId: string, dataReady: boolean) => void;
}

const MaintenancePanel: React.FC<MaintenancePanelProps> = ({
    selectedMarket,
    currentMarketCfg,
    currentMarket,
    dailySyncLoading,
    syncLoading,
    parquetLoading,
    fundamentalsLoading,
    marketSyncing,
    syncTaskId,
    syncTaskProgress,
    syncStepProgress,
    parquetResult,
    fundamentalsResult,
    onDailySync,
    onSyncOfficialData,
    onUpdateFeatureParquet,
    onUpdateMarketFeatures,
    onSyncFundamentals,
    onSyncMarket,
}) => (
    <Card
        className="rounded-[2.5rem] border-none shadow-xl shadow-slate-200/40 bg-white"
        styles={{ body: { padding: '32px' } }}
    >
        <div className="flex items-center justify-between mb-8">
            <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
                    <CloudSyncOutlined className="text-indigo-600 text-xl" />
                </div>
                <span className="text-slate-800 font-black text-xl uppercase tracking-tight">
                    自动化维护
                </span>
            </div>
            <Tag
                className={`m-0 border-none rounded-full px-3 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                    selectedMarket === 'a_share'
                        ? 'bg-indigo-50 text-indigo-600'
                        : `bg-gradient-to-r ${currentMarketCfg.gradient} text-white`
                }`}
            >
                {currentMarketCfg.label}
            </Tag>
        </div>

        <div className="space-y-6">
            {/* 同步说明 */}
            {selectedMarket === 'a_share' ? (
                <div className="p-5 rounded-2xl bg-slate-50 border border-slate-100">
                    <Title
                        level={5}
                        className="!text-slate-800 !font-black !mb-3 uppercase tracking-tight text-sm"
                    >
                        日常同步任务包含：
                    </Title>
                    <ul className="space-y-2 m-0 p-0 list-none">
                        {[
                            'QuantDB A股 增量同步 parquet (data/quantdb/)',
                            '从 parquet 批量填充 PG stock_daily_latest',
                            '增量更新 Qlib 二进制缓存 (.qlib_cache/cn_data)',
                            '估值/技术指标随 features_daily 一并写入',
                        ].map((text, i) => (
                            <li
                                key={i}
                                className="flex items-start text-xs text-slate-500 font-medium"
                            >
                                <CheckCircleFilled className="text-emerald-500 mt-0.5 mr-2" />
                                {text}
                            </li>
                        ))}
                    </ul>
                </div>
            ) : (
                <div className="p-5 rounded-2xl bg-slate-50 border border-slate-100">
                    <Title
                        level={5}
                        className="!text-slate-800 !font-black !mb-3 uppercase tracking-tight text-sm"
                    >
                        {currentMarketCfg.label}数据同步：
                    </Title>
                    <ul className="space-y-2 m-0 p-0 list-none">
                        {(
                            selectedMarket === 'crypto'
                                ? [
                                      '从 Binance API 下载 5 分钟 K 线数据',
                                      '转换为 Qlib bin 格式 (5min)',
                                      '生成日历、标的列表、特征文件',
                                      '支持 33 个主流加密货币交易对',
                                  ]
                                : selectedMarket === 'hong_kong'
                                  ? [
                                        'QuantHK parquet 单源（本地 daily_forward 分区）',
                                        'Qlib 缓存从 parquet 构建（.qlib_cache/hk_data）',
                                        '覆盖 3000+ 只港股，1980 年起历史数据',
                                        '支持增量更新和全量重建',
                                    ]
                                  : selectedMarket === 'futures'
                                    ? [
                                          'akshare：国际期货 + 国内商品 + 上金所贵金属',
                                          '本地 parquet 存储（QuantFutures 数据中枢）',
                                          '覆盖 36 个主力/贵金属合约（CL.FUT / RB0.CN / Au99.99）',
                                          '支持增量更新和全量重下',
                                      ]
                                    : [
                                          'QuantUS parquet 单源（本地 daily_forward 分区）',
                                          'Qlib 缓存从 parquet 构建（.qlib_cache/us_data）',
                                          '覆盖 500+ 只美股，2001 年起历史数据',
                                          '支持增量更新和全量重建',
                                      ]
                        ).map((text, i) => (
                            <li
                                key={i}
                                className="flex items-start text-xs text-slate-500 font-medium"
                            >
                                <CheckCircleFilled className="text-emerald-500 mt-0.5 mr-2" />
                                {text}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* 操作按钮 */}
            <Space direction="vertical" className="w-full" size="middle">
                {selectedMarket === 'a_share' ? (
                    <>
                        <Button
                            type="primary"
                            block
                            className="h-12 rounded-2xl bg-blue-600 hover:bg-blue-700 border-none font-black text-sm shadow-lg shadow-blue-100 transition-all flex items-center justify-center"
                            loading={dailySyncLoading}
                            onClick={() => {
                                dataPlatformService
                                    .checkQuantDBDiff()
                                    .then((result) => {
                                        const behind = result.datasets.filter(
                                            (d: any) => d.status === 'updates_available',
                                        );
                                        const notSynced = result.datasets.filter(
                                            (d: any) => d.status === 'not_synced',
                                        );
                                        if (behind.length === 0 && notSynced.length === 0) {
                                            message.success('所有数据集均为最新，无需同步');
                                        } else {
                                            message.info(
                                                `${behind.length} 个数据集有更新，${notSynced.length} 个未同步，开始增量同步...`,
                                            );
                                            onDailySync(true);
                                        }
                                    })
                                    .catch(() => {
                                        onDailySync(true);
                                    });
                            }}
                            icon={<CloudSyncOutlined />}
                            disabled={!!syncTaskId}
                        >
                            智能同步（先检查更新）
                        </Button>
                        <Button
                            block
                            className="h-12 rounded-2xl bg-indigo-600 hover:bg-indigo-700 border-none font-black text-sm shadow-lg shadow-indigo-100 transition-all flex items-center justify-center"
                            loading={dailySyncLoading}
                            onClick={() => onDailySync(true)}
                            icon={<SyncOutlined />}
                            disabled={!!syncTaskId}
                        >
                            直接增量同步（QuantDB）
                        </Button>
                        <Button
                            block
                            className="h-12 rounded-2xl border-slate-200 text-slate-600 font-bold hover:bg-slate-50 transition-all"
                            loading={dailySyncLoading}
                            onClick={() => onDailySync(false)}
                            icon={<CloudDownloadOutlined />}
                            disabled={!!syncTaskId}
                        >
                            全量同步
                        </Button>
                        <Button
                            block
                            className="h-12 rounded-2xl border-slate-200 text-slate-600 font-bold hover:bg-slate-50 transition-all"
                            loading={syncLoading}
                            onClick={onSyncOfficialData}
                            icon={<ThunderboltOutlined />}
                        >
                            旧版全量同步
                        </Button>
                        <Divider className="!my-2" />
                        <Button
                            block
                            className="h-12 rounded-2xl bg-emerald-600 hover:bg-emerald-700 border-none text-white font-black text-sm shadow-lg shadow-emerald-100 transition-all"
                            loading={parquetLoading}
                            onClick={() => onUpdateFeatureParquet(false)}
                            icon={<LineChartOutlined />}
                        >
                            更新特征快照（补充缺失日期）
                        </Button>
                        <Button
                            block
                            className="h-12 rounded-2xl border-amber-200 text-amber-700 font-bold hover:bg-amber-50 transition-all"
                            loading={parquetLoading}
                            onClick={() => onUpdateFeatureParquet(true)}
                            icon={<SyncOutlined />}
                        >
                            全量重建特征（覆盖全部日期）
                        </Button>
                    </>
                ) : (
                    <>
                        <Button
                            type="primary"
                            block
                            className={`h-14 rounded-2xl border-none font-black text-sm shadow-lg transition-all flex items-center justify-center bg-gradient-to-r ${currentMarketCfg.gradient} hover:opacity-90`}
                            loading={marketSyncing === selectedMarket}
                            onClick={() =>
                                onSyncMarket(selectedMarket, currentMarket?.data_ready)
                            }
                            icon={<SyncOutlined />}
                        >
                            {currentMarket?.data_ready
                                ? `重新同步${currentMarketCfg.label}数据`
                                : `开始同步${currentMarketCfg.label}数据`}
                        </Button>
                        {currentMarket?.data_ready && (
                            <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-100">
                                <div className="flex items-center gap-2">
                                    <CheckCircleFilled className="text-emerald-500" />
                                    <Text className="text-xs text-emerald-700 font-bold">
                                        数据已就绪: {currentMarket.h5_info?.symbols}只,{' '}
                                        {currentMarket.h5_info?.rows?.toLocaleString()}行
                                    </Text>
                                </div>
                            </div>
                        )}
                        {!currentMarket?.data_ready && (
                            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-100">
                                <div className="flex items-center gap-2">
                                    <WarningFilled className="text-amber-500" />
                                    <Text className="text-xs text-amber-700 font-bold">
                                        数据未下载，请点击上方按钮同步
                                    </Text>
                                </div>
                            </div>
                        )}
                        {currentMarket?.data_ready && (
                            <>
                                <Divider className="!my-2" />
                                <Button
                                    block
                                    className="h-12 rounded-2xl bg-emerald-600 hover:bg-emerald-700 border-none text-white font-black text-sm shadow-lg shadow-emerald-100 transition-all"
                                    loading={parquetLoading}
                                    onClick={() =>
                                        onUpdateMarketFeatures(selectedMarket, false)
                                    }
                                    icon={<LineChartOutlined />}
                                >
                                    计算{currentMarketCfg.label}特征快照
                                </Button>
                                <Button
                                    block
                                    className="h-12 rounded-2xl border-amber-200 text-amber-700 font-bold hover:bg-amber-50 transition-all"
                                    loading={parquetLoading}
                                    onClick={() =>
                                        onUpdateMarketFeatures(selectedMarket, true)
                                    }
                                    icon={<SyncOutlined />}
                                >
                                    全量重建{currentMarketCfg.label}特征
                                </Button>
                                {(selectedMarket === 'hong_kong' ||
                                    selectedMarket === 'us_stock') && (
                                    <>
                                        <Divider className="!my-2" />
                                        <Button
                                            block
                                            className="h-12 rounded-2xl bg-purple-600 hover:bg-purple-700 border-none text-white font-black text-sm shadow-lg shadow-purple-100 transition-all"
                                            loading={fundamentalsLoading}
                                            onClick={() =>
                                                onSyncFundamentals(
                                                    selectedMarket === 'hong_kong'
                                                        ? 'HK'
                                                        : 'US',
                                                )
                                            }
                                            icon={<StockOutlined />}
                                        >
                                            同步{currentMarketCfg.label}基本面
                                            (PE/PB/ROE)
                                        </Button>
                                    </>
                                )}
                            </>
                        )}
                    </>
                )}
                {syncTaskProgress && (
                    <div className="p-4 rounded-2xl bg-blue-50 border border-blue-100 space-y-3">
                        <div className="flex items-center gap-2">
                            <Spin size="small" />
                            <Text className="text-xs text-blue-600 font-bold">
                                {syncStepProgress?.detail || syncTaskProgress}
                            </Text>
                        </div>
                        {syncStepProgress && syncStepProgress.pct > 0 && (
                            <div>
                                <Progress
                                    percent={syncStepProgress.pct}
                                    size="small"
                                    strokeColor={{ from: '#6366f1', to: '#10b981' }}
                                    format={(pct) => (
                                        <span className="text-[10px] font-bold text-slate-500">
                                            {pct}%
                                        </span>
                                    )}
                                />
                                {syncStepProgress.total > 0 && (
                                    <Text className="text-[10px] text-slate-400 mt-1 block">
                                        {syncStepProgress.current}/
                                        {syncStepProgress.total} 只股票
                                    </Text>
                                )}
                            </div>
                        )}
                        <div className="flex gap-1">
                            {[
                                'init',
                                'pg_query',
                                'data_sync',
                                'qlib_bin',
                                'calibrate',
                                'parquet',
                                'done',
                            ].map((s, i) => {
                                const stepOrder = [
                                    'init',
                                    'pg_query',
                                    'data_sync',
                                    'qlib_bin',
                                    'calibrate',
                                    'parquet',
                                    'done',
                                ];
                                const currentIdx = stepOrder.indexOf(
                                    syncStepProgress?.step || '',
                                );
                                const isActive = i === currentIdx;
                                const isDone = i < currentIdx;
                                return (
                                    <div
                                        key={s}
                                        className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                                            isDone
                                                ? 'bg-emerald-400'
                                                : isActive
                                                  ? 'bg-indigo-500 animate-pulse'
                                                  : 'bg-slate-200'
                                        }`}
                                    />
                                );
                            })}
                        </div>
                        <div className="flex justify-between text-[8px] text-slate-400 font-medium">
                            <span>初始化</span>
                            <span>PG</span>
                            <span>同步</span>
                            <span>Qlib</span>
                            <span>指标</span>
                            <span>Parquet</span>
                            <span>完成</span>
                        </div>
                    </div>
                )}
                {parquetResult && (
                    <div
                        className={`p-4 rounded-2xl border ${
                            parquetResult.success
                                ? 'bg-emerald-50 border-emerald-100'
                                : 'bg-rose-50 border-rose-100'
                        }`}
                    >
                        <Text
                            className={`text-xs font-bold ${
                                parquetResult.success
                                    ? 'text-emerald-600'
                                    : 'text-rose-600'
                            }`}
                        >
                            {parquetResult.success ? '更新成功' : '更新失败'} (exit=
                            {parquetResult.exit_code})
                        </Text>
                        {parquetResult.stdout && (
                            <pre className="mt-2 text-[10px] text-slate-500 bg-white p-2 rounded-lg max-h-32 overflow-auto whitespace-pre-wrap">
                                {parquetResult.stdout.slice(-1000)}
                            </pre>
                        )}
                        {parquetResult.stderr && !parquetResult.success && (
                            <pre className="mt-2 text-[10px] text-rose-500 bg-white p-2 rounded-lg max-h-32 overflow-auto whitespace-pre-wrap">
                                {parquetResult.stderr.slice(-1000)}
                            </pre>
                        )}
                    </div>
                )}
                {fundamentalsResult && (
                    <div
                        className={`p-4 rounded-2xl border ${
                            fundamentalsResult.success
                                ? 'bg-emerald-50 border-emerald-100'
                                : 'bg-rose-50 border-rose-100'
                        }`}
                    >
                        <Text
                            className={`text-xs font-bold ${
                                fundamentalsResult.success
                                    ? 'text-emerald-600'
                                    : 'text-rose-600'
                            }`}
                        >
                            {fundamentalsResult.success
                                ? '基本面同步成功'
                                : '基本面同步失败'}
                        </Text>
                        {fundamentalsResult.data?.result && (
                            <pre className="mt-2 text-[10px] text-slate-500 bg-white p-2 rounded-lg max-h-32 overflow-auto whitespace-pre-wrap">
                                {JSON.stringify(
                                    fundamentalsResult.data.result,
                                    null,
                                    2,
                                )}
                            </pre>
                        )}
                        {fundamentalsResult.data?.results && (
                            <pre className="mt-2 text-[10px] text-slate-500 bg-white p-2 rounded-lg max-h-32 overflow-auto whitespace-pre-wrap">
                                {JSON.stringify(
                                    fundamentalsResult.data.results,
                                    null,
                                    2,
                                )}
                            </pre>
                        )}
                    </div>
                )}
            </Space>

            {/* 提示信息 */}
            <div className="bg-amber-50 border border-amber-100 p-4 rounded-2xl">
                <div className="flex items-start">
                    <InfoCircleOutlined className="text-amber-500 mt-0.5 mr-2" />
                    <Text className="text-[11px] text-amber-700 font-medium leading-relaxed">
                        {selectedMarket === 'a_share'
                            ? '增量同步：QuantDB A股 → parquet → PG → Qlib 缓存（A 股唯一数据源）。Celery Beat 已配置每日 18:00 自动执行。'
                            : selectedMarket === 'crypto'
                              ? '加密货币数据从 Binance 公开 API 下载 5 分钟 K 线，转换为 Qlib bin 格式。数据量较大，首次同步需要 20-30 分钟。'
                              : selectedMarket === 'hong_kong'
                                ? '港股数据从 QuantHK parquet 单源读取，Qlib 缓存由 parquet 构建（.qlib_cache/hk_data），覆盖 3000+ 标的、1980 年起历史。'
                                : selectedMarket === 'futures'
                                  ? '期货数据源按勾选分发：akshare（国际期货/国内商品/上金所贵金属），落盘本地 parquet，Qlib 缓存从 parquet 构建。'
                                  : '美股数据从 QuantUS parquet 单源读取，Qlib 缓存由 parquet 构建（.qlib_cache/us_data），覆盖 500+ 标的、2001 年起历史。'}
                    </Text>
                </div>
            </div>
        </div>
    </Card>
);

interface IssueTrackerProps {
    olderSamples: AdminFeatureSnapshotsOlderSample[];
    invalidSamples: AdminFeatureSnapshotsInvalidSample[];
    sampleSize: number;
    olderColumns: any[];
    invalidColumns: any[];
}

const IssueTrackerCards: React.FC<IssueTrackerProps> = ({
    olderSamples,
    invalidSamples,
    sampleSize,
    olderColumns,
    invalidColumns,
}) => {
    if (olderSamples.length === 0 && invalidSamples.length === 0) return null;

    return (
        <div className="space-y-6">
            <Card
                title={
                    <span className="font-black text-rose-500 tracking-tight uppercase text-sm flex items-center">
                        <WarningFilled className="mr-2" /> 数据滞后（Top {sampleSize}）
                    </span>
                }
                className="rounded-3xl border-none shadow-xl shadow-slate-200/20"
                styles={{ body: { padding: '0 12px 12px' } }}
            >
                <Table<AdminFeatureSnapshotsOlderSample>
                    size="small"
                    pagination={false}
                    rowKey={(r) => `${r.symbol}-${r.last_date}`}
                    dataSource={olderSamples}
                    columns={olderColumns}
                    className="custom-table"
                    locale={{ emptyText: '无滞后数据' }}
                    scroll={{ y: 240 }}
                />
            </Card>
            <Card
                title={
                    <span className="font-black text-slate-400 tracking-tight uppercase text-sm flex items-center">
                        <InfoCircleOutlined className="mr-2" /> 无效文件
                    </span>
                }
                className="rounded-3xl border-none shadow-xl shadow-slate-200/20"
                styles={{ body: { padding: '0 12px 12px' } }}
            >
                <Table<AdminFeatureSnapshotsInvalidSample>
                    size="small"
                    pagination={false}
                    rowKey={(r) => `${r.symbol}-${r.reason}-${r.file || ''}`}
                    dataSource={invalidSamples}
                    columns={invalidColumns}
                    className="custom-table"
                    locale={{ emptyText: '所有文件正常' }}
                    scroll={{ y: 240 }}
                />
            </Card>
        </div>
    );
};

interface AdminRightColumnProps {
    selectedMarket: string;
    currentMarketCfg: { label: string; gradient: string; color: string };
    currentMarket: any;
    dailySyncLoading: boolean;
    syncLoading: boolean;
    parquetLoading: boolean;
    fundamentalsLoading: boolean;
    marketSyncing: string | null;
    syncTaskId: string | null;
    syncTaskProgress: string;
    syncStepProgress: {
        step: string;
        detail: string;
        pct: number;
        current: number;
        total: number;
    } | null;
    parquetResult: any;
    fundamentalsResult: any;
    syncStatus: any;
    syncStatusLoading: boolean;
    snapshots: any;
    olderSamples: AdminFeatureSnapshotsOlderSample[];
    invalidSamples: AdminFeatureSnapshotsInvalidSample[];
    sampleSize: number;
    olderColumns: any[];
    invalidColumns: any[];
    onReloadSyncStatus: () => void;
    onDailySync: (incremental: boolean) => void;
    onSyncOfficialData: () => void;
    onUpdateFeatureParquet: (rebuild: boolean) => void;
    onUpdateMarketFeatures: (market: string, rebuild: boolean) => void;
    onSyncFundamentals: (market: string) => void;
    onSyncMarket: (marketId: string, dataReady: boolean) => void;
}

export const AdminRightColumn: React.FC<AdminRightColumnProps> = ({
    selectedMarket,
    currentMarketCfg,
    currentMarket,
    dailySyncLoading,
    syncLoading,
    parquetLoading,
    fundamentalsLoading,
    marketSyncing,
    syncTaskId,
    syncTaskProgress,
    syncStepProgress,
    parquetResult,
    fundamentalsResult,
    syncStatus,
    syncStatusLoading,
    snapshots,
    olderSamples,
    invalidSamples,
    sampleSize,
    olderColumns,
    invalidColumns,
    onReloadSyncStatus,
    onDailySync,
    onSyncOfficialData,
    onUpdateFeatureParquet,
    onUpdateMarketFeatures,
    onSyncFundamentals,
    onSyncMarket,
}) => (
    <Col span={24} lg={9} className="space-y-8">
        <MaintenancePanel
            selectedMarket={selectedMarket}
            currentMarketCfg={currentMarketCfg}
            currentMarket={currentMarket}
            dailySyncLoading={dailySyncLoading}
            syncLoading={syncLoading}
            parquetLoading={parquetLoading}
            fundamentalsLoading={fundamentalsLoading}
            marketSyncing={marketSyncing}
            syncTaskId={syncTaskId}
            syncTaskProgress={syncTaskProgress}
            syncStepProgress={syncStepProgress}
            parquetResult={parquetResult}
            fundamentalsResult={fundamentalsResult}
            onDailySync={onDailySync}
            onSyncOfficialData={onSyncOfficialData}
            onUpdateFeatureParquet={onUpdateFeatureParquet}
            onUpdateMarketFeatures={onUpdateMarketFeatures}
            onSyncFundamentals={onSyncFundamentals}
            onSyncMarket={onSyncMarket}
        />

        <SyncStatusCard
            syncStatus={syncStatus}
            syncStatusLoading={syncStatusLoading}
            onReload={onReloadSyncStatus}
        />

        {snapshots?.exists && (
            <IssueTrackerCards
                olderSamples={olderSamples}
                invalidSamples={invalidSamples}
                sampleSize={sampleSize}
                olderColumns={olderColumns}
                invalidColumns={invalidColumns}
            />
        )}
    </Col>
);
