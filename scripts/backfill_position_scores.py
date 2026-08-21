"""回填历史推理信号的 position_score（凯利仓位建议）。

对 engine_signal_scores 中已有 fusion_score 但 quality.position 为空的行，
按交易日截面逐日补算 position_score，写回 quality JSONB。

用法（容器内）：
  docker cp scripts/backfill_position_scores.py quantmind:/tmp/
  docker exec quantmind python3 /tmp/backfill_position_scores.py [--model MODEL_ID] [--days 180]
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.services.engine.inference.position_signal import (
    compute_position_scores,
    batch_update_quality,
)


def main(model_id: str | None, days: int | None) -> None:
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "+psycopg2")
    if not url.startswith("postgresql"):
        url = "postgresql+psycopg2://postgres:password@localhost:5432/quantmind"
    eng = create_engine(url, pool_pre_ping=True, future=True)
    Sess = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = Sess()
    try:
        # 取所有需要回填的交易日（有信号、quality.position 为空）
        mwhere = (
            "AND run_id IN (SELECT run_id FROM qm_model_inference_runs WHERE model_id=:m)"
            if model_id else ""
        )
        dwhere = "AND trade_date >= :cutoff" if days else ""
        params: dict = {}
        if model_id:
            params["m"] = model_id
        if days:
            params["cutoff"] = date.today() - timedelta(days=days)
        # distinct trade_date + 该日的 run_id（一个交易日可能多 run，逐 run 回填）
        rows = db.execute(
            text(f"""
                SELECT DISTINCT e.trade_date, e.run_id, e.tenant_id, e.user_id
                FROM engine_signal_scores e
                WHERE e.fusion_score IS NOT NULL
                  AND (e.quality IS NULL OR e.quality->'position' IS NULL)
                  {mwhere} {dwhere}
                ORDER BY e.trade_date DESC
            """),
            params,
        ).fetchall()
        print(f"待回填交易日×run: {len(rows)}")
        if not rows:
            print("无待回填记录")
            return

        done = 0
        for trade_date, run_id, tenant_id, user_id in rows:
            # 取该 run 的全部信号
            sigs = db.execute(
                text("""
                    SELECT symbol, fusion_score, signal_side
                    FROM engine_signal_scores
                    WHERE run_id=:rid AND tenant_id=:tid AND user_id=:uid
                      AND fusion_score IS NOT NULL
                """),
                {"rid": run_id, "tid": tenant_id, "uid": user_id},
            ).fetchall()
            if not sigs:
                continue
            syms = [str(r[0]) for r in sigs]
            scores = [float(r[1]) for r in sigs]
            sides = [str(r[2]) for r in sigs]
            preds = compute_position_scores(syms, scores, sides)
            batch_update_quality(db, str(run_id), str(tenant_id), str(user_id), preds)
            entered = sum(1 for p in preds if p["position_score"] > 0)
            print(f"  {trade_date} run={run_id}: {len(preds)} 条，入场 {entered}")
            done += 1
        print(f"\n完成：回填 {done} 个交易日×run")
    finally:
        db.close()
        eng.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="模型ID（缺省=全模型）")
    ap.add_argument("--days", type=int, default=180, help="只回填最近 N 天（默认180，0=全量）")
    a = ap.parse_args()
    main(a.model, a.days if a.days else None)
