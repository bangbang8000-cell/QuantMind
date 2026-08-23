"""新闻情绪深度研究报告（docs/news_sentiment_deep_report.md）的落地匹配器。

把单条 RSS 新闻对照报告的可落地规律（§3 来源预测力 / §4 时段质量 / §7 事件标签）
打上直观分级标记，让资讯列表一眼可见信号质量。纯展示侧增强，不参与回测。

使用：
    item = annotate_news_item({id, title, source, published_at})  # 返回追加字段
"""
from __future__ import annotations

import logging
import os
import sqlite3
from functools import lru_cache

logger = logging.getLogger("news.report_match")

_HUNTLY_SQLITE_PATH = os.getenv("HUNTLY_SQLITE_PATH", "/data/huntly/db.sqlite")

# ── §3 来源预测力：白名单（预测力 Top，可信） / 黑名单（反向指标，情绪标签不可信）──
GOLD_SOURCE_KEYWORDS = (
    "财联社", "同花顺", "瓦斯", "界面", "东方财富", "东财",
)
REVERSE_SOURCE_KEYWORDS = (
    "南华早报", "创业邦", "彭博", "华尔街见闻", "雅虎", "链捕手",
    "路透", "人民日报", "商业 - 最新新闻",
)

# ── §4.2 时段预测力（按小时，Shanghai 本地时刻）──
def hour_tier_label(hour: int) -> tuple[str, str]:
    """小时 -> (tier, label)。tier: gold/evening/morning/close/early/weak/noise/normal"""
    if hour == 21:
        return "gold", "黄金时段"        # T+5 +1.27% 全时段最优
    if hour in (19, 20):
        return "evening", "晚间复盘"     # +0.36%/+0.74%
    if hour in (10, 11):
        return "morning", "早盘"         # +0.47%/+0.59%
    if 15 <= hour <= 17:
        return "close", "收盘后"         # +0.12%~+0.72%
    if hour == 9:
        return "early", "盘前"           # +0.13% 中性
    if hour in (13, 14):
        return "weak", "午后转弱"        # -0.35% T+5 转弱
    if hour == 0 or (1 <= hour <= 5) or hour == 23:
        return "noise", "噪声时段"       # 凌晨/深夜，无预测力甚至有害
    return "normal", "普通时段"


# ── §7 事件标签预测力（标题关键词）──
# (关键词, 标签, 方向: bullish/bearish/neutral)
EVENT_TAG_RULES = (
    # 利空真实有效
    ("立案", "立案调查", "bearish"),
    ("立案调查", "立案调查", "bearish"),
    ("警示函", "监管", "bearish"),
    ("监管", "监管", "bearish"),
    ("处罚", "监管", "bearish"),
    ("违规", "监管", "bearish"),
    ("退市", "退市风险", "bearish"),
    ("问询函", "监管", "bearish"),
    # 利好有效
    ("业绩预告", "业绩预告", "bullish"),
    ("扭亏为盈", "扭亏为盈", "bullish"),
    ("净利润增长", "业绩", "bullish"),
    ("净利增长", "业绩", "bullish"),
    ("预增", "业绩预告", "bullish"),
    ("预盈", "业绩预告", "bullish"),
    ("业绩快报", "业绩", "bullish"),
    ("涨停", "涨停", "bullish"),
    ("连板", "涨停", "bullish"),
    ("封板", "涨停", "bullish"),
    ("可转债", "可转债", "bullish"),
    ("增持", "增持", "bullish"),
    ("举牌", "增持", "bullish"),
    ("回购", "增持", "bullish"),
    ("战略合作", "战略合作", "bullish"),
    ("合作协议", "战略合作", "bullish"),
    # 中性/噪声
    ("政策", "政策", "neutral"),
    ("降准", "政策", "neutral"),
    ("降息", "政策", "neutral"),
    ("国常会", "政策", "neutral"),
    ("财报", "财报", "neutral"),
    ("一季报", "财报", "neutral"),
    ("半年报", "财报", "neutral"),
    ("中报", "财报", "neutral"),
    ("年报", "财报", "neutral"),
)


def match_event_tags(title: str) -> list[dict]:
    """标题匹配事件标签。返回 [{tag, dir}]，按规则顺序去重（长关键词优先已在规则序）。"""
    if not title:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for kw, tag, d in EVENT_TAG_RULES:
        if kw in title and tag not in seen:
            seen.add(tag)
            out.append({"tag": tag, "dir": d})
    return out


@lru_cache(maxsize=1)
def _load_connector_names() -> dict[str, str]:
    """connector_id(str) -> 可读名（同 Huntly immutable=1 只读）。"""
    try:
        con = sqlite3.connect(f"file:{_HUNTLY_SQLITE_PATH}?immutable=1", uri=True, timeout=3)
        rows = con.execute("SELECT id, name FROM connector").fetchall()
        con.close()
        return {str(r[0]): str(r[1] or "") for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_match: 读取 connector 名失败: %s", exc)
        return {}


def _fmt_hour(published_at: str | None) -> int | None:
    """'YYYY-MM-DD HH:MM:SS'（或含 T）→ 小时；无法解析返回 None。"""
    if not published_at or len(published_at) < 11:
        return None
    try:
        return int(published_at[11:13])
    except (TypeError, ValueError):
        return None


def annotate_news_item(item: dict) -> dict:
    """对一条新闻追加：source_name / source_tier / pub_hour / hour_label / event_tags / note。

    返回新 dict（不就地改 item）。
    """
    out = dict(item)
    src = str(item.get("source") or "")
    tz = src.split(".")[0]  # 兼容 '123' 与 '123.SH'

    names = _load_connector_names()
    source_name = names.get(src) or names.get(tz) or str(src)
    out["source_name"] = source_name

    tier = "neutral"
    if any(k in source_name for k in GOLD_SOURCE_KEYWORDS):
        tier = "gold"
    elif any(k in source_name for k in REVERSE_SOURCE_KEYWORDS):
        tier = "reverse"
    out["source_tier"] = tier
    out["source_tier_label"] = {
        "gold": "高质量源",
        "reverse": "反向源",
        "neutral": "一般来源",
    }[tier]

    hour = _fmt_hour(item.get("published_at"))
    out["pub_hour"] = hour
    if hour is not None:
        h_tier, h_label = hour_tier_label(hour)
        out["hour_tier"] = h_tier
        out["hour_label"] = h_label
    else:
        out["hour_tier"] = None
        out["hour_label"] = None

    out["event_tags"] = match_event_tags(item.get("title") or "")

    # ── 一句话提示：来源 × 时段 × 事件标签 × 情绪 叠加 ──
    note_parts: list[str] = []
    if tier == "gold":
        note_parts.append("优质源可信")
    elif tier == "reverse":
        note_parts.append("反向源·情绪易反指")
    if hour is not None:
        if out["hour_tier"] == "noise":
            note_parts.append("噪声时段")
        elif out["hour_tier"] == "gold":
            note_parts.append("黄金时段")
    bearish_tag = any(t["dir"] == "bearish" for t in out["event_tags"])
    bullish_tag = any(t["dir"] == "bullish" for t in out["event_tags"])
    if bearish_tag:
        note_parts.append("监管/立案·真利空")
    if bullish_tag and not bearish_tag:
        note_parts.append("业绩/事件·真利好")
    out["note"] = (" · ".join(note_parts)) or None
    return out


__all__ = ["annotate_news_item", "match_event_tags", "hour_tier_label"]
