/** 个股 RSS 资讯 Tab：Huntly 标题关键词检索 + 情绪标签（FinBERT/字典法） */

import { useEffect, useState } from 'react';
import { Rss, ExternalLink, TrendingUp, TrendingDown } from 'lucide-react';
import { message, Spin } from 'antd';
import { stockTerminalService } from '../../services/stockTerminalService';

interface NewsItem {
  id: number;
  title: string;
  link: string | null;
  published_at: string | null;
  source: string;
  sentiment_label?: 'bullish' | 'bearish' | 'neutral' | null;
  sentiment_score?: number | null;
  tickers?: string[];
}

const SENT_TONE: Record<string, string> = {
  bullish: 'bg-rose-50 text-rose-600 border-rose-200',
  bearish: 'bg-emerald-50 text-emerald-600 border-emerald-200',
};

export function NewsTab({ symbol }: { symbol: string }) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    let c = false;
    setLoading(true);
    stockTerminalService.getNews(symbol).then(r => {
      if (!c) setItems(r.items);
    }).catch(() => message.error('资讯加载失败')).finally(() => { if (!c) setLoading(false); });
    return () => { c = true; };
  }, [symbol]);

  return (
    <Spin spinning={loading}>
      <div className="flex flex-col gap-1">
        {!items.length && !loading && (
          <div className="py-8 text-center text-[11px] text-slate-400">暂无可匹配的资讯（标题检索）</div>
        )}
        {items.map(it => (
          <a
            key={it.id}
            href={it.link || undefined}
            target="_blank"
            rel="noreferrer"
            className="flex items-start gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-50 transition-colors group"
          >
            <Rss className="w-3 h-3 text-orange-400 mt-0.5 shrink-0" />
            <span className="flex-1 min-w-0">
              <span className="flex items-center gap-1.5 min-w-0">
                {/* 情绪标签（红=利好 绿=利空） */}
                {it.sentiment_label === 'bullish' && (
                  <span className={`shrink-0 inline-flex items-center gap-0.5 text-[9px] font-bold rounded border px-1 py-0.5 ${SENT_TONE.bullish}`}>
                    <TrendingUp className="w-2.5 h-2.5" /> 利好{it.sentiment_score != null && Math.abs(it.sentiment_score) >= 0.5 ? ` ${it.sentiment_score.toFixed(2)}` : ''}
                  </span>
                )}
                {it.sentiment_label === 'bearish' && (
                  <span className={`shrink-0 inline-flex items-center gap-0.5 text-[9px] font-bold rounded border px-1 py-0.5 ${SENT_TONE.bearish}`}>
                    <TrendingDown className="w-2.5 h-2.5" /> 利空{it.sentiment_score != null && Math.abs(it.sentiment_score) >= 0.5 ? ` ${it.sentiment_score.toFixed(2)}` : ''}
                  </span>
                )}
                <span className="block text-xs text-slate-700 group-hover:text-blue-600 leading-snug line-clamp-2">
                  {it.title}
                </span>
              </span>
              <span className="text-[10px] text-slate-400 mt-0.5 block">
                {it.published_at?.replace('T', ' ') || ''} {it.source ? `· 源 ${it.source}` : ''}
              </span>
            </span>
            <ExternalLink className="w-3 h-3 text-slate-300 group-hover:text-blue-400 shrink-0 mt-1" />
          </a>
        ))}
      </div>
    </Spin>
  );
}
