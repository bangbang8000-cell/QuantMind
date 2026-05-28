import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Square, Compass } from 'lucide-react';
import { TaskConfig } from '../types-v2';
import { alphaAgentService, MarketInfo } from '../services/alphaAgentService';

const MARKET_EMOJI: Record<string, string> = {
  a_share: '🇨🇳',
  crypto: '₿',
  hong_kong: '🇭🇰',
  us_stock: '🇺🇸',
};

interface ChatInputProps {
  onSubmit: (config: TaskConfig) => void;
  onStop?: () => void;
  isRunning?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSubmit, onStop, isRunning = false }) => {
  const [input, setInput] = useState('');
  const [useCustomMiningDirection, setUseCustomMiningDirection] = useState(false);
  const [miningMarket, setMiningMarket] = useState<string>('a_share');
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [config] = useState<Partial<TaskConfig>>({
    librarySuffix: '',
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    alphaAgentService.listMarkets().then(setMarkets).catch(() => {});
  }, []);

  const examplePrompts = [
    '💹 挖掘动量类因子，关注短期反转和成交量配合',
    '💰 探索价值成长组合，考虑行业中性化',
    '📊 基于技术指标构建因子，重点RSI和MACD',
  ];

  const handleSubmit = () => {
    if (isRunning) return;
    const suffix = config.librarySuffix?.trim() || undefined;
    onSubmit({
      userInput: input.trim(),
      useCustomMiningDirection,
      miningMarket: miningMarket as TaskConfig['miningMarket'],
      ...config,
      librarySuffix: suffix,
    } as TaskConfig);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  return (
    <div className="fixed left-0 right-0 z-50 pb-2" style={{ bottom: '88px' }}>
      <div className="container mx-auto px-6">

        {/* Market Selector */}
        <div className="flex justify-center gap-2 mb-3">
          {markets.length > 0 ? (
            markets.map((m) => (
              <button
                key={m.market_id}
                onClick={() => setMiningMarket(m.market_id)}
                disabled={isRunning || !m.data_ready}
                className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs transition-all ${
                  miningMarket === m.market_id
                    ? 'bg-primary/15 text-primary ring-1 ring-primary/30 font-medium'
                    : m.data_ready
                      ? 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                      : 'text-muted-foreground/40 cursor-not-allowed'
                }`}
                title={!m.data_ready ? '数据未就绪' : m.description}
              >
                <span>{MARKET_EMOJI[m.market_id] || '📈'}</span>
                <span>{m.market_name}</span>
                {!m.data_ready && <span className="text-[10px] opacity-50">(待接入)</span>}
              </button>
            ))
          ) : (
            <>
              {[
                { id: 'a_share', name: 'A股', ready: true },
                { id: 'crypto', name: '加密货币', ready: true },
                { id: 'hong_kong', name: '港股', ready: false },
                { id: 'us_stock', name: '美股', ready: false },
              ].map((m) => (
                <button
                  key={m.id}
                  onClick={() => setMiningMarket(m.id)}
                  disabled={isRunning || !m.ready}
                  className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs transition-all ${
                    miningMarket === m.id
                      ? 'bg-primary/15 text-primary ring-1 ring-primary/30 font-medium'
                      : m.ready
                        ? 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                        : 'text-muted-foreground/40 cursor-not-allowed'
                  }`}
                >
                  <span>{MARKET_EMOJI[m.id] || '📈'}</span>
                  <span>{m.name}</span>
                  {!m.ready && <span className="text-[10px] opacity-50">(待接入)</span>}
                </button>
              ))}
            </>
          )}
        </div>

        {/* Example Prompts */}
        {!input && !isRunning && (
          <div className="flex flex-wrap justify-center gap-2 mb-3 overflow-x-auto pb-2 scrollbar-hide">
            {(miningMarket === 'crypto'
              ? [
                  '₿ 挖掘 BTC 短期动量反转因子，关注 5 分钟和 1 小时级别量价背离',
                  '📈 构建加密货币波动率因子，结合交易量变化和链上数据',
                  '🔗 探索 ETH/BTC 相关性因子，用于跨币种套利策略',
                ]
              : examplePrompts
            ).map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => setInput(prompt)}
                className="glass rounded-xl px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:scale-105 transition-all whitespace-nowrap flex items-center gap-2 card-hover"
              >
                <Sparkles className="h-3 w-3" />
                {prompt}
              </button>
            ))}
          </div>
        )}

        {/* Main Input */}
        <div className="gradient-border">
          <div className="gradient-border-content">
            <div className="glass-strong rounded-xl p-4">
              {/* Icon bar: Custom mining direction etc. */}
              <div className="flex items-center gap-1 mb-3">
                <button
                  type="button"
                  onClick={() => setUseCustomMiningDirection(!useCustomMiningDirection)}
                  title={useCustomMiningDirection ? '使用设置中的挖掘方向（已开）' : '使用设置中的挖掘方向（点击开启）'}
                  className={`p-2 rounded-lg transition-all ${
                    useCustomMiningDirection
                      ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                      : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
                  }`}
                >
                  <Compass className="h-4 w-4" />
                </button>
                <span
                  className={`text-xs ml-1 ${
                    useCustomMiningDirection ? 'text-primary font-medium' : 'text-muted-foreground'
                  }`}
                >
                  自选挖掘方向
                </span>
              </div>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={
                      isRunning
                        ? '实验运行中...可以切换到其他页面，任务不会中断'
                        : useCustomMiningDirection
                        ? '已开启自选挖掘方向，将使用「设置 → 挖掘方向」中的选项'
                        : miningMarket === 'crypto'
                          ? '描述加密货币因子挖掘需求，例如：短期动量反转、量价背离、波动率突破...'
                          : '描述因子挖掘需求，或开启「自选挖掘方向」使用设置中的方向 (Shift+Enter 换行，Enter 发送)'
                    }
                    disabled={isRunning}
                    className="w-full bg-transparent text-base placeholder:text-muted-foreground focus:outline-none resize-none"
                    rows={1}
                    style={{ maxHeight: '120px' }}
                  />
                </div>

                <div className="flex items-center gap-2">
                  {isRunning && onStop ? (
                    <button
                      onClick={onStop}
                      className="p-2.5 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-all hover:scale-105 active:scale-95"
                      title="中断实验"
                    >
                      <Square className="h-5 w-5" />
                    </button>
                  ) : (
                    <button
                      onClick={handleSubmit}
                      disabled={isRunning}
                      className="p-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95"
                      title="发送 (Enter)"
                    >
                      <Send className="h-5 w-5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
