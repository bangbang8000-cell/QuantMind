/** 个股 RSS 资讯 Tab：Huntly 标题关键词检索 */

import { useEffect, useState } from 'react';
import { Rss, ExternalLink } from 'lucide-react';
import { message, Spin } from 'antd';
import { stockTerminalService } from '../../services/stockTerminalService';

interface NewsItem {
  id: number;
  title: string;
  link: string | null;
  published_at: string | null;
  source: string;
}

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
              <span className="block text-xs text-slate-700 group-hover:text-blue-600 leading-snug line-clamp-2">
                {it.title}
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
