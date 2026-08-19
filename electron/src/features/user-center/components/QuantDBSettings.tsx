import React, { useCallback, useEffect, useState } from 'react';
import {
  Database, Key, ShieldCheck, CheckCircle2, AlertCircle, RefreshCw,
  HardDrive, Activity, Eye, EyeOff, Save, Check, ExternalLink, Zap
} from 'lucide-react';
import { Button, Input, Tag, message, Spin, Alert, Tooltip } from 'antd';
import { dataPlatformService, QuantDBConfig, QuantDBInfo } from '../../admin/services/dataPlatformService';

export const QuantDBSettings: React.FC = () => {
  const [config, setConfig] = useState<QuantDBConfig | null>(null);
  const [info, setInfo] = useState<QuantDBInfo | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setRefreshing(true);
      const [cfg, sdkInfo] = await Promise.allSettled([
        dataPlatformService.getQuantDBConfig(),
        dataPlatformService.getQuantDBInfo(),
      ]);

      if (cfg.status === 'fulfilled') {
        setConfig(cfg.value);
      }
      if (sdkInfo.status === 'fulfilled') {
        setInfo(sdkInfo.value?.quantdb || (sdkInfo.value as any));
      }
    } catch (e: any) {
      console.error('加载 QuantDB 状态失败:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSave = async () => {
    const trimmed = apiKey.trim();
    if (trimmed.length < 8) {
      message.warning('请输入完整的 API Key（至少 8 位）');
      return;
    }

    setSaving(true);
    setVerifyError(null);
    try {
      const result = await dataPlatformService.saveQuantDBConfig(trimmed);
      if (result.verified) {
        message.success('QuantDB API Key 已成功保存并验证通过！');
      } else {
        setVerifyError(result.error ?? '未知原因');
        message.warning('API Key 已保存，但连接测试未通过，请检查 Key 有效性');
      }
      setApiKey('');
      await loadData();
    } catch (error: any) {
      message.error(`保存失败: ${error?.message || '未知错误'}`);
    } finally {
      setSaving(false);
    }
  };

  const isConfigured = Boolean(config?.api_key_configured);
  const isInstalled = Boolean(info?.installed);
  const isConnected = Boolean(info?.connected);

  return (
    <div className="space-y-6 max-w-5xl">
      {/* 顶部标题卡片 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-200">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-black text-slate-800 m-0">QuantDB 数据源凭据</h3>
                <Tag color={isConfigured ? 'green' : 'default'} className="rounded-lg text-[10px] font-bold m-0 border-0">
                  {isConfigured ? '已授权' : '未授权'}
                </Tag>
              </div>
              <p className="text-xs text-slate-500 m-0 mt-0.5">
                管理 QuantDB A股、行业、财务与机器学习因子等高频数据仓库的访问凭据
              </p>
            </div>
          </div>
          <Button
            icon={<RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />}
            onClick={loadData}
            loading={refreshing}
            className="rounded-xl font-bold text-xs"
          >
            刷新状态
          </Button>
        </div>
      </div>

      {/* 状态指标条 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3.5">
        {/* 1. SDK 状态 */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>SDK 状态</span>
            <HardDrive className="w-4 h-4 text-blue-500" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isInstalled ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
            <span className="text-base font-black text-slate-800">
              {isInstalled ? '已安装就绪' : '待检测/未安装'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-1">
            {info?.version ? `v${info.version}` : 'Python SDK 运行时'}
          </span>
        </div>

        {/* 2. API Key 状态 */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>API Key 状态</span>
            <Key className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isConfigured ? 'bg-emerald-500' : 'bg-rose-400'}`} />
            <span className="text-base font-black text-slate-800">
              {isConfigured ? '已安全配置' : '未配置密钥'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-1 truncate">
            {config?.api_key_masked || '未设置 API 密钥'}
          </span>
        </div>

        {/* 3. 已用流量 */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>已用流量</span>
            <Activity className="w-4 h-4 text-amber-500" />
          </div>
          <div className="mt-2">
            <span className="text-base font-black font-mono text-slate-800">
              {info?.usage?.used_gb != null ? `${info.usage.used_gb} GB` : info?.used_bytes_human || (info?.used_traffic ? `${info.used_traffic}` : '—')}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1">
            {info?.traffic_reset_date ? `周期重置: ${info.traffic_reset_date}` : '本计费周期统计'}
          </span>
        </div>

        {/* 4. 剩余流量 / 配额 */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>剩余配额</span>
            <Zap className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2">
            <span className="text-base font-black font-mono text-emerald-600">
              {info?.usage?.remaining_gb != null ? `${info.usage.remaining_gb} GB` : info?.remaining_bytes_human || (info?.remaining_traffic ? `${info.remaining_traffic}` : '—')}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1">
            {info?.usage?.subscription?.status ? `订阅状态: ${info.usage.subscription.status}` : info?.tier_name ? `当前套餐: ${info.tier_name}` : '高速同步配额'}
          </span>
        </div>
      </div>

      {/* API Key 输入与管理卡片 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs space-y-4">
        <div className="border-b border-slate-100 pb-3">
          <h4 className="text-sm font-bold text-slate-800 m-0">API Key 绑定与更新</h4>
          <p className="text-xs text-slate-400 m-0 mt-0.5">
            请输入您在 QuantDB 官方平台获取的 API 访问秘钥进行授权绑定
          </p>
        </div>

        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            <div className="relative flex-1">
              <Input
                type={showKey ? 'text' : 'password'}
                placeholder={isConfigured ? `已配置: ${config?.api_key_masked} (输入新 Key 进行覆盖)` : '粘贴 QuantDB API Key (如 qk_...)'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                onPressEnter={handleSave}
                className="rounded-xl h-10 font-mono text-xs pr-10"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors p-1"
                title={showKey ? '隐藏明文' : '显示明文'}
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <Button
              type="primary"
              icon={<Save className="w-4 h-4" />}
              onClick={handleSave}
              loading={saving}
              className="rounded-xl h-10 px-5 font-bold bg-blue-600 shadow-sm"
            >
              保存并验证
            </Button>
          </div>

          {verifyError && (
            <Alert
              type="warning"
              showIcon
              message="Key 已写入，但 QuantDB 握手验证未通过"
              description={verifyError}
              closable
              onClose={() => setVerifyError(null)}
              className="rounded-xl text-xs"
            />
          )}

          <div className="p-3.5 bg-slate-50/70 border border-slate-100 rounded-xl space-y-1.5 text-xs text-slate-500">
            <div className="flex items-center gap-1.5 font-semibold text-slate-700">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>安全与生效说明</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-slate-500 pl-1">
              <li>API Key 经加密写入系统本地运行时密钥文件，服务重启仍有效，页面只展示脱敏指纹。</li>
              <li>点击「保存并验证」后系统会向 QuantDB 网关发送轻量探测请求以确认账户配额。</li>
              <li>若操作系统环境变量 <code className="text-slate-700 font-mono font-bold">QUANTDB_API_KEY</code> 已设定，系统将自动优先采用环境变量。</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 运行时路径与存储信息 */}
      {config && (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">本地存储与运行环境</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex flex-col gap-1">
              <span className="text-[11px] text-slate-400 font-medium">数据仓库落盘目录</span>
              <span className="font-mono text-slate-700 font-bold break-all">{config.data_dir || '/data/quantdb'}</span>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex flex-col gap-1">
              <span className="text-[11px] text-slate-400 font-medium">运行时密钥配置文件</span>
              <span className="font-mono text-slate-700 font-bold break-all">{config.runtime_env_file || 'config/runtime.env'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuantDBSettings;
