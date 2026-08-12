import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.client import build_client
from src.utils.config import Config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bridge-linux")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--mode", default="auto", choices=["auto", "http", "file_sync"])
    args = parser.parse_args()

    cfg = Config(args.config)
    client = build_client(cfg, mode=args.mode)
    await client.channels.start()

    log.info("bridge-linux 已就绪. 供 QuandMind 策略通过 TradingClient 调用.")
    log.info("在 Python 中使用: from src.api.client import build_client")
    log.info("  from src.utils.config import Config")
    log.info("  client = build_client(Config('config.yaml'))")
    log.info("  client.query_account() / client.buy('600519.SH', 100) ...")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await client.channels.stop()


if __name__ == "__main__":
    asyncio.run(main())
