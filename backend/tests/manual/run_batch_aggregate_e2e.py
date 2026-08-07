"""端到端验证批量推理聚合端点（P2 验收 8~10）。

用 P1 已跑出的真实批次，核对聚合结果能否手算复现。
"""
import asyncio
import sys

from backend.services.api.routers import model_training as mt

USER = {
    "user_id": "00000001",
    "tenant_id": "default",
    "username": "admin",
    "is_admin": True,
    "roles": ["admin"],
}


async def main() -> None:
    from backend.shared.database_manager_v2 import init_database

    await init_database()

    batch_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not batch_id:
        lst = await mt.list_batch_inferences(
            model_id=None, status=None, page=1, page_size=1, current_user=USER
        )
        if not lst["items"]:
            print("no batches found")
            return
        batch_id = lst["items"][0]["batch_id"]
    print("batch_id:", batch_id)

    agg = await mt.get_batch_inference_aggregate(
        batch_id=batch_id,
        top_k=20,
        decay=0.85,
        lam=0.5,
        mu=0.1,
        min_coverage=0.6,
        consensus_band=0.95,
        side="both",
        current_user=USER,
    )

    meta = agg["meta"]
    print()
    print("=== META ===")
    for k in (
        "window_days",
        "horizon_days",
        "effective_independent_bets",
        "overlap_ratio",
        "signal_autocorr",
        "symbol_count",
        "span_calendar_days",
        "anchor_adjusted",
    ):
        print("  %-30s %s" % (k, meta.get(k)))
    for w in meta.get("warnings") or []:
        print("  WARN", w)
    print("  cached:", agg.get("cached"))

    print()
    print("=== DAILY ===")
    for d in agg["daily"]:
        if d.get("missing"):
            print("  %s MISSING" % d["trade_date"])
            continue
        print(
            "  %s n=%-5s mean=%-9s std=%-8s buy=%-5s sell=%-5s turnover=%s consensus_overlap=%s"
            % (
                d["trade_date"],
                d.get("count"),
                d.get("score_mean"),
                d.get("score_std"),
                d.get("buy_count"),
                d.get("sell_count"),
                d.get("topk_turnover"),
                d.get("consensus_overlap"),
            )
        )

    print()
    print("=== GROUPS (counts) ===")
    for k, v in agg["groups"].items():
        print("  %-24s %d" % (k, len(v)))

    print()
    print("=== MOVERS keys ===")
    for k, v in agg["movers"].items():
        if isinstance(v, dict):
            inner = {ik: (len(iv) if isinstance(iv, list) else iv) for ik, iv in v.items()}
            print("  %-20s %s" % (k, inner))

    print()
    print("=== TOP 8 by conviction_long ===")
    for r in agg["per_symbol"][:8]:
        print(
            "  %-12s %-8s conv=%-6s wpct=%-7s cov=%-5s topk=%-3s rho=%-7s mono_up=%-5s streak=%s"
            % (
                r["symbol"],
                (r.get("stock_name") or "")[:6],
                r["conviction_long"],
                r["weighted_pct"],
                r["coverage"],
                r["topk_hits"],
                r.get("trend_rho"),
                r.get("is_monotonic_up"),
                r.get("up_streak"),
            )
        )

    print()
    print("=== 手算复现：取 consensus_long 首只，逐日核对 ===")
    pool = agg["groups"].get("consensus_long") or agg["per_symbol"]
    if pool:
        target = pool[0]["symbol"]
        panel, dates = await mt._load_batch_panel(
            batch=await mt.model_inference_batch_persistence.get_batch(
                batch_id=batch_id, tenant_id="default", user_id="00000001"
            ),
            tenant_id="default",
            user_id="00000001",
        )
        sub = panel[panel["symbol"] == target].sort_values("trade_date")
        print("  symbol:", target, " dates:", dates)
        for _, row in sub.iterrows():
            print(
                "    %s score=%-10.6f rk=%-6s pct=%.6f side=%s"
                % (
                    row["trade_date"],
                    row["fusion_score"],
                    int(row["rk"]),
                    row["pct"],
                    row["signal_side"],
                )
            )
        # 手算加权分位
        n = len(dates)
        num = den = 0.0
        for _, row in sub.iterrows():
            age = n - 1 - dates.index(row["trade_date"])
            w = 0.85**age
            num += w * row["pct"]
            den += w
        manual = num / den if den else None
        stated = next(
            (r["weighted_pct"] for r in agg["per_symbol"] if r["symbol"] == target), None
        )
        print("  手算 weighted_pct = %.6f  聚合输出 = %s" % (manual, stated))
        print("  一致" if abs(manual - float(stated)) < 1e-3 else "  ✗ 不一致！")

    print()
    print("=== 参数敏感性：top_k=50 应改变榜单但不重跑推理 ===")
    agg50 = await mt.get_batch_inference_aggregate(
        batch_id=batch_id,
        top_k=50,
        decay=0.85,
        lam=0.5,
        mu=0.1,
        min_coverage=0.6,
        consensus_band=0.95,
        side="both",
        current_user=USER,
    )
    print(
        "  top_k=20 consensus_long=%d  top_k=50 consensus_long=%d  cached=%s"
        % (
            len(agg["groups"].get("consensus_long") or []),
            len(agg50["groups"].get("consensus_long") or []),
            agg50.get("cached"),
        )
    )


asyncio.run(main())
