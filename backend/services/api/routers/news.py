"""Huntly 资讯聚合代理 — /api/v1/news/*

后端代理 lcomplete/huntly:latest 的 REST API：
- 首次启动自动注册管理员账号 (POST /api/auth/signup)
- 已存在则登录 (POST /api/auth/signin) 拿 JSESSIONID
- 把 Huntly 的 Folder / Connector / Page 模型转译成 QuantMind 风格 JSON
- 前端无须知道 Huntly 存在，零 401 风险

环境变量：
- HUNTLY_BASE_URL    默认 http://quantmind-huntly
- HUNTLY_USERNAME    默认 admin
- HUNTLY_PASSWORD    默认 quantmind2026
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/news", tags=["News"])

HUNTLY_BASE_URL = os.getenv("HUNTLY_BASE_URL", "http://quantmind-huntly").rstrip("/")
HUNTLY_USERNAME = os.getenv("HUNTLY_USERNAME", "admin")
HUNTLY_PASSWORD = os.getenv("HUNTLY_PASSWORD", "quantmind2026")
HUNTLY_TIMEOUT = float(os.getenv("HUNTLY_TIMEOUT_SECONDS", "20"))

# 财经事件关键词 (用于把普通文章打上 "financial_event" 标记)
_FINANCIAL_EVENT_KEYWORDS = (
    "减持", "增持", "回购", "公告", "业绩快报", "业绩预告", "重大事项",
    "股权激励", "分红", "送转", "停牌", "复牌", "ST", "退市",
    "IPO", "并购", "重组", "定增", "可转债", "中标",
)

# Huntly 鉴权：JWT (auth_token cookie + Bearer header 都能用)
# /api/auth/signin 返回 {"code":0, "data":"<jwt>"}, 同时 Set-Cookie: auth_token=<jwt>
_SESSION_LOCK = asyncio.Lock()
_SESSION_TOKEN: str | None = None
_SESSION_EXPIRES_AT: float = 0.0
_SESSION_TTL = 30 * 60  # 30 分钟内复用


async def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=HUNTLY_BASE_URL, timeout=HUNTLY_TIMEOUT)


def _unwrap(body: Any) -> Any:
    """Huntly 统一返回 {code, message, data} 包装；抽出 data。"""
    if isinstance(body, dict) and "data" in body and "code" in body:
        return body.get("data")
    return body


async def _ensure_session() -> str:
    """获取有效 JWT；若 Huntly 未设置用户则自动 signup 再 signin。"""
    global _SESSION_TOKEN, _SESSION_EXPIRES_AT

    if _SESSION_TOKEN and time.time() < _SESSION_EXPIRES_AT:
        return _SESSION_TOKEN

    async with _SESSION_LOCK:
        if _SESSION_TOKEN and time.time() < _SESSION_EXPIRES_AT:
            return _SESSION_TOKEN

        async with await _http() as client:
            # 1. 探测是否已设置用户 — Huntly 返回 {"code":0, "data": <bool>}
            user_set = False
            try:
                r = await client.get("/api/auth/isUserSet")
                if r.status_code == 200:
                    user_set = bool(_unwrap(r.json()))
            except Exception as exc:
                logger.warning("huntly isUserSet probe failed: %s", exc)

            # 2. 未设置则注册（已存在会返回 BusinessException 5101，忽略即可）
            if not user_set:
                try:
                    r = await client.post(
                        "/api/auth/signup",
                        json={"username": HUNTLY_USERNAME, "password": HUNTLY_PASSWORD},
                    )
                    logger.info(
                        "huntly signup status=%s body=%s",
                        r.status_code, r.text[:200],
                    )
                except Exception as exc:
                    logger.warning("huntly signup failed: %s", exc)

            # 3. 登录拿 JWT
            r = await client.post(
                "/api/auth/signin",
                json={"username": HUNTLY_USERNAME, "password": HUNTLY_PASSWORD},
            )
            if r.status_code >= 300:
                raise HTTPException(
                    status_code=502,
                    detail=f"Huntly signin failed: HTTP {r.status_code} {r.text[:200]}",
                )

            token = _unwrap(r.json()) if r.headers.get("content-type", "").startswith("application/json") else None
            if not token:
                # 回退到 Set-Cookie: auth_token=...
                token = r.cookies.get("auth_token")
            if not token:
                set_cookie = r.headers.get("set-cookie", "")
                if "auth_token=" in set_cookie:
                    token = set_cookie.split("auth_token=", 1)[1].split(";", 1)[0]

            if not token or not isinstance(token, str):
                raise HTTPException(
                    status_code=502,
                    detail="Huntly signin succeeded but no JWT returned",
                )

            _SESSION_TOKEN = token
            _SESSION_EXPIRES_AT = time.time() + _SESSION_TTL
            logger.info("huntly session established (jwt len=%d)", len(token))
            return token


async def _huntly_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: Any = None,
    retry_on_401: bool = True,
) -> httpx.Response:
    """带 JWT 的 Huntly 调用，401 自动重登一次。"""
    token = await _ensure_session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Cookie": f"auth_token={token}",
    }
    async with await _http() as client:
        r = await client.request(method, path, params=params, json=json, headers=headers)
        if r.status_code in (401, 403) and retry_on_401:
            global _SESSION_TOKEN, _SESSION_EXPIRES_AT
            _SESSION_TOKEN = None
            _SESSION_EXPIRES_AT = 0
            return await _huntly_request(
                method, path, params=params, json=json, retry_on_401=False
            )
        return r


def _is_financial_event(title: str | None, summary: str | None) -> bool:
    haystack = (title or "") + " " + (summary or "")
    return any(kw in haystack for kw in _FINANCIAL_EVENT_KEYWORDS)


def _normalize_page(page: dict) -> dict:
    """把 Huntly Page 转成 QuantMind News Article 标准结构。"""
    title = page.get("title") or page.get("siteName") or "(无标题)"
    summary = page.get("description") or page.get("content")
    if summary and len(summary) > 280:
        summary = summary[:280] + "..."

    # Huntly 的字段：connectedAt > recordAt > pubDate > createdAt
    published_at = (
        page.get("connectedAt")
        or page.get("recordAt")
        or page.get("pubDate")
        or page.get("createdAt")
    )

    return {
        "id": page.get("id"),
        "title": title,
        "summary": summary,
        "url": page.get("url"),
        "source_id": page.get("connectorId") or page.get("sourceId"),
        "source_name": page.get("siteName") or page.get("domain"),
        "folder_id": page.get("folderId"),
        "published_at": published_at,
        "read": bool(page.get("markRead")),
        "starred": bool(page.get("starred")),
        "is_financial_event": _is_financial_event(title, summary),
        "thumbnail": page.get("thumbUrl") or page.get("faviconUrl"),
    }


# ---------------------------------------------------------------------------
# 公开路由
# ---------------------------------------------------------------------------


@router.get("/health")
async def news_health():
    """检查 Huntly 上游连通性 (无须登录)"""
    try:
        async with await _http() as client:
            r = await client.get("/api/health")
        return {
            "huntly_status": "up" if r.status_code == 200 else "down",
            "huntly_http_code": r.status_code,
            "huntly_base_url": HUNTLY_BASE_URL,
        }
    except Exception as exc:
        return {
            "huntly_status": "unreachable",
            "huntly_base_url": HUNTLY_BASE_URL,
            "error": str(exc),
        }


@router.get("/sources")
async def list_sources():
    """列出所有订阅源 (Huntly Folder + Connector)

    Huntly 真实端点是 GET /api/connector/folder-connectors，
    返回 {folderFeedConnectors: [{id, name, connectorItems: [...]}, ...]}
    folder.id=null 表示 "未分组"。
    """
    r = await _huntly_request("GET", "/api/connector/folder-connectors")
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Huntly /connector/folder-connectors HTTP {r.status_code}",
        )

    body = _unwrap(r.json()) or {}
    folders_raw = body.get("folderFeedConnectors") if isinstance(body, dict) else body
    folders_raw = folders_raw or []

    sources: list[dict] = []
    folders_summary: list[dict] = []

    for folder in folders_raw:
        folder_id = folder.get("id")
        folder_name = folder.get("name") or "未分组"
        items = folder.get("connectorItems") or []
        folders_summary.append({
            "folder_id": folder_id if folder_id is not None else 0,
            "folder_name": folder_name,
            "source_count": len(items),
            "unread_count": sum(int(it.get("inboxCount") or 0) for it in items),
        })
        for conn in items:
            sources.append({
                "source_id": conn.get("id"),
                "source_name": conn.get("name") or "(未命名)",
                "subscribe_url": conn.get("subscribeUrl"),
                "type": conn.get("type"),
                "folder_id": folder_id if folder_id is not None else 0,
                "folder_name": folder_name,
                "site_avatar_url": conn.get("iconUrl"),
                "unread_count": int(conn.get("inboxCount") or 0),
            })

    return {
        "sources": sources,
        "folders": folders_summary,
        "total": len(sources),
    }


@router.post("/sources/{source_id}/refresh")
async def refresh_source(source_id: int):
    """手动触发抓取（Huntly 上游 v0.5.x 未公开 fetchNow 端点，这里仅作占位返回 202）"""
    return {
        "ok": False,
        "source_id": source_id,
        "message": "当前 Huntly 版本未暴露手动抓取接口，请等待下一次定时抓取（每 1 小时）",
    }


@router.get("/articles")
async def list_articles(
    source_id: int | None = Query(None, description="按 connector(source) 过滤"),
    folder_id: int | None = Query(None, description="按 folder 过滤"),
    keyword: str | None = Query(None, description="标题关键词"),
    only_financial_event: bool = Query(False, description="仅返回财务事件"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
):
    """资讯文章列表 (代理 Huntly /api/page/list)

    Huntly 端是 GET，返回纯数组（按 connectedAt desc）。
    """
    # Huntly v0.6.x 真实参数：count(总数) / sort(枚举) / isAsc / connectorId / folderId
    params: dict = {
        "count": page_size,
        "sort": "CONNECTED_AT",
        "isAsc": "false",
    }
    if source_id is not None:
        params["connectorId"] = source_id
    if folder_id is not None and folder_id > 0:
        params["folderId"] = folder_id
    if keyword:
        params["q"] = keyword

    r = await _huntly_request("GET", "/api/page/list", params=params)
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Huntly /page/list HTTP {r.status_code}: {r.text[:200]}",
        )

    body = _unwrap(r.json())
    if isinstance(body, list):
        raw_pages = body
        total_hint = len(raw_pages)
    elif isinstance(body, dict):
        raw_pages = body.get("items") or body.get("content") or body.get("data") or []
        total_hint = body.get("total") or body.get("totalElements") or len(raw_pages)
    else:
        raw_pages, total_hint = [], 0

    articles = [_normalize_page(p) for p in raw_pages]
    if only_financial_event:
        articles = [a for a in articles if a["is_financial_event"]]

    # 计算最新一条同步时间，前端用于显示 "最新资讯 X 秒前"
    latest_at = None
    for a in articles:
        if a.get("published_at"):
            latest_at = a["published_at"]
            break

    return {
        "articles": articles,
        "page": page,
        "page_size": page_size,
        "total": total_hint,
        "latest_published_at": latest_at,
        "server_time": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }


@router.get("/articles/{article_id}")
async def get_article(article_id: int):
    """获取单篇正文 (代理 Huntly /api/page/{id})"""
    r = await _huntly_request("GET", f"/api/page/{article_id}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Huntly /page/{article_id} HTTP {r.status_code}")
    page = _unwrap(r.json()) or {}
    # Huntly /api/page/{id} 实际返回 {"page": {...}, "contents": [...]}
    if isinstance(page, dict) and "page" in page and isinstance(page["page"], dict):
        contents = page.get("contents") or []
        page_obj = page["page"]
        detail = _normalize_page(page_obj)
        # 优先取 contents[0].content，回退到 page.content
        if contents and isinstance(contents[0], dict):
            detail["content"] = contents[0].get("content") or page_obj.get("content") or ""
        else:
            detail["content"] = page_obj.get("content") or ""
        detail["content_html"] = page_obj.get("contentHtml") or detail["content"]
        return detail
    detail = _normalize_page(page)
    detail["content"] = page.get("content") or ""
    detail["content_html"] = page.get("contentHtml") or ""
    return detail


@router.post("/articles/{article_id}/star")
async def star_article(article_id: int, starred: bool = True):
    """收藏 / 取消收藏"""
    path = f"/api/page/{'star' if starred else 'unStar'}/{article_id}"
    r = await _huntly_request("POST", path)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Huntly star HTTP {r.status_code}")
    return {"ok": True, "starred": starred}


@router.post("/articles/{article_id}/read")
async def mark_read(article_id: int, read: bool = True):
    """标记已读 / 未读"""
    path = f"/api/page/{'markRead' if read else 'unMarkRead'}/{article_id}"
    r = await _huntly_request("POST", path)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Huntly markRead HTTP {r.status_code}")
    return {"ok": True, "read": read}


@router.get("/events")
async def list_financial_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
):
    """财务事件流 (=资讯流中含财务关键词的子集，方便量化业务消费)"""
    return await list_articles(
        source_id=None,
        folder_id=None,
        keyword=None,
        only_financial_event=True,
        page=page,
        page_size=page_size,
    )
