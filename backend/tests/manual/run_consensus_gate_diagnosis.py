"""诊断共识池门槛是否可满足。

计划里 consensus_long 要求 topk_hits >= ceil(0.6N)。但若每日 Top-K 换手率极高，
该门槛在真实数据下可能恒为空集。此脚本给出 topk_hits 与分位命中数的实际分布，
用来决定共识口径该用「绝对 Top-K 命中」还是「分位区间命中」。
"""
import asyncio
import math
import sys
from collections import Counter

from backend.services.api.routers import model_training as mt

TENANT, USER_ID = "default", "00000001"


async def main() -> None:
    from backend.shared.database_manager_v2 import init_database

    await init_database()

    batch_id = sys.argv[1]
    batch = await mt.model_inference_batch_persistence.get_batch(
        batch_id=batch_id, tenant_id=TENANT, user_id=USER_ID
    )
    panel, dates = await mt._load_batch_panel(
        batch=batch, tenant_id=TENANT, user_id=USER_ID
    )
    n = len(dates)
    universe = int(panel.groupby("trade_date")["symbol"].nunique().median())
    print("N=%d 每日样本中位数=%d" % (n, universe))
    gate = math.ceil(0.6 * n)
    print("计划门槛 topk_hits >= ceil(0.6*%d) = %d" % (n, gate))

    for k in (20, 50, 100, 200):
        hits = Counter()
        for d, g in panel.groupby("trade_date"):
            for s in g.nsmallest(k, "rk")["symbol"]:
                hits[s] += 1
        dist = Counter(hits.values())
        passing = sum(c for h, c in dist.items() if h >= gate)
        expected_max = k * n / universe
        print()
        print("--- Top-%d (占全市场 %.2f%%) ---" % (k, 100.0 * k / universe))
        print("  上榜过的股票数: %d" % len(hits))
        print("  命中次数分布: %s" % dict(sorted(dist.items())))
        print("  满足 >=%d 次的股票数: %d" % (gate, passing))
        print("  纯随机下单只期望命中次数 = %.2f" % expected_max)

    print()
    print("=== 改用分位门槛（scale-free）===")
    for thr in (0.90, 0.95, 0.99):
        hits = Counter()
        for d, g in panel.groupby("trade_date"):
            for s in g.loc[g["pct"] >= thr, "symbol"]:
                hits[s] += 1
        dist = Counter(hits.values())
        passing = sum(c for h, c in dist.items() if h >= gate)
        print(
            "  pct>=%.2f (每日约 %d 只): 上榜股票 %d, 满足>=%d次 %d 只"
            % (thr, int(universe * (1 - thr)), len(hits), gate, passing)
        )

    print()
    print("=== 每日 Top-20 换手率 ===")
    prev = None
    for d in dates:
        g = panel[panel["trade_date"] == d]
        cur = set(g.nsmallest(20, "rk")["symbol"])
        if prev is not None:
            j = len(cur & prev) / len(cur | prev) if (cur | prev) else 0
            print("  %s 与前日重叠 %d/20  Jaccard=%.3f 换手=%.3f" % (d, len(cur & prev), j, 1 - j))
        prev = cur


asyncio.run(main())
