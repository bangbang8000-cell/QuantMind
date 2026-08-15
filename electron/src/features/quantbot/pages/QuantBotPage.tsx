/**
 * QuantBot 主页面 — 完整嵌入 QwenPaw 智能体 Web 界面
 *
 * QwenPaw 是项目的大脑，提供完整 AI 智能体能力：
 * 执行命令、写代码、跑回测、跑因子挖掘、获取股票数据 AI 分析、获取新闻数据等。
 *
 * 加载策略：
 * - Web 浏览器端：通过当前域名的 /api/v1/qwenpaw-ui/ 反向代理（局域网访问同样适用）
 * - Electron 桌面端：通过用户配置的服务器地址代理；未配置时回退本机 8089
 */

import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Bot, RefreshCw, Wifi, WifiOff, ExternalLink, AlertTriangle } from 'lucide-react';
import { isElectronEnv, SERVICE_URLS } from '../../../config/services';

const QWENPAW_UI_PATH = '/api/v1/qwenpaw-ui/';
/** 无任何服务器配置时的兜底地址（QwenPaw 容器宿主映射端口） */
const QWENPAW_LOCAL_FALLBACK_URL = 'http://127.0.0.1:8089/';

/** iframe 加载超时时间（毫秒） */
const IFRAME_LOAD_TIMEOUT_MS = 15_000;

const QuantBotPage: React.FC = () => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [iframeKey, setIframeKey] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [connected, setConnected] = useState<boolean>(false);
  const [timedOut, setTimedOut] = useState<boolean>(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const embedUrl = useMemo(() => {
    // Web 模式：走当前访问域名的 nginx 代理，天然支持局域网/公网访问
    if (!isElectronEnv() && typeof window !== 'undefined') {
      return `${window.location.origin}${QWENPAW_UI_PATH}`;
    }
    // 桌面端：走用户配置的服务器地址代理，避免硬编码 127.0.0.1 在远程/局域网场景拒连
    const gateway = SERVICE_URLS.API_GATEWAY;
    if (gateway) {
      return `${gateway}${QWENPAW_UI_PATH}`;
    }
    return QWENPAW_LOCAL_FALLBACK_URL;
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const handleReload = useCallback(() => {
    setLoading(true);
    setConnected(false);
    setTimedOut(false);
    clearTimer();
    setIframeKey(iframeKey + 1);
  }, [clearTimer]);

  const handleOpenExternal = useCallback(() => {
    window.open(embedUrl, '_blank');
  }, [embedUrl]);

  const handleIframeLoad = useCallback(() => {
    clearTimer();
    setLoading(false);
    setConnected(true);
    setTimedOut(false);
  }, [clearTimer]);

  const handleIframeError = useCallback(() => {
    clearTimer();
    setLoading(false);
    setConnected(false);
    setTimedOut(true);
  }, [clearTimer]);

  useEffect(() => {
    setLoading(true);
    setConnected(false);
    setTimedOut(false);
    clearTimer();

    // 启动超时计时器：如果 iframe 在指定时间内未触发 onLoad，标记为超时
    timerRef.current = setTimeout(() => {
      setLoading(false);
      setTimedOut(true);
    }, IFRAME_LOAD_TIMEOUT_MS);

    return () => {
      clearTimer();
    };
  }, [iframeKey, clearTimer]);

  return (
    <div className="w-full h-full flex flex-col overflow-hidden bg-[#1a1a1a]">
      {/* 顶部工具栏 — 极简，最大保留内容区域 */}
      <div className="h-[40px] flex-shrink-0 bg-[#1e1e1e] border-b border-[#333] flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <span className="text-sm font-medium text-gray-300">QuantBot · QwenPaw</span>
        </div>

        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1 text-xs ${connected ? 'text-emerald-400' : timedOut ? 'text-red-400' : loading ? 'text-amber-400' : 'text-red-400'}`}>
            {connected ? <Wifi className="w-3.5 h-3.5" /> : timedOut ? <AlertTriangle className="w-3.5 h-3.5" /> : loading ? <div className="w-3.5 h-3.5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" /> : <WifiOff className="w-3.5 h-3.5" />}
            <span>{connected ? '已连接' : timedOut ? '连接超时' : loading ? '连接中…' : '断开'}</span>
          </div>
          <button
            onClick={handleOpenExternal}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 hover:text-gray-200 hover:bg-[#333] transition-colors"
            title="在外部浏览器打开"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleReload}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 hover:text-gray-200 hover:bg-[#333] transition-colors"
            title="重新加载"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* iframe 内容区域— 无缝全屏嵌入 */}
      <div className="flex-1 relative overflow-hidden bg-[#1a1a1a]">
        {loading && !timedOut && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#1a1a1a]">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <div className="text-center">
                <p className="text-sm text-gray-400">QwenPaw 智能体加载中…</p>
                <p className="text-xs text-gray-500 mt-1">AI Brain · Code · Backtest · Factor · Data</p>
              </div>
            </div>
          </div>
        )}

        {timedOut && !connected && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#1a1a1a]">
            <div className="flex flex-col items-center gap-4 max-w-md text-center">
              <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                <AlertTriangle className="w-7 h-7 text-red-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-300">QwenPaw 未部署或未启动</p>
                <p className="text-xs text-gray-400 mt-2">
                  请按文档部署并启动 QwenPaw 智能体服务：
                </p>
                <code className="block mt-2 px-3 py-1.5 bg-[#2a2a2a] rounded text-xs text-emerald-400/90 font-mono">
                  docker-compose up -d qwenpaw
                </code>
              </div>
              <button
                onClick={handleReload}
                className="flex items-center gap-2 mt-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                重新连接
              </button>
            </div>
          </div>
        )}

        <iframe
          ref={iframeRef}
          key={iframeKey}
          src={embedUrl}
          className="w-full h-full border-0"
          title="QwenPaw Agent"
          allow="clipboard-read; clipboard-write; fullscreen; microphone; camera"
          sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-popups-to-escape-sandbox allow-modals allow-presentation"
          onLoad={handleIframeLoad}
          onError={handleIframeError}
        />
      </div>
    </div>
  );
};

export default QuantBotPage;