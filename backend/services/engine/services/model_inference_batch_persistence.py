from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

_JSON_FIELDS = ("member_runs", "params", "agg_json")


class ModelInferenceBatchPersistence:
    """批量多日推理批次的持久化与进度追踪。

    进度落 DB 行而非进程内 dict，因此服务重启后前端仍能读到批次状态。
    """

    async def ensure_tables(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS qm_model_inference_batches (
              batch_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL DEFAULT 'default',
              user_id TEXT NOT NULL,
              model_id TEXT NOT NULL,
              anchor_date DATE NOT NULL,
              window_days INTEGER NOT NULL,
              horizon_days INTEGER NOT NULL,
              member_runs JSONB,
              status TEXT NOT NULL,
              progress_done INTEGER NOT NULL DEFAULT 0,
              progress_total INTEGER NOT NULL DEFAULT 0,
              current_trade_date TEXT,
              params JSONB,
              agg_json JSONB,
              error_message TEXT,
              created_at TIMESTAMPTZ NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_qm_mib_owner_created
              ON qm_model_inference_batches (tenant_id, user_id, created_at DESC);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_qm_mib_owner_model_anchor
              ON qm_model_inference_batches
                 (tenant_id, user_id, model_id, anchor_date DESC);
            """,
        ]
        async with get_session() as session:
            for stmt in statements:
                await session.execute(text(stmt))

    @staticmethod
    def _parse_json_field(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    @classmethod
    def _row_to_batch(cls, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        for key in _JSON_FIELDS:
            if key in item:
                item[key] = cls._parse_json_field(item.get(key))
        for key in ("anchor_date", "created_at", "updated_at"):
            value = item.get(key)
            if value is not None and hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        if not isinstance(item.get("member_runs"), list):
            item["member_runs"] = []
        return item

    async def create_batch(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        user_id: str,
        model_id: str,
        anchor_date: date,
        window_days: int,
        horizon_days: int,
        trade_dates: list[str],
        params: dict[str, Any],
        created_at: datetime | None = None,
    ) -> None:
        now = created_at or datetime.now(_SHANGHAI_TZ)
        member_runs = [
            {
                "trade_date": d,
                "run_id": None,
                "status": "pending",
                "reused": False,
                "signals_count": 0,
            }
            for d in trade_dates
        ]
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO qm_model_inference_batches (
                      batch_id, tenant_id, user_id, model_id, anchor_date,
                      window_days, horizon_days, member_runs, status,
                      progress_done, progress_total, current_trade_date,
                      params, agg_json, error_message, created_at, updated_at
                    ) VALUES (
                      :batch_id, :tenant_id, :user_id, :model_id, :anchor_date,
                      :window_days, :horizon_days, CAST(:member_runs AS JSONB),
                      'pending', 0, :progress_total, NULL,
                      CAST(:params AS JSONB), NULL, NULL, :created_at, :created_at
                    )
                    ON CONFLICT (batch_id) DO UPDATE SET
                      member_runs = EXCLUDED.member_runs,
                      status = EXCLUDED.status,
                      progress_done = 0,
                      progress_total = EXCLUDED.progress_total,
                      current_trade_date = NULL,
                      params = EXCLUDED.params,
                      agg_json = NULL,
                      error_message = NULL,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "batch_id": batch_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "model_id": model_id,
                    "anchor_date": anchor_date,
                    "window_days": int(window_days),
                    "horizon_days": int(horizon_days),
                    "member_runs": json.dumps(member_runs, ensure_ascii=False),
                    "progress_total": len(trade_dates),
                    "params": json.dumps(params, ensure_ascii=False),
                    "created_at": now,
                },
            )

    async def update_progress(
        self,
        *,
        batch_id: str,
        member_runs: list[dict[str, Any]],
        progress_done: int,
        current_trade_date: str | None,
        status: str = "running",
    ) -> None:
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    UPDATE qm_model_inference_batches
                    SET member_runs = CAST(:member_runs AS JSONB),
                        progress_done = :progress_done,
                        current_trade_date = :current_trade_date,
                        status = :status,
                        updated_at = :updated_at
                    WHERE batch_id = :batch_id
                    """
                ),
                {
                    "batch_id": batch_id,
                    "member_runs": json.dumps(member_runs, ensure_ascii=False),
                    "progress_done": int(progress_done),
                    "current_trade_date": current_trade_date,
                    "status": status,
                    "updated_at": datetime.now(_SHANGHAI_TZ),
                },
            )

    async def finalize_batch(
        self,
        *,
        batch_id: str,
        status: str,
        member_runs: list[dict[str, Any]],
        progress_done: int,
        error_message: str | None = None,
        agg_payload: dict[str, Any] | None = None,
    ) -> None:
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    UPDATE qm_model_inference_batches
                    SET status = :status,
                        member_runs = CAST(:member_runs AS JSONB),
                        progress_done = :progress_done,
                        current_trade_date = NULL,
                        error_message = :error_message,
                        agg_json = CAST(:agg_json AS JSONB),
                        updated_at = :updated_at
                    WHERE batch_id = :batch_id
                    """
                ),
                {
                    "batch_id": batch_id,
                    "status": status,
                    "member_runs": json.dumps(member_runs, ensure_ascii=False),
                    "progress_done": int(progress_done),
                    "error_message": error_message,
                    "agg_json": (
                        json.dumps(agg_payload, ensure_ascii=False)
                        if agg_payload is not None
                        else None
                    ),
                    "updated_at": datetime.now(_SHANGHAI_TZ),
                },
            )

    async def save_aggregate(
        self,
        *,
        batch_id: str,
        agg_payload: dict[str, Any],
    ) -> None:
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    UPDATE qm_model_inference_batches
                    SET agg_json = CAST(:agg_json AS JSONB),
                        updated_at = :updated_at
                    WHERE batch_id = :batch_id
                    """
                ),
                {
                    "batch_id": batch_id,
                    "agg_json": json.dumps(agg_payload, ensure_ascii=False),
                    "updated_at": datetime.now(_SHANGHAI_TZ),
                },
            )

    async def get_batch(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        async with get_session(read_only=True) as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT *
                            FROM qm_model_inference_batches
                            WHERE batch_id = :batch_id
                              AND tenant_id = :tenant_id
                              AND user_id = :user_id
                            LIMIT 1
                            """
                        ),
                        {
                            "batch_id": batch_id,
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        return self._row_to_batch(dict(row))

    async def list_batches(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        filters = ["tenant_id = :tenant_id", "user_id = :user_id"]
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "limit": int(page_size),
            "offset": max(page - 1, 0) * int(page_size),
        }
        if model_id:
            filters.append("model_id = :model_id")
            params["model_id"] = model_id
        if status:
            filters.append("status = :status")
            params["status"] = status
        where_sql = " AND ".join(filters)

        async with get_session(read_only=True) as session:
            total_row = (
                (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) AS total "
                            "FROM qm_model_inference_batches "
                            f"WHERE {where_sql}"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            total = int((total_row or {}).get("total") or 0)
            rows = (
                (
                    await session.execute(
                        text(
                            f"""
                            SELECT batch_id, tenant_id, user_id, model_id,
                                   anchor_date, window_days, horizon_days,
                                   member_runs, status, progress_done,
                                   progress_total, current_trade_date, params,
                                   error_message, created_at, updated_at
                            FROM qm_model_inference_batches
                            WHERE {where_sql}
                            ORDER BY created_at DESC
                            LIMIT :limit OFFSET :offset
                            """
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            )

        items = [self._row_to_batch(dict(row)) for row in rows]
        return {"page": page, "page_size": page_size, "total": total, "items": items}

    async def find_reusable_run(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_id: str,
        trade_date: date,
    ) -> dict[str, Any] | None:
        """查找该模型在该交易日仍有信号行可读的 run，供幂等复用。

        必须用 EXISTS 实测 engine_signal_scores 行数，不能信 signals_count：
        script_runner 的「当日覆盖」策略按 (trade_date, tenant, user,
        feature_version) 删除旧行，同日重跑会清空先前 run 的信号，但那些 run 的
        signals_count 仍留在 qm_model_inference_runs 里。实测库中已有
        status=completed & signals_count=5524 却零信号行的记录。
        """
        async with get_session(read_only=True) as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT r.run_id,
                                   r.signals_count,
                                   r.prediction_trade_date,
                                   (
                                     SELECT COUNT(*)
                                     FROM engine_signal_scores e
                                     WHERE e.run_id = r.run_id
                                       AND e.tenant_id = r.tenant_id
                                       AND e.user_id = r.user_id
                                   ) AS actual_rows
                            FROM qm_model_inference_runs r
                            WHERE r.tenant_id = :tenant_id
                              AND r.user_id = :user_id
                              AND r.model_id = :model_id
                              AND r.data_trade_date = :trade_date
                              AND r.status = 'completed'
                              AND EXISTS (
                                    SELECT 1
                                    FROM engine_signal_scores e
                                    WHERE e.run_id = r.run_id
                                      AND e.tenant_id = r.tenant_id
                                      AND e.user_id = r.user_id
                              )
                            ORDER BY r.created_at DESC
                            LIMIT 1
                            """
                        ),
                        {
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "model_id": model_id,
                            "trade_date": trade_date,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        item = dict(row)
        pred = item.get("prediction_trade_date")
        if pred is not None and hasattr(pred, "isoformat"):
            item["prediction_trade_date"] = pred.isoformat()
        return item

    async def delete_batch(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                text(
                    """
                    DELETE FROM qm_model_inference_batches
                    WHERE batch_id = :batch_id
                      AND tenant_id = :tenant_id
                      AND user_id = :user_id
                    """
                ),
                {
                    "batch_id": batch_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                },
            )
        return {"deleted": bool(result.rowcount), "batch_id": batch_id}


model_inference_batch_persistence = ModelInferenceBatchPersistence()
