#!/usr/bin/env python3
"""南向资金（港股通）→ QuantHK 增量爬虫同步脚本。

复用 HKEX 南向爬虫（hsgt_south_crawler.py）的 AsyncNanxiangFetcher，按日期
抓取全市场港股通持仓，落盘到 quanthk 本地 parquet。

落盘格式:
  {quanthk}/2_base_sector/hsgt_south/dt=YYYYMMDD/data.parquet
  股份代号 5位（00700）→ 4位+.HK（0700.HK）

用法:
  python backend/scripts/quanthk_south_sync.py --days 5
  python backend/scripts/quanthk_south_sync.py --date 2026-08-07
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quanthk_south_sync")

QUANTHK_DATA_DIR = Path(
    os.getenv("QM_QUANTHK_DATA_DIR", str(PROJECT_ROOT / "data" / "quanthk"))
)
REL_DIR = "2_base_sector/hsgt_south"

CRAWLER_PATH = str(Path(__file__).parent / "hsgt_south_crawler.py")

_crawler_mod = None


def _load_crawler():
    global _crawler_mod
    if _crawler_mod is not None:
        return _crawler_mod
    spec = importlib.util.spec_from_file_location("hsgt_south", CRAWLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _crawler_mod = mod
    return mod


def _quanthk_root() -> Path:
    env_val = os.getenv("QM_QUANTHK_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/data/quanthk").is_dir():
        return Path("/data/quanthk")
    QUANTHK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTHK_DATA_DIR


def _to_qhk_symbol(code: str) -> str:
    code = code.strip().zfill(5)
    if code.startswith("0") and len(code) == 5:
        code = code[1:]
    return f"{code}.HK"


def _existing_partitions() -> set[str]:
    d = _quanthk_root() / REL_DIR
    if not d.is_dir():
        return set()
    return {p.name[3:] for p in d.glob("dt=*")}


def _normalise(df: pd.DataFrame, query_date: date) -> pd.DataFrame | None:
    """爬虫输出 → 标准列。列：股份代号/名称/于中央结算系统的持股量/百分比"""
    if df is None or df.empty:
        return None
    rename = {}
    for col in df.columns:
        if "股份代号" in col:
            rename[col] = "stock_code"
        elif "名称" in col:
            rename[col] = "stock_name"
        elif "持股量" in col:
            rename[col] = "holding_quantity"
        elif "百分比" in col:
            rename[col] = "holding_percentage"
    df = df.rename(columns=rename)

    if "stock_code" not in df.columns or "holding_quantity" not in df.columns:
        return None

    df["symbol"] = df["stock_code"].astype(str).map(_to_qhk_symbol)
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")
    df["holding_percentage"] = (
        df["holding_percentage"].astype(str).str.replace("%", "", regex=False).str.strip()
    )
    df["holding_percentage"] = pd.to_numeric(df["holding_percentage"], errors="coerce").fillna(0.0) / 100.0
    df["query_date"] = query_date
    out_cols = ["symbol", "stock_name", "holding_quantity", "holding_percentage", "query_date"]
    df = df[[c for c in out_cols if c in df.columns]]
    return df.dropna(subset=["symbol"])


async def _sync_date(mod, query_date: date, target_dir: Path) -> dict:
    """同步单个交易日。"""
    date_str = query_date.strftime("%Y%m%d")
    hkex_date = query_date.strftime("%Y/%m/%d")

    async with mod.AsyncNanxiangFetcher() as fetcher:
        df = await fetcher.fetch_market_data(hkex_date)

    norm = _normalise(df, query_date)
    if norm is None or norm.empty:
        return {"date": date_str, "status": "no_data"}

    dt_dir = target_dir / f"dt={date_str}"
    dt_dir.mkdir(parents=True, exist_ok=True)
    out = dt_dir / "data.parquet"
    if out.exists():
        old = pd.read_parquet(out)
        combined = pd.concat([old, norm], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol"], keep="last")
        combined.to_parquet(out, index=False)
    else:
        norm.to_parquet(out, index=False)

    return {"date": date_str, "status": "synced", "rows": len(norm)}


def sync(*, days: int = 5, target_date: str | None = None, dry_run: bool = False) -> dict:
    """增量同步南向资金。"""
    mod = _load_crawler()

    end = date.today()
    if target_date:
        end = datetime.strptime(target_date, "%Y-%m-%d").date()

    existing = _existing_partitions()

    # 取最近 days 个交易日（缺的才补）
    trading = []
    d = end
    while len(trading) < days:
        if mod.HKEXTradingCalendar.is_trading_day(d.strftime("%Y-%m-%d")):
            trading.append(d)
        d -= timedelta(days=1)
    trading.reverse()

    todo = [day for day in trading if day.strftime("%Y%m%d") not in existing]
    log.info("最近 %d 个交易日，待补 %d 个（已有 %d 分区）", len(trading), len(todo), len(existing))

    if dry_run:
        return {"trading_days": len(trading), "todo": len(todo), "dates": [d.strftime("%Y%m%d") for d in todo], "dry_run": True}

    target_dir = _quanthk_root() / REL_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for day in todo:
        r = asyncio.run(_sync_date(mod, day, target_dir))
        results.append(r)
        log.info("[%s] %s", day.strftime("%Y%m%d"), r["status"])

    synced = [r for r in results if r["status"] == "synced"]
    return {
        "checked": len(todo),
        "synced": len(synced),
        "details": results,
        "target_dir": str(target_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="南向资金 → QuantHK 增量同步")
    parser.add_argument("--days", type=int, default=5, help="同步最近多少个交易日")
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    try:
        result = sync(days=args.days, target_date=args.date, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("同步失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
