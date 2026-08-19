"""Admin APIs for the versioned, direct-QuantDB training factor catalog."""

from __future__ import annotations

import asyncio
import re
import uuid
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.services.api.user_app.middleware.auth import require_admin
from backend.services.engine.data_platform.quantdb_factor_reader import (
    DEFAULT_FACTOR_SOURCE,
    FACTOR_SOURCE_DIRS,
    KEY_COLUMNS,
    REQUIRED_COLUMNS,
    QuantDBFactorReader,
)
from backend.services.engine.data_platform.quantdb_factor_dictionary import definition_for
from backend.shared.database_manager_v2 import get_session

router = APIRouter(dependencies=[Depends(require_admin)])

_VALID_SOURCE = set(FACTOR_SOURCE_DIRS)
_VALID_STATUS = {"draft", "published", "archived"}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qm_quantdb_factor_field (
    market VARCHAR(16) NOT NULL DEFAULT 'CN',
    dataset_id VARCHAR(64) NOT NULL,
    column_name VARCHAR(128) NOT NULL,
    data_type VARCHAR(64),
    schema_hash VARCHAR(128) NOT NULL DEFAULT '',
    min_date DATE,
    max_date DATE,
    is_present BOOLEAN NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market, dataset_id, column_name)
);
CREATE TABLE IF NOT EXISTS qm_training_factor_catalog_version (
    version_id VARCHAR(64) PRIMARY KEY,
    version_name VARCHAR(128) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    source_dataset VARCHAR(64),
    created_by VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    CHECK (status IN ('draft', 'published', 'archived'))
);
CREATE TABLE IF NOT EXISTS qm_training_factor_mapping (
    mapping_id VARCHAR(64) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES qm_training_factor_catalog_version(version_id) ON DELETE CASCADE,
    source_dataset VARCHAR(64) NOT NULL,
    source_column VARCHAR(128) NOT NULL,
    feature_key VARCHAR(128) NOT NULL,
    display_name VARCHAR(256) NOT NULL,
    category_id VARCHAR(64) NOT NULL,
    category_name VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    default_selected BOOLEAN NOT NULL DEFAULT FALSE,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(version_id, source_dataset, feature_key),
    UNIQUE(version_id, source_dataset, source_column)
);
CREATE INDEX IF NOT EXISTS idx_qm_training_factor_mapping_version
    ON qm_training_factor_mapping(version_id, source_dataset, category_id, sort_order);
