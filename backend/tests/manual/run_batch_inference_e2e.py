"""端到端验证批量推理：直接调用端点函数，绕过 HTTP auth 中间件。

验证点（对应计划 P1 验收 2~6）：
  - 提交返回 batch_id + 窗口口径
  - 逐日进度推进
  - 第二次提交秒级复用（reused=true）
  - 并发去重（409）
"""
import asyncio
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


async def poll(batch_id: str, timeout_s: int = 900) -> dict:
    last = None
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        b = await mt.get_batch_inference(batch_id=batch_id, current_user=USER)
        sig = (b["status"], b["progress_done"], b.get("current_trade_date"))
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
            return b
        await asyncio.sleep(2)
    raise TimeoutError("batch did not finish in %ds" % timeout_s)


async def main() -> None:
    from backend.shared.database_manager_v2 import init_database
    from backend.services.engine.services.model_inference_batch_persistence import (
        model_inference_batch_persistence,
    )

    await init_database()
    await model_inference_batch_persistence.ensure_tables()

    print("=== 提交 1：anchor=2026-07-22 window=3 ===")
    req = mt.BatchInferenceRequest(
        model_id=MODEL, anchor_date="2026-07-22", window_days=3, top_k=20
    )
    r1 = await mt.submit_batch_inference(payload=req, current_user=USER)
    print("batch_id:", r1["batch_id"])
    print("trade_dates:", r1["trade_dates"])
    wm = r1["window_meta"]
    print(
        "window_meta: N=%s H=%s eff_bets=%s span_cal=%s"
        % (
            wm["window_days"],
            wm["horizon_days"],
            wm["effective_independent_bets"],
            wm["span_calendar_days"],
        )
    )
    for w in wm["warnings"]:
        print("  WARN", w)

    print("--- 并发去重检查（应 409）---")
    try:
        await mt.submit_batch_inference(payload=req, current_user=USER)
        print("  FAIL: 并发提交未被拒绝")
    except Exception as exc:
        print("  OK 被拒绝:", type(exc).__name__, getattr(exc, "detail", exc))

    b1 = await poll(r1["batch_id"])
    print("终态:", b1["status"], "error:", b1.get("error_message"))
    for m in b1["member_runs"]:
        print(
            "  %s run=%s status=%s reused=%s signals=%s %s"
            % (
                m["trade_date"],
                (m.get("run_id") or "")[:22],
                m["status"],
                m["reused"],
                m["signals_count"],
                m.get("error_message", "") or "",
            )
        )

    print()
    print("=== 提交 2：同参数，应全部 reused 且秒级 ===")
    t0 = time.time()
    r2 = await mt.submit_batch_inference(payload=req, current_user=USER)
    b2 = await poll(r2["batch_id"])
    elapsed = time.time() - t0
    reused = sum(1 for m in b2["member_runs"] if m["reused"])
    print(
        "终态: %s 耗时 %.1fs reused=%d/%d"
        % (b2["status"], elapsed, reused, len(b2["member_runs"]))
    )

    print()
    print("=== 历史列表 ===")
    lst = await mt.list_batch_inferences(
        model_id=MODEL, status=None, page=1, page_size=5, current_user=USER
    )
    print("total:", lst["total"])
    for it in lst["items"]:
        print(
            "  %s anchor=%s N=%s status=%s %s/%s"
            % (
                it["batch_id"],
                it["anchor_date"],
                it["window_days"],
                it["status"],
                it["progress_done"],
                it["progress_total"],
            )
        )

    print()
    print("=== 清理提交 2 ===")
    print(await mt.delete_batch_inference(batch_id=r2["batch_id"], current_user=USER))
    print("KEEP batch_id for aggregate test:", r1["batch_id"])


asyncio.run(main())
