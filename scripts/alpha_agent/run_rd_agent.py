"""RD-Agent 多市场因子挖掘 runner 脚本

由 launcher 作为子进程调用。使用 RDLoopWrapper 运行 RD-Agent 因子挖掘，
提取发现的因子并持久化到 QuantMind 数据库。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rd_agent_run")


async def persist_factors(factors: list[dict], task_id: str, user_id: str, market: str) -> int:
    """持久化因子到数据库"""
    if not factors:
        return 0

    import hashlib
    from backend.services.engine.qlib_app.services.rd_agent_persistence import (
        RDAgentFactorPersistence,
    )

    persistence = RDAgentFactorPersistence()
    await persistence.ensure_tables()

    count = 0
    for f in factors:
        try:
            raw_id = f"{task_id}:{f['name']}"
            factor_id = hashlib.md5(raw_id.encode()).hexdigest()

            metadata = {
                "source": "rd_agent",
                "market": market,
                "task_id": task_id,
                "category": f.get("category", market),
            }
            if f.get("formulation"):
                metadata["formulation"] = f["formulation"]
            if f.get("description"):
                metadata["description"] = f["description"]
            if f.get("feedback"):
                metadata["feedback"] = f["feedback"][:2000]

            await persistence.save_factor(
                factor_id=factor_id,
                factor_name=f["name"],
                factor_code=f.get("code", ""),
                user_id=user_id,
                metadata=metadata,
            )
            count += 1
            logger.info("Persisted factor: %s (market=%s, id=%s)", f["name"], market, factor_id)
        except Exception as e:
            logger.warning("Failed to persist factor %s: %s", f["name"], e)

    return count


def main():
    parser = argparse.ArgumentParser(description="QuantMind RD-Agent Multi-Market Runner")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--market", default="a_share", help="Market: a_share, crypto, hong_kong, us_stock")
    parser.add_argument("--loop-n", type=int, default=3)
    parser.add_argument("--log-dir", default="")
    parser.add_argument("--direction", default="")
    args = parser.parse_args()

    log_dir = args.log_dir or os.getenv("LOG_TRACE_PATH", "/tmp/rd_agent_logs")
    log_dir = str(Path(log_dir).resolve())
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("RD-Agent Runner starting")
    logger.info("  Task ID: %s", args.task_id)
    logger.info("  User ID: %s", args.user_id)
    logger.info("  Market:  %s", args.market)
    logger.info("  Loops:   %d", args.loop_n)
    logger.info("  Log dir: %s", log_dir)
    logger.info("  Direction: %s", args.direction or "(default)")
    logger.info("=" * 60)

    try:
        os.environ["LOG_TRACE_PATH"] = log_dir

        from backend.services.engine.rd_agent.rd_loop_wrapper import RDLoopWrapper

        wrapper = RDLoopWrapper(market=args.market)
        logger.info("[%s] Market adapter: %s (%s)", args.market, wrapper.market_name, args.market)

        t0 = time.time()
        result = asyncio.run(wrapper.run(
            loop_n=args.loop_n,
            task_log_dir=log_dir,
            direction=args.direction,
        ))
        elapsed = time.time() - t0

        factors = result.get("factors", [])
        logger.info("Factor mining completed in %.1fs, found %d factors", elapsed, len(factors))

        for i, f in enumerate(factors, 1):
            logger.info("  Factor %d: %s (expr: %s)", i, f["name"],
                         f.get("formulation", "")[:80] or "N/A")

        # Persist
        count = asyncio.run(persist_factors(factors, args.task_id, args.user_id, args.market))
        logger.info("Persisted %d factors to database", count)

        # Write result JSON for launcher to read
        result_file = Path(log_dir) / "result.json"
        result_file.write_text(json.dumps({
            "task_id": args.task_id,
            "market": args.market,
            "total_factors": len(factors),
            "persisted_factors": count,
            "elapsed_seconds": elapsed,
        }, indent=2))

        logger.info("=" * 60)
        logger.info("RD-Agent task complete! task_id=%s, market=%s", args.task_id, args.market)
        logger.info("  Found: %d factors, Persisted: %d", len(factors), count)
        logger.info("=" * 60)

    except Exception as e:
        logger.exception("RD-Agent runner failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