CREATE TABLE IF NOT EXISTS qm_quantdb_factor_source_status (
    market VARCHAR(16) NOT NULL DEFAULT 'CN',
    dataset_id VARCHAR(64) NOT NULL,
    files INTEGER NOT NULL DEFAULT 0,
    column_count INTEGER NOT NULL DEFAULT 0,
    schema_hash VARCHAR(128) NOT NULL DEFAULT '',
    min_date DATE,
    max_date DATE,
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    missing_required TEXT NOT NULL DEFAULT '[]',
    reason TEXT,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market, dataset_id)
);
"""


class CatalogVersionCreate(BaseModel):
    version_name: str = Field(min_length=1, max_length=128)
    source_dataset: str = DEFAULT_FACTOR_SOURCE


class CatalogVersionClone(BaseModel):
    version_name: str = Field(min_length=1, max_length=128)


class FactorMappingInput(BaseModel):
    mapping_id: str | None = None
    source_dataset: str
    source_column: str = Field(min_length=1, max_length=128)
    feature_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    category_id: str = Field(min_length=1, max_length=64)
    category_name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    default_selected: bool = False
    required: bool = False
    sort_order: int = 0


class MappingUpdate(BaseModel):
    mapping: FactorMappingInput


def _validate_source(source: str) -> str:
    if source not in _VALID_SOURCE:
        raise HTTPException(status_code=400, detail=f"Unknown factor source: {source}")
    return source


def _category_for(column: str) -> tuple[str, str]:
    prefix = column.split("_", 1)[0].lower()
    categories = {
        "turn": ("turnover", "换手与流动性"), "amt": ("amount", "成交额与资金"),
        "mom": ("momentum", "动量"), "vol": ("volatility", "波动率"),
        "tech": ("technical", "技术指标"), "fun": ("fundamental", "基本面"),
        "chip": ("chip", "筹码"), "style": ("style", "风格"),
        "ind": ("industry", "行业"), "concept": ("concept", "概念"),
        "micro": ("microstructure", "微观结构"), "flow": ("money_flow", "资金流"),
    }
    return categories.get(prefix, ("other", "其他因子"))


def _legacy_catalog_defaults() -> dict[str, dict[str, Any]]:
    """One-time seed aid: retain existing category/default choices if a raw
    QuantDB column has the same logical key.  The database is authoritative
    after the draft is created and published.
    """
    candidates = [
        Path(__file__).resolve().parents[5] / "config" / "features" / "model_training_feature_catalog_v1.json",
        Path.cwd() / "config" / "features" / "model_training_feature_catalog_v1.json",
    ]
    for path in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            defaults: dict[str, dict[str, Any]] = {}
            for category in raw.get("categories") or []:
                for feature in category.get("features") or []:
                    key = str(feature.get("key") or "")
                    if key:
                        defaults[key] = {
                            "category_id": str(category.get("id") or "other"),
                            "category_name": str(category.get("name") or "其他因子"),
                            "display_name": str(feature.get("description") or key),
                            "enabled": bool(feature.get("enabled", True)),
                            "default_selected": bool(feature.get("default_selected", False)),
                            "sort_order": int(feature.get("order_no") or 0),
                        }
            return defaults
        except Exception:
            continue
    return {}


async def _ensure_schema(session) -> None:
    for statement in _SCHEMA_SQL.split(";"):
        if statement.strip():
            await session.execute(text(statement))


async def _active_version(session, source_dataset: str | None = None) -> dict[str, Any] | None:
    source_clause = " AND source_dataset = :source_dataset" if source_dataset else ""
    result = await session.execute(text(
        "SELECT version_id, version_name, status, source_dataset, created_at, published_at "
        "FROM qm_training_factor_catalog_version WHERE status = 'published'"
        f"{source_clause} ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT 1"
    ), {"source_dataset": source_dataset} if source_dataset else {})
    row = result.mappings().first()
    return dict(row) if row else None


def _unrefreshed_source_status(source: str) -> dict[str, Any]:
    """Fast explicit state for a source that has not been scanned yet."""
    return {
        "dataset_id": source,
        "path": str(QuantDBFactorReader().source_path(source)),
        "files": 0,
        "column_count": 0,
        "columns": [],
        "column_types": {},
        "schema_hash": "",
        "min_date": None,
        "max_date": None,
        "ready": False,
        "missing_required": list(REQUIRED_COLUMNS),
        "reason": "字段尚未刷新，请点击“刷新字段”执行 QuantDB 扫描",
        "refreshed_at": None,
    }


async def _cached_factor_sources(session) -> dict[str, dict[str, Any]]:
    """Read readiness from the registry, never by scanning parquet on page load."""
    rows = (await session.execute(text("""
        SELECT dataset_id, files, column_count, schema_hash, min_date, max_date,
               ready, missing_required, reason, refreshed_at
        FROM qm_quantdb_factor_source_status
        WHERE market = 'CN'
    """))).mappings().all()
    cached = {str(row["dataset_id"]): dict(row) for row in rows}
    sources: dict[str, dict[str, Any]] = {}
    reader = QuantDBFactorReader()
    for source in FACTOR_SOURCE_DIRS:
        row = cached.get(source)
        if not row:
            sources[source] = _unrefreshed_source_status(source)
            continue
        try:
            missing_required = json.loads(str(row["missing_required"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            missing_required = list(REQUIRED_COLUMNS)
        sources[source] = {
            "dataset_id": source,
            "path": str(reader.source_path(source)),
            "files": int(row["files"] or 0),
            "column_count": int(row["column_count"] or 0),
            "columns": [],
            "column_types": {},
            "schema_hash": str(row["schema_hash"] or ""),
            "min_date": str(row["min_date"]) if row["min_date"] else None,
            "max_date": str(row["max_date"]) if row["max_date"] else None,
            "ready": bool(row["ready"]),
            "missing_required": missing_required,
            "reason": row["reason"],
            "refreshed_at": str(row["refreshed_at"]) if row["refreshed_at"] else None,
        }
    return sources


async def _store_discovered_sources(
    session, discovered: dict[str, dict[str, Any]]
) -> None:
    for source, status in discovered.items():
        await session.execute(text("""
            INSERT INTO qm_quantdb_factor_source_status
              (market, dataset_id, files, column_count, schema_hash, min_date,
               max_date, ready, missing_required, reason, refreshed_at)
            VALUES ('CN', :dataset_id, :files, :column_count, :schema_hash,
                    :min_date, :max_date, :ready, :missing_required, :reason, NOW())
            ON CONFLICT (market, dataset_id) DO UPDATE SET
              files = EXCLUDED.files, column_count = EXCLUDED.column_count,
              schema_hash = EXCLUDED.schema_hash, min_date = EXCLUDED.min_date,
              max_date = EXCLUDED.max_date, ready = EXCLUDED.ready,
              missing_required = EXCLUDED.missing_required, reason = EXCLUDED.reason,
              refreshed_at = NOW()
        """), {
            "dataset_id": source,
            "files": status["files"],
            "column_count": len(status["columns"]),
            "schema_hash": status["schema_hash"],
            "min_date": date.fromisoformat(status["min_date"]) if status["min_date"] else None,
            "max_date": date.fromisoformat(status["max_date"]) if status["max_date"] else None,
            "ready": status["ready"],
            "missing_required": json.dumps(status["missing_required"]),
            "reason": status["reason"],
        })


async def _catalog_payload(session, version: dict[str, Any], source_dataset: str) -> dict[str, Any]:
    rows = (await session.execute(text("""
        SELECT mapping_id, source_dataset, source_column, feature_key, display_name,
               category_id, category_name, enabled, default_selected, required, sort_order
        FROM qm_training_factor_mapping
        WHERE version_id = :version_id AND source_dataset = :source_dataset
        ORDER BY category_name, sort_order, feature_key
    """), {"version_id": version["version_id"], "source_dataset": source_dataset})).mappings().all()
    categories: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = categories.setdefault(str(row["category_id"]), {
            "id": str(row["category_id"]), "name": str(row["category_name"]),
            "order": len(categories), "feature_count": 0, "features": [],
        })
        category["features"].append({
            "feature_id": str(row["mapping_id"]), "key": str(row["feature_key"]),
            "feature_name": str(row["display_name"]), "source_dataset": str(row["source_dataset"]),
            "source_column": str(row["source_column"]), "enabled": bool(row["enabled"]),
            "default_selected": bool(row["default_selected"]), "required": bool(row["required"]),
            "category_id": str(row["category_id"]), "category_name": str(row["category_name"]),
            "order_no": int(row["sort_order"]),
        })
        category["feature_count"] += 1
    return {
        "version_id": version["version_id"], "version_name": version["version_name"],
        "source_dataset": source_dataset, "status": version["status"],
        "feature_count": sum(c["feature_count"] for c in categories.values()),
        "categories": list(categories.values()), "source": "quantdb_factor_catalog",
    }


async def load_active_factor_catalog(source_dataset: str = DEFAULT_FACTOR_SOURCE) -> dict[str, Any] | None:
    """Public compatibility helper used by the user-facing training catalog API."""
    source_dataset = _validate_source(source_dataset)
    async with get_session() as session:
        await _ensure_schema(session)
        version = await _active_version(session, source_dataset)
        return await _catalog_payload(session, version, source_dataset) if version else None


@router.get("/sources")
async def get_factor_sources(current_user: dict = Depends(require_admin)):
    """Return cached direct-read readiness for the three factor sources."""
    _ = current_user
    async with get_session() as session:
        await _ensure_schema(session)
        sources = await _cached_factor_sources(session)
    return {"sources": sources, "default_source": DEFAULT_FACTOR_SOURCE}


@router.post("/sources/refresh")
async def refresh_factor_sources(current_user: dict = Depends(require_admin)):
    """Scan local QuantDB schemas and upsert the raw field registry."""
    _ = current_user
    discovered = await asyncio.to_thread(QuantDBFactorReader().discover)
    async with get_session() as session:
        await _ensure_schema(session)
        await _store_discovered_sources(session, discovered)
        for source, status in discovered.items():
            await session.execute(text("""
                UPDATE qm_quantdb_factor_field SET is_present = FALSE, discovered_at = NOW()
                WHERE market = 'CN' AND dataset_id = :source
            """), {"source": source})
            for column in status["columns"]:
                await session.execute(text("""
                    INSERT INTO qm_quantdb_factor_field
                      (market, dataset_id, column_name, data_type, schema_hash, min_date, max_date, is_present, discovered_at)
                    VALUES ('CN', :dataset_id, :column_name, :data_type, :schema_hash, :min_date, :max_date, TRUE, NOW())
                    ON CONFLICT (market, dataset_id, column_name) DO UPDATE SET
                      data_type = EXCLUDED.data_type, schema_hash = EXCLUDED.schema_hash, min_date = EXCLUDED.min_date,
                      max_date = EXCLUDED.max_date, is_present = TRUE, discovered_at = NOW()
                """), {
                    "dataset_id": source, "column_name": column, "data_type": status["column_types"].get(column), "schema_hash": status["schema_hash"],
                    "min_date": date.fromisoformat(status["min_date"]) if status["min_date"] else None,
                    "max_date": date.fromisoformat(status["max_date"]) if status["max_date"] else None,
                })
    return {"sources": discovered}


@router.get("/fields")
async def list_factor_fields(
    source_dataset: str = Query(DEFAULT_FACTOR_SOURCE),
    include_keys: bool = Query(False),
    current_user: dict = Depends(require_admin),
):
    _ = current_user
    source_dataset = _validate_source(source_dataset)
    async with get_session() as session:
        await _ensure_schema(session)
        rows = (await session.execute(text("""
            SELECT column_name, data_type, schema_hash, min_date, max_date, is_present, discovered_at
            FROM qm_quantdb_factor_field
            WHERE market = 'CN' AND dataset_id = :source_dataset
            ORDER BY column_name
        """), {"source_dataset": source_dataset})).mappings().all()
    fields = [
        {
            **dict(row),
            "dictionary": definition_for(str(row["column_name"])),
        }
        for row in rows
    ]
    if not include_keys:
        fields = [row for row in fields if row["column_name"] not in KEY_COLUMNS | set(REQUIRED_COLUMNS)]
    return {"source_dataset": source_dataset, "fields": fields}


@router.post("/versions")
async def create_draft_version(payload: CatalogVersionCreate, current_user: dict = Depends(require_admin)):
    """Create an empty draft. Mapping rows are explicitly added by the admin UI."""
    source_dataset = _validate_source(payload.source_dataset)
    version_id = f"qdb-{source_dataset}-{uuid.uuid4().hex[:12]}"
    async with get_session() as session:
        await _ensure_schema(session)
        await session.execute(text("""
            INSERT INTO qm_training_factor_catalog_version
              (version_id, version_name, status, source_dataset, created_by)
            VALUES (:version_id, :version_name, 'draft', :source_dataset, :created_by)
        """), {
            "version_id": version_id, "version_name": payload.version_name,
            "source_dataset": source_dataset,
            "created_by": str(current_user.get("user_id") or current_user.get("sub") or "admin"),
        })
    return {"version_id": version_id, "status": "draft", "source_dataset": source_dataset}


@router.get("/catalog")
async def get_factor_catalog(
    source_dataset: str = Query(DEFAULT_FACTOR_SOURCE),
    version_id: str | None = Query(None),
    current_user: dict = Depends(require_admin),
):
    _ = current_user
    source_dataset = _validate_source(source_dataset)
    async with get_session() as session:
        await _ensure_schema(session)
        if version_id:
            row = (await session.execute(text("""
                SELECT version_id, version_name, status, source_dataset, created_at, published_at
                FROM qm_training_factor_catalog_version WHERE version_id = :version_id
            """), {"version_id": version_id})).mappings().first()
            version = dict(row) if row else None
        else:
            version = await _active_version(session, source_dataset)
        # 没有活动发布版本是管理员首次配置时的正常状态，而不是资源路由
        # 不存在或权限异常。返回 200 可以让前端安静地显示“未发布”，避免被
        # 全局鉴权拦截器误报为 Auth Error。
        if not version and not version_id:
            return {
                "catalog": None,
                "source_dataset": source_dataset,
                "message": "No published factor catalog for this source",
            }
        if not version:
            raise HTTPException(status_code=404, detail="Catalog version not found")
        if version["source_dataset"] != source_dataset:
            raise HTTPException(status_code=400, detail="Catalog version belongs to a different factor source")
        return await _catalog_payload(session, version, source_dataset)


@router.put("/versions/{version_id}/mappings")
async def upsert_factor_mapping(version_id: str, payload: MappingUpdate, current_user: dict = Depends(require_admin)):
    _ = current_user
    mapping = payload.mapping
    source_dataset = _validate_source(mapping.source_dataset)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mapping.source_column):
        raise HTTPException(status_code=400, detail="Invalid source_column")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mapping.feature_key):
        raise HTTPException(status_code=400, detail="Invalid feature_key")
    if mapping.feature_key in set(REQUIRED_COLUMNS) | {"trade_date", "symbol"}:
        raise HTTPException(status_code=400, detail="feature_key cannot overwrite key or OHLCV columns")
    async with get_session() as session:
        await _ensure_schema(session)
        version = (await session.execute(text("""
            SELECT status, source_dataset FROM qm_training_factor_catalog_version WHERE version_id = :version_id
        """), {"version_id": version_id})).mappings().first()
        if not version:
            raise HTTPException(status_code=404, detail="Catalog version not found")
        if version["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only draft catalogs can be edited")
        if version["source_dataset"] != source_dataset:
            raise HTTPException(status_code=400, detail="Mapping source must match draft source")
        field = (await session.execute(text("""
            SELECT 1 FROM qm_quantdb_factor_field
            WHERE market = 'CN' AND dataset_id = :dataset_id AND column_name = :column_name AND is_present
        """), {"dataset_id": source_dataset, "column_name": mapping.source_column})).first()
        if not field:
            raise HTTPException(status_code=400, detail="Source field is not present in the discovered QuantDB schema")
        mapping_id = mapping.mapping_id or uuid.uuid4().hex
        await session.execute(text("""
            INSERT INTO qm_training_factor_mapping
             (mapping_id, version_id, source_dataset, source_column, feature_key, display_name,
              category_id, category_name, enabled, default_selected, required, sort_order)
            VALUES (:mapping_id, :version_id, :source_dataset, :source_column, :feature_key, :display_name,
                    :category_id, :category_name, :enabled, :default_selected, :required, :sort_order)
            ON CONFLICT (mapping_id) DO UPDATE SET
              source_column = EXCLUDED.source_column, feature_key = EXCLUDED.feature_key,
              display_name = EXCLUDED.display_name, category_id = EXCLUDED.category_id,
              category_name = EXCLUDED.category_name, enabled = EXCLUDED.enabled,
              default_selected = EXCLUDED.default_selected, required = EXCLUDED.required,
              sort_order = EXCLUDED.sort_order
        """), {
            "mapping_id": mapping_id,
            "version_id": version_id,
            **mapping.model_dump(exclude={"mapping_id"}),
        })
    return {"mapping_id": mapping_id, "version_id": version_id}


@router.post("/versions/{version_id}/publish")
async def publish_factor_catalog(version_id: str, current_user: dict = Depends(require_admin)):
    _ = current_user
    async with get_session() as session:
        await _ensure_schema(session)
        version = (await session.execute(text("""
            SELECT version_id, source_dataset, status FROM qm_training_factor_catalog_version
            WHERE version_id = :version_id
        """), {"version_id": version_id})).mappings().first()
        if not version:
            raise HTTPException(status_code=404, detail="Catalog version not found")
        if version["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only draft catalogs can be published")
        count = (await session.execute(text("""
            SELECT count(*) FROM qm_training_factor_mapping
            WHERE version_id = :version_id AND enabled
        """), {"version_id": version_id})).scalar_one()
        if not count:
            raise HTTPException(status_code=400, detail="A published catalog needs at least one enabled factor")
        await session.execute(text("""
            UPDATE qm_training_factor_catalog_version SET status = 'archived'
            WHERE source_dataset = :source_dataset AND status = 'published'
        """), {"source_dataset": version["source_dataset"]})
        await session.execute(text("""
            UPDATE qm_training_factor_catalog_version
            SET status = 'published', published_at = :published_at WHERE version_id = :version_id
        """), {"version_id": version_id, "published_at": datetime.now(timezone.utc)})
    return {"version_id": version_id, "status": "published"}


@router.post("/versions/{version_id}/clone")
async def clone_factor_catalog(version_id: str, payload: CatalogVersionClone, current_user: dict = Depends(require_admin)):
    """Copy an immutable published version into an independently editable draft."""
    _ = current_user
    async with get_session() as session:
        await _ensure_schema(session)
        source = (await session.execute(text("""
            SELECT source_dataset FROM qm_training_factor_catalog_version WHERE version_id = :version_id
        """), {"version_id": version_id})).scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="Catalog version not found")
        clone_id = f"qdb-{source}-{uuid.uuid4().hex[:12]}"
        await session.execute(text("""
            INSERT INTO qm_training_factor_catalog_version
              (version_id, version_name, status, source_dataset, created_by)
            VALUES (:clone_id, :version_name, 'draft', :source_dataset, :created_by)
        """), {
            "clone_id": clone_id, "version_name": payload.version_name, "source_dataset": source,
            "created_by": str(current_user.get("user_id") or current_user.get("sub") or "admin"),
        })
        await session.execute(text("""
            INSERT INTO qm_training_factor_mapping
              (mapping_id, version_id, source_dataset, source_column, feature_key, display_name,
               category_id, category_name, enabled, default_selected, required, sort_order)
            SELECT :prefix || mapping_id, :clone_id, source_dataset, source_column, feature_key, display_name,
                   category_id, category_name, enabled, default_selected, required, sort_order
            FROM qm_training_factor_mapping WHERE version_id = :version_id
        """), {"prefix": f"{uuid.uuid4().hex[:8]}-", "clone_id": clone_id, "version_id": version_id})
    return {"version_id": clone_id, "source_dataset": source, "status": "draft"}


@router.post("/versions/{version_id}/seed")
async def seed_draft_mappings(version_id: str, current_user: dict = Depends(require_admin)):
    """Convenience endpoint: add all discovered factor columns to a draft as disabled mappings."""
    _ = current_user
    async with get_session() as session:
        await _ensure_schema(session)
        version = (await session.execute(text("""
            SELECT status, source_dataset FROM qm_training_factor_catalog_version WHERE version_id = :version_id
        """), {"version_id": version_id})).mappings().first()
        if not version:
            raise HTTPException(status_code=404, detail="Catalog version not found")
        if version["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only draft catalogs can be seeded")
        fields = (await session.execute(text("""
            SELECT column_name FROM qm_quantdb_factor_field
            WHERE market = 'CN' AND dataset_id = :dataset_id AND is_present
            ORDER BY column_name
        """), {"dataset_id": version["source_dataset"]})).scalars().all()
        legacy_defaults = _legacy_catalog_defaults()
        count = 0
        for column in fields:
            if column in KEY_COLUMNS or column in REQUIRED_COLUMNS:
                continue
            definition = definition_for(str(column))
            cat_id = str(definition["category_id"])
            cat_name = str(definition["category_name"])
            inherited = legacy_defaults.get(str(column), {})
            await session.execute(text("""
                INSERT INTO qm_training_factor_mapping
                 (mapping_id, version_id, source_dataset, source_column, feature_key, display_name,
                  category_id, category_name, enabled, default_selected, required, sort_order)
                VALUES (:mapping_id, :version_id, :source_dataset, :source_column, :feature_key, :display_name,
                        :category_id, :category_name, :enabled, :default_selected, FALSE, :sort_order)
                ON CONFLICT (version_id, source_dataset, source_column) DO NOTHING
            """), {
                "mapping_id": uuid.uuid4().hex, "version_id": version_id,
                "source_dataset": version["source_dataset"], "source_column": column,
                "feature_key": column,
                "category_name": cat_name,
                "category_id": cat_id,
                "display_name": str(definition["explanation"]),
                "enabled": bool(inherited.get("enabled", False)),
                "default_selected": bool(inherited.get("default_selected", False)),
                "sort_order": int(definition["sort_order"]) + count,
            })
            count += 1
    return {"version_id": version_id, "seeded_fields": count}
