#!/usr/bin/env python3
"""Bulk backfill CCASS June-July 2026 in a single process with higher concurrency."""

from __future__ import annotations

import asyncio, sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.scripts.quanthk_ccass_sync import (
    _load_crawler, _target_dir, _existing_stocks, _normalise_fetch,
    OUT_COLS,
)
import pandas as pd

mod = _load_crawler()
AsyncHKEXFetcher = mod.AsyncHKEXFetcher
StockListManager = mod.StockListManager

# Load stock list once
csv_path = str(Path(__file__).parent / "hk.csv")
stock_df, _ = StockListManager.refresh_stock_list(csv_path)
all_stocks = [(r["id"], r["name"]) for r in stock_df.to_dict("records")]
print(f"Loaded {len(all_stocks)} stocks")

# Dates to backfill
start = date(2026, 6, 3)
end = date(2026, 7, 31)
hk_holidays = {
    '20260403','20260404','20260406','20260407','20260501','20260504',
    '20260519','20260525','20260701','20260925','20261001','20261006',
    '20261007','20261019','20261225',
}

days = []
for d in (start + timedelta(n) for n in range((end - start).days + 1)):
    ds = d.strftime('%Y%m%d')
    if d.weekday() < 5 and ds not in hk_holidays:
        # Skip if already exists and complete
        target = _target_dir() / f"dt={ds}"
        if target.is_dir():
            existing = _existing_stocks(ds)
            if len(existing) > max(50, int(len(stock_df) * 0.5)):
                print(f"SKIP {ds} (already {len(existing)} stocks)")
                continue
        days.append(d)

print(f"Days to sync: {len(days)}")
for d in days:
    print(f"  {d}")
print()

if not days:
    print("Nothing to do!")
    sys.exit(0)

async def fetch_all_for_day(fetcher, target_day, stocks):
    hkex_date = target_day.strftime("%Y/%m/%d")
    tasks = [
        fetcher.fetch_data(code, hkex_date)
        for code, name in stocks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    rows = []
    for (code, name), raw in zip(stocks, results):
        if isinstance(raw, Exception):
            continue
        df = _normalise_fetch(raw, code, name, target_day)
        if df is not None and not df.empty:
            rows.append(df)
    return rows

async def main():
    for i, target_day in enumerate(days):
        ds = target_day.strftime('%Y%m%d')
        print(f"[{i+1}/{len(days)}] {ds} fetching {len(all_stocks)} stocks...")

        async with AsyncHKEXFetcher(max_concurrent=16) as fetcher:
            rows = await fetch_all_for_day(fetcher, target_day, all_stocks)

        if not rows:
            print(f"  -> no data")
            continue

        all_df = pd.concat(rows, ignore_index=True)
        partition_dir = _target_dir() / f"dt={ds}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        out_path = partition_dir / "data.parquet"

        if out_path.exists():
            old = pd.read_parquet(out_path)
            combined = pd.concat([old, all_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["stock_code", "participant_id"], keep="last")
            combined.to_parquet(out_path, index=False)
        else:
            all_df.to_parquet(out_path, index=False)

        print(f"  -> {len(all_df)} rows, {all_df['stock_code'].nunique()} stocks")

    print("DONE")

asyncio.run(main())
