import React, { useEffect, useState } from 'react';
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  Key,
  RefreshCw,
  Settings,
  ShieldCheck,
  Cable,
  Wifi,
} from 'lucide-react';
import { SERVICE_URLS } from '../../../config/services';

// 与后端 ApiKeyInfo 对齐：/api-keys/init 是幂等接口，永不返回 secret_key
interface ApiKeyInfo {
  id: number;
  access_key: string;
  name: string;
  permissions: string[];
  is_active: boolean;
  created_at: string;
  expires_at?: string | null;
  last_used_at?: string | null;
}

interface RotateSecretInfo {
  access_key: string;
  secret_key: string;
}

interface TdxConfig {
  enabled: boolean;
  bridge_url: string;
  bridge_token_configured: boolean;
  real_trading_enabled: boolean;
  broker_type: string;
  health?: { status?: string; tdx_connected?: boolean; error?: string } | null;
}

interface SettingsCenterProps {
  userId: string;
  isActive: boolean;
}

const SettingsCenter: React.FC<SettingsCenterProps> = ({ userId, isActive }) => {
  const apiGatewayBase = SERVICE_URLS.API_GATEWAY.replace(/\/+$/, '');
  const authHeader = () => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  });

  const [copied, setCopied] = useState('');
  const [keyInfo, setKeyInfo] = useState<ApiKeyInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAccessKey, setShowAccessKey] = useState(false);
  const [showSecretKey, setShowSecretKey] = useState(false);
  const [secretKey, setSecretKey] = useState<string | null>(null);

  // 通达信桥配置
  const [tdxConfig, setTdxConfig] = useState<TdxConfig | null>(null);
  const [tdxLoading, setTdxLoading] = useState(false);
  const [tdxNewToken, setTdxNewToken] = useState('');
  const [tdxNewUrl, setTdxNewUrl] = useState('');
  const [tdxMsg, setTdxMsg] = useState('');

  const handleCopy = async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(''), 2000);
  };

  const maskValue = (value: string) => value.replace(/(.{8}).*(.{4})$/, '$1••••••••••••$2');

  const fetchBootstrap = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiGatewayBase}/api/v1/api-keys/init`, {
        method: 'POST',
        headers: authHeader(),
      });
      if (!res.ok) {
        throw new Error('init failed');
      }
      const data: ApiKeyInfo = await res.json();
      setKeyInfo({
        ...data,
        access_key: String(data.access_key || '').trim(),
      });
    } catch (e) {
      console.error('Failed to init api key', e);
    } finally {
      setLoading(false);
    }
  };

  const rotateSecret = async () => {
    if (!keyInfo?.access_key) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${apiGatewayBase}/api/v1/api-keys/${keyInfo.access_key}/rotate-secret`,
        {
          method: 'POST',
          headers: authHeader(),
        }
      );
      if (!res.ok) {
        throw new Error('rotate secret failed');
      }
      const data: RotateSecretInfo = await res.json();
      setSecretKey(String(data.secret_key || '').trim());
      setShowSecretKey(true);
    } catch (e) {
      console.error('Failed to rotate secret key', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchTdxConfig = async () => {
    setTdxLoading(true);
    try {
      const res = await fetch(`${apiGatewayBase}/api/v1/tdx/config`, {
        headers: authHeader(),
      });
      if (res.ok) {
        const data: TdxConfig = await res.json();
        setTdxConfig(data);
        setTdxNewToken('');
        setTdxNewUrl(data.bridge_url || '');
      }
    } catch (e) {
      console.error('Failed to fetch tdx config', e);
    } finally {
      setTdxLoading(false);
    }
  };

  const updateTdxConfig = async () => {
    setTdxLoading(true);
    setTdxMsg('');
    try {
      const payload: Record<string, string> = {};
      if (tdxNewToken.trim()) payload.bridge_token = tdxNewToken.trim();
      if (tdxNewUrl.trim()) payload.bridge_url = tdxNewUrl.trim();
      const res = await fetch(`${apiGatewayBase}/api/v1/tdx/config`, {
        method: 'POST',
        headers: authHeader(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('update failed');
      setTdxMsg('✅ 通达信桥配置已更新');
      await fetchTdxConfig();
    } catch (e) {
      setTdxMsg(`❌ 更新失败: ${e}`);
    } finally {
      setTdxLoading(false);
    }
  };

  useEffect(() => {
    if (!isActive) return;
    fetchBootstrap();
    fetchTdxConfig();
  }, [isActive, userId]);

  if (!isActive) return null;

  return (
    <div className="h-full flex flex-col p-4 bg-gray-50/30 overflow-y-auto custom-scrollbar">
      <div className="mb-4 pb-3 border-b border-gray-200">
        <h3 className="text-xl font-bold text-gray-800 flex items-center">
          <Settings className="mr-3 text-blue-600" size={24} />
          模拟交易设置
        </h3>
        <p className="text-xs text-gray-500 mt-1">
          管理接入凭证与 API 密钥。
        </p>
      </div>

      <div className="bg-white rounded-3xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-5 flex flex-col gap-4">
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-bold text-gray-900">接入凭证</div>
                <div className="text-xs text-gray-500 mt-1">
                  Access Key 用于鉴权，Secret Key 仅在重置后展示一次，请立即保存。
                </div>
              </div>
              <button
                onClick={fetchBootstrap}
                disabled={loading}
                className="shrink-0 text-xs text-indigo-500 hover:text-indigo-700 font-medium flex items-center gap-1"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                刷新
              </button>
            </div>

            <div className="space-y-3">
              <div className="rounded-2xl border border-gray-100 bg-white px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-indigo-50 rounded-xl text-indigo-600 shrink-0">
                    <Key size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-gray-500 mb-1">Access Key</div>
                    <div className="flex items-center gap-2 min-w-0 bg-white px-3 py-2 rounded-2xl border border-gray-100">
                      <code className="text-xs font-mono text-indigo-700 truncate flex-1">
                        {keyInfo ? (showAccessKey ? keyInfo.access_key : maskValue(keyInfo.access_key)) : '-'}
                      </code>
                      {keyInfo && (
                        <>
                          <button onClick={() => setShowAccessKey(!showAccessKey)} className="p-1 text-gray-500 hover:text-gray-700">
                            {showAccessKey ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                          <button onClick={() => handleCopy(keyInfo.access_key, 'access_key')} className="p-1 text-gray-500 hover:text-indigo-600">
                            {copied === 'access_key' ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                          </button>
                          <div className={`hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${keyInfo.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                            <ShieldCheck size={10} />
                            {keyInfo.is_active ? '可用' : '已禁用'}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-gray-100 bg-white px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-amber-50 rounded-xl text-amber-700 shrink-0">
                    <Key size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-gray-500 mb-1">Secret Key</div>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-2xl border border-gray-100 flex-1 min-w-0">
                        <code className="text-xs font-mono text-amber-900 truncate flex-1">
                          {secretKey ? (showSecretKey ? secretKey : maskValue(secretKey)) : '未展示，点击右侧按钮重新生成'}
                        </code>
                        {secretKey && (
                          <>
                            <button onClick={() => setShowSecretKey(!showSecretKey)} className="p-1 text-gray-500 hover:text-gray-700">
                              {showSecretKey ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                            <button onClick={() => handleCopy(secretKey, 'secret_key')} className="p-1 text-gray-500 hover:text-amber-700">
                              {copied === 'secret_key' ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                            </button>
                          </>
                        )}
                      </div>
                      <button
                        onClick={rotateSecret}
                        disabled={!keyInfo || loading}
                        className="shrink-0 px-3 py-2 rounded-xl bg-gray-900 text-white text-xs font-bold hover:bg-black disabled:opacity-50"
                      >
                        重置密钥
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 通达信交易桥卡片 */}
      <div className="bg-white rounded-3xl border border-gray-200 shadow-sm overflow-hidden mt-4">
        <div className="p-5 flex flex-col gap-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-bold text-gray-900 flex items-center">
                <Cable className="mr-2 text-emerald-600" size={16} />
                通达信交易桥
              </div>
              <div className="text-xs text-gray-500 mt-1">
                QuantMind 通过桥连接 Windows 通达信，推送选股/下单/拉取账户状态。
              </div>
            </div>
            <button
              onClick={fetchTdxConfig}
              disabled={tdxLoading}
              className="shrink-0 text-xs text-emerald-600 hover:text-emerald-700 font-medium flex items-center gap-1"
            >
              <RefreshCw size={14} className={tdxLoading ? 'animate-spin' : ''} />
              刷新
            </button>
          </div>

          {tdxConfig && (
            <>
              <div className="flex flex-wrap gap-2">
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${tdxConfig.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                  <Wifi size={11} />
                  自动推送: {tdxConfig.enabled ? '开启' : '关闭'}
                </span>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${tdxConfig.real_trading_enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                  <ShieldCheck size={11} />
                  实盘: {tdxConfig.real_trading_enabled ? '开启' : '关闭'}
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-blue-100 text-blue-700">
                  桥: {tdxConfig.bridge_url || '-'}
                </span>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${tdxConfig.bridge_token_configured ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  Token: {tdxConfig.bridge_token_configured ? '已配置' : '未配置'}
                </span>
              </div>

              {tdxConfig.health && (
                <div className={`rounded-2xl border px-4 py-3 text-xs ${tdxConfig.health.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
                  {tdxConfig.health.error
                    ? `桥不可达: ${tdxConfig.health.error}`
                    : `桥在线 · 通达信客户端: ${tdxConfig.health.tdx_connected ? '已连接' : '未登录(17709)'}`}
                </div>
              )}

              <div className="space-y-3">
                <div>
                  <div className="text-xs text-gray-500 mb-1">桥地址</div>
                  <input
                    type="text"
                    value={tdxNewUrl}
                    onChange={(e) => setTdxNewUrl(e.target.value)}
                    placeholder="http://192.168.31.39:8550"
                    className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">桥 Token (64位 hex, 与 Windows 侧一致)</div>
                  <input
                    type="text"
                    value={tdxNewToken}
                    onChange={(e) => setTdxNewToken(e.target.value)}
                    placeholder="输入新 token (留空则保持现有)"
                    className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                {tdxMsg && <div className="text-xs font-medium text-gray-700">{tdxMsg}</div>}
                <button
                  onClick={updateTdxConfig}
                  disabled={tdxLoading || (!tdxNewToken.trim() && !tdxNewUrl.trim())}
                  className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 disabled:opacity-50"
                >
                  保存配置
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SettingsCenter;
