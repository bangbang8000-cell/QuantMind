#!/usr/bin/env python3
"""Backfill financial data (total_mv, pe_ttm, pb) into stock_daily_latest from parquet."""
import os
import time
import logging
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_financial")

def main():
    conn = psycopg2.connect(
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    cur = conn.cursor()

    parquet_path = "/app/db/custom/fundamental_aligned.parquet"
    logger.info(f"Reading {parquet_path}...")
    df = pd.read_parquet(parquet_path, engine="pyarrow")
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    # Keep only rows with financial data
    valid = df[df["total_mv"].notna()][["trade_date", "symbol", "total_mv", "pe_ttm", "pb"]].copy()
    logger.info(f"Rows with valid financial data: {len(valid)}")

    # Create temp table
    cur.execute("DROP TABLE IF EXISTS _tmp_financial_backfill")
    cur.execute("""
        CREATE TEMP TABLE _tmp_financial_backfill (
            trade_date date,
            symbol text,
            total_mv double precision,
            pe_ttm double precision,
            pb double precision
        )
    """)
    conn.commit()

    # Insert into temp table using execute_values
    rows = [
        (r.trade_date, r.symbol,
         float(r.total_mv),
         float(r.pe_ttm) if pd.notna(r.pe_ttm) else None,
         float(r.pb) if pd.notna(r.pb) else None)
        for r in valid.itertuples(index=False)
    ]
    logger.info(f"Inserting {len(rows)} rows into temp table...")
    execute_values(cur, """
        INSERT INTO _tmp_financial_backfill (trade_date, symbol, total_mv, pe_ttm, pb)
        VALUES %s
    """, rows, page_size=10000)
    conn.commit()
    logger.info("Temp table populated successfully")

    # Bulk update using UPDATE FROM
    logger.info("Updating stock_daily_latest from temp table...")
    t0 = time.time()
    cur.execute("""
        UPDATE stock_daily_latest s
        SET total_mv = t.total_mv,
            pe_ttm = t.pe_ttm,
            pb = t.pb
        FROM _tmp_financial_backfill t
        WHERE s.trade_date = t.trade_date
          AND s.symbol = t.symbol
          AND (s.total_mv IS NULL OR s.pe_ttm IS NULL OR s.pb IS NULL)
    """)
    updated = cur.rowcount
    conn.commit()
    elapsed = time.time() - t0
    logger.info(f"Updated {updated} rows in {elapsed:.1f}s")

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS _tmp_financial_backfill")
    conn.commit()
    conn.close()
    logger.info("Done!")

if __name__ == "__main__":
    main()
