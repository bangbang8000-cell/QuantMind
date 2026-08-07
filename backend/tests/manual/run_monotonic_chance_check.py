"""量化「一直上升」在小窗口下的偶然性。

用户核心诉求之一是「5 天里排名或分数一直上升的股票」。但严格单调上升在
N 天随机序列中的概率是 1/N!，样本量一大就会有大量偶然入选者。这个脚本
用真实批次面板算出实际单调数 vs 纯随机期望数，判断该榜单在给定 N 下是否有信息量。
"""
import asyncio
import math
import sys

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
    print("batch=%s N=%d dates=%s" % (batch_id, n, dates))

    full = panel.groupby("symbol").filter(lambda g: len(g) == n)
    total = full["symbol"].nunique()
    print("全窗口出现的股票数: %d" % total)

    mono_up = 0
    mono_down = 0
    for _sym, g in full.sort_values("trade_date").groupby("symbol"):
        p = g["pct"].tolist()
        if all(b > a for a, b in zip(p, p[1:])):
            mono_up += 1
        if all(b < a for a, b in zip(p, p[1:])):
            mono_down += 1

    expected = total / math.factorial(n)
    print()
    print("严格单调上升: 实际 %d  纯随机期望 %.1f  倍数 %.2fx"
          % (mono_up, expected, mono_up / expected if expected else 0))
    print("严格单调下降: 实际 %d  纯随机期望 %.1f  倍数 %.2fx"
          % (mono_down, expected, mono_down / expected if expected else 0))
    print()
    print("解读: 倍数接近 1 → 该榜单基本是噪声；显著 >1 → 存在真实持续性")
    print("N=%d 时单条序列偶然单调的概率 = 1/%d! = %.4f%%"
          % (n, n, 100.0 / math.factorial(n)))


asyncio.run(main())
