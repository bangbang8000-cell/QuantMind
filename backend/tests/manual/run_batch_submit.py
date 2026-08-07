"""提交一个批次并等待完成，供后续聚合/统计验证使用。

用法: python run_batch_submit.py <anchor_date> <window_days>
"""
import asyncio
import sys
import time

from backend.services.api.routers import model_training as mt

USER = {
    "user_id": "00000001",
    "tenant_id": "default",
    "username": "admin",
    "is_admin": True,
    "roles": ["admin"],
}
MODEL = "mdl_train_20260803015340_1637df5e_0d322a31"


async def main() -> None:
    from backend.shared.database_manager_v2 import init_database

    await init_database()

    anchor = sys.argv[1] if len(sys.argv) > 1 else "2026-07-22"
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    req = mt.BatchInferenceRequest(
        model_id=MODEL, anchor_date=anchor, window_days=window, top_k=20
    )
    r = await mt.submit_batch_inference(payload=req, current_user=USER)
    bid = r["batch_id"]
    print("batch_id:", bid)
    print("trade_dates:", r["trade_dates"])

    t0 = time.time()
    last = None
    while time.time() - t0 < 3600:
        b = await mt.get_batch_inference(batch_id=bid, current_user=USER)
        sig = (b["status"], b["progress_done"])
        if sig != last:
            print(
                "  [%5.1fs] %s %d/%d cur=%s"
                % (
                    time.time() - t0,
                    b["status"],
                    b["progress_done"],
                    b["progress_total"],
                    b.get("current_trade_date"),
                )
            )
            last = sig
        if b["status"] in ("completed", "partial", "failed"):
            print("终态:", b["status"], b.get("error_message") or "")
            reused = sum(1 for m in b["member_runs"] if m["reused"])
            failed = [m["trade_date"] for m in b["member_runs"] if m["status"] != "completed"]
            print("reused=%d/%d failed=%s" % (reused, len(b["member_runs"]), failed))
            print("BATCH_ID=%s" % bid)
            return
        await asyncio.sleep(3)


asyncio.run(main())
