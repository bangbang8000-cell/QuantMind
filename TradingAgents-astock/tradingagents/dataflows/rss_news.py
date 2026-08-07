"""RSS-based news search via RSSHub for TradingAgents.

Fetches financial RSS feeds from multiple sources and filters items by
keywords related to the stock being analyzed.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_RSSHUB_BASE = "http://quantmind-rsshub:1200"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Financial RSS sources with stable routes
RSS_SOURCES = [
    # 华尔街见闻 - 最新资讯
    {"name": "华尔街见闻", "url": "/wallstreetcn/news/global", "lang": "zh"},
    # 华尔街见闻 - 快讯
    {"name": "华尔街快讯", "url": "/wallstreetcn/news/quick", "lang": "zh"},
    # 东方财富 - 策略报告
    {"name": "东方财富策略", "url": "/eastmoney/report/strategyreport", "lang": "zh"},
    # 36氪 - 快讯
    {"name": "36氪快讯", "url": "/36kr/newsflashes", "lang": "zh"},
    # 财新 - 最新
    {"name": "财新网", "url": "/caixin/latest", "lang": "zh"},
    # 第一财经 - 简报
    {"name": "第一财经", "url": "/yicai/brief", "lang": "zh"},
]


def _fetch_rss(url: str, timeout: int = 10) -> list[dict]:
    """Fetch and parse an RSS feed, return list of {title, link, pubDate, description}."""
    try:
        req = Request(url, headers={"User-Agent": _UA})
        resp = urlopen(req, timeout=timeout)
        xml_data = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(xml_data)
        items = []
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            desc = item.findtext("description", "").strip()
            # Strip HTML tags from description
            desc_clean = re.sub(r"<[^>]+>", "", desc)[:500]
            items.append({
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "description": desc_clean,
            })
        return items
    except Exception as e:
        logger.debug("RSS fetch failed for %s: %s", url, e)
        return []


def _extract_keywords(ticker: str, company_name: str = "") -> list[str]:
    """Extract search keywords from ticker and company name.

    For a stock like 宁德时代 (300750), returns keywords like:
    ['宁德时代', '电池', '锂电', 'CATL']
    """
    keywords = []

    if company_name:
        keywords.append(company_name)
        # Add common industry keywords based on company name
        industry_map = {
            "宁德时代": ["电池", "锂电", "新能源", "储能", "CATL"],
            "比亚迪": ["新能源车", "电池", "电动车", "BYD"],
            "茅台": ["白酒", "酱酒", "消费"],
            "隆基绿能": ["光伏", "硅片", "太阳能"],
            "中芯国际": ["芯片", "半导体", "晶圆"],
            "腾讯": ["游戏", "社交", "微信"],
            "阿里巴巴": ["电商", "云计算", "淘宝"],
            "华为": ["5G", "通信", "鸿蒙"],
            "小米": ["手机", "IoT", "智能家居"],
            "药明康德": ["医药", "CRO", "新药"],
            "迈瑞医疗": ["医疗器械", "监护", "超声"],
            "恒瑞医药": ["创新药", "仿制药", "抗肿瘤"],
            "通威股份": ["光伏", "硅料", "电池片"],
            "中国平安": ["保险", "金融", "平安银行"],
            "招商银行": ["银行", "零售银行", "财富管理"],
            "海天味业": ["调味品", "酱油", "消费"],
            "伊利股份": ["乳业", "牛奶", "消费"],
            "牧原股份": ["养猪", "生猪", "畜牧"],
            "长城汽车": ["SUV", "新能源车", "皮卡"],
            "中远海控": ["航运", "集装箱", "海运"],
            "中国中免": ["免税", "旅游", "消费"],
        }
        for name, kws in industry_map.items():
            if name in company_name:
                keywords.extend(kws)
                break

    keywords.append(ticker)
    return list(set(keywords))


def _matches_keywords(item: dict, keywords: list[str]) -> bool:
    """Check if an RSS item matches any keyword."""
    text = f"{item['title']} {item['description']}".lower()
    return any(kw.lower() in text for kw in keywords)


def search_rss_news(
    ticker: str,
    company_name: str = "",
    max_items: int = 20,
) -> str:
    """Search RSS feeds for news related to a stock.

    Args:
        ticker: 6-digit A-stock code (e.g. '300750')
        company_name: Chinese company name (e.g. '宁德时代')
        max_items: Maximum number of items to return

    Returns:
        Formatted string with matching RSS news items
    """
    keywords = _extract_keywords(ticker, company_name)
    if not keywords:
        return f"No keywords to search for ticker {ticker}"

    all_matches = []
    for source in RSS_SOURCES:
        url = f"{_RSSHUB_BASE}{source['url']}"
        items = _fetch_rss(url)
        for item in items:
            if _matches_keywords(item, keywords):
                all_matches.append({
                    **item,
                    "source": source["name"],
                })

    # Deduplicate by title
    seen = set()
    unique = []
    for item in all_matches:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    # Limit results
    unique = unique[:max_items]

    if not unique:
        return f"RSS feeds: no news found for {company_name or ticker}"

    # Format output
    lines = [f"## RSS News for {company_name or ticker} ({ticker})", ""]
    for i, item in enumerate(unique, 1):
        lines.append(f"### {i}. [{item['source']}] {item['title']}")
        if item["description"]:
            lines.append(item["description"][:300])
        if item["pubDate"]:
            lines.append(f"Date: {item['pubDate']}")
        lines.append("")

    return "\n".join(lines)
