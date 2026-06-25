#!/usr/bin/env python3
"""
回填 stock_daily_latest 基本面数据 (pe_ttm / pb / roe / total_mv / float_mv / industry).

数据源策略 (双源, 互补):
  Phase 1 - fundamental_aligned.parquet (本地离线, 权威历史值)
            覆盖 2020-01-02 ~ 2026-05-20, 含 pe_ttm/pb/roe/total_mv/float_mv/industry.
            前缀代码 (SH600000) -> 后缀代码 (600000.SH) 转换后 JOIN.
  Phase 2 - Eastmoney clist 直连 API (当日快照, 补 parquet 截止后的最新月)
            f9=PE动态 f23=PB f20=总市值 f21=流通市值, 全市场 ~5860 只.
            快照值按 DB 各日收盘价线性缩放, 得到逐日估值估计.

两阶段均用 COALESCE(NULLIF(db, 0/空), src) 仅填充缺失, 保留已有有效数据.

用法:
    python backend/scripts/backfill_sdl_fundamentals.py --diagnose        # 仅诊断
    python backend/scripts/backfill_sdl_fundamentals.py --phase-parquet   # 阶段1: parquet 批量
    python backend/scripts/backfill_sdl_fundamentals.py --phase-em        # 阶段2: Eastmoney 最新月
    python backend/scripts/backfill_sdl_fundamentals.py --all            # 两阶段全跑
    python backend/scripts/backfill_sdl_fundamentals.py --dry-run        # 试运行
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

PARQUET_PATH = "/app/db/custom/fundamental_aligned.parquet"
# parquet 最晚日期之后, 由 Eastmoney 快照覆盖
PARQUET_CUTOFF = date(2026, 5, 20)

FUND_COLS = ["pe_ttm", "pb", "roe", "total_mv", "float_mv", "industry"]


def _get_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', 'quantmind')}:{os.getenv('DB_PASSWORD', 'quantmind2026')}"
        f"@{os.getenv('DB_HOST', 'db')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'quantmind')}",
    )
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "+psycopg2")
    if not db_url.startswith("postgresql"):
        db_url = (
            f"postgresql+psycopg2://{os.getenv('DB_USER', 'quantmind')}:"
            f"{os.getenv('DB_PASSWORD', 'quantmind2026')}@{os.getenv('DB_HOST', 'db')}:5432/quantmind"
        )
    return create_engine(db_url, pool_pre_ping=True, future=True)


def diagnose(engine):
    print("\n" + "=" * 70)
    print("  stock_daily_latest 基本面覆盖率诊断")
    print("=" * 70)
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM stock_daily_latest WHERE volume > 0")).scalar()
        print(f"\n📊 总行数: {total:,}")
        r = conn.execute(text("SELECT MIN(trade_date), MAX(trade_date) FROM stock_daily_latest WHERE volume > 0")).one()
        print(f"   日期范围: {r[0]} → {r[1]}")
        print(f"\n📋 基本面列覆盖率:")
        for col in FUND_COLS:
            if col == "industry":
                has = conn.execute(text(
                    "SELECT COUNT(*) FROM stock_daily_latest WHERE volume>0 AND industry IS NOT NULL AND industry <> ''"
                )).scalar()
            else:
                has = conn.execute(text(
                    f"SELECT COUNT(*) FROM stock_daily_latest WHERE volume>0 AND {col} IS NOT NULL AND {col} > 0"
                )).scalar()
            pct = has / total * 100 if total else 0
            status = "✅" if pct > 80 else "⚠️ " if pct > 10 else "❌"
            print(f"   {status} {col:12s}: {has:,} / {total:,} ({pct:.1f}%)")
    return total


def _prefix_to_suffix(sym: str) -> str | None:
    """SH600000 -> 600000.SH ; 仅保留 6 位数字股票代码, 剔除指数."""
    if not isinstance(sym, str) or len(sym) < 8:
        return None
    market, code = sym[:2], sym[2:]
    if market not in ("SH", "SZ", "BJ"):
        return None
    if not code.isdigit() or len(code) != 6:
        return None
    return f"{code}.{market}"


def phase_parquet(engine, dry_run: bool = False) -> int:
    """阶段1: 从 fundamental_aligned.parquet 批量回填历史基本面."""
    print("\n" + "=" * 70)
    print("  阶段1: parquet 批量回填 (历史权威值)")
    print("=" * 70)

    if not os.path.exists(PARQUET_PATH):
        print(f"   ❌ parquet 不存在: {PARQUET_PATH}")
        return 0

    print(f"\n1️⃣  读取 parquet: {PARQUET_PATH}")
    cols = ["trade_date", "symbol", "pe_ttm", "pb", "roe", "total_mv", "float_mv", "industry"]
    df = pd.read_parquet(PARQUET_PATH, columns=cols)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    print(f"   parquet 原始: {len(df):,} 行, {df['symbol'].nunique()} 只, "
          f"{df['trade_date'].min()} → {df['trade_date'].max()}")

    # 转换代码格式: 前缀 -> 后缀
    df["symbol"] = df["symbol"].map(_prefix_to_suffix)
    df = df.dropna(subset=["symbol"])
    print(f"   代码转换后 (6位数字股票): {df['symbol'].nunique()} 只")

    # 仅保留 DB 日期范围内 (parquet 能覆盖的部分)
    with engine.connect() as conn:
        r = conn.execute(text("SELECT MIN(trade_date), MAX(trade_date) FROM stock_daily_latest WHERE volume>0")).one()
    db_min, db_max = r[0], r[1]
    df = df[(df["trade_date"] >= db_min) & (df["trade_date"] <= PARQUET_CUTOFF)]
    print(f"   过滤至 DB 日期范围 & ≤{PARQUET_CUTOFF}: {len(df):,} 行")

    # 数值列转 float, 剔除无效
    for c in ["pe_ttm", "pb", "roe", "total_mv", "float_mv"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["industry"] = df["industry"].fillna("").astype(str).replace("nan", "")

    if dry_run:
        nn = {c: int(df[c].notna().sum()) for c in FUND_COLS if c != "industry"}
        nn["industry"] = int((df["industry"] != "").sum())
        print(f"   [DRY RUN] 将写入临时表 {len(df):,} 行, 非空分布: {nn}")
        return 0

    print(f"\n2️⃣  写入临时表 tmp_fund_backfill ({len(df):,} 行)...")
    t0 = time.time()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tmp_fund_backfill"))
    df.to_sql("tmp_fund_backfill", engine, if_exists="replace", index=False,
              method="multi", chunksize=5000)
    # 建索引加速 JOIN
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS tmp_fund_sym_dt ON tmp_fund_backfill(symbol, trade_date)"
        ))
    print(f"   临时表就绪 ({time.time()-t0:.1f}s)")

    print(f"\n3️⃣  UPDATE JOIN 回填 (仅填充缺失, COALESCE 保留已有值)...")
    # 行业是文本, 用 NULLIF('') ; 数值用 NULLIF(0)
    sets = []
    for c in FUND_COLS:
        if c == "industry":
            sets.append(f"industry = COALESCE(NULLIF(s.industry, ''), t.industry, s.industry)")
        else:
            sets.append(f"{c} = COALESCE(NULLIF(s.{c}, 0), t.{c}, s.{c})")
    sql = text(f"""
        UPDATE stock_daily_latest s
        SET {', '.join(sets)}
        FROM tmp_fund_backfill t
        WHERE s.symbol = t.symbol
          AND s.trade_date = t.trade_date
          AND s.volume > 0
    """)
    with engine.begin() as conn:
        result = conn.execute(sql)
        updated = result.rowcount
    print(f"   ✅ 阶段1完成: {updated:,} 行基本面已回填 ({time.time()-t0:.1f}s)")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tmp_fund_backfill"))
    return updated


def _fetch_eastmoney_snapshot() -> pd.DataFrame:
    """直连 Eastmoney clist API, 分页拉取全市场快照 (含逐页重试)."""
    import requests

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    # f2=最新价 f9=PE动态 f12=代码 f14=名称 f20=总市值 f21=流通市值 f23=市净率
    fields = "f2,f9,f12,f14,f20,f21,f23"
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}

    # Eastmoney clist 每页上限 100 条 (请求更大 pz 会被服务端截断到 100).
    # 服务端在连续请求 ~1100 次后会断连 (RemoteDisconnected), 故:
    #   - 逐页指数退避重试 (1/2/4/8s)
    #   - 同页全部失败后进入外层恢复 (sleep 10s 再试同页, 而非中断), 最多 3 轮
    #   - 已累积的 all_items 保留, 实现断点续传
    page, page_size, all_items, total = 1, 100, [], None
    max_pages = 120  # 安全上限, 防止死循环
    backoff = [1, 2, 4, 8]
    sess = requests.Session()
    sess.headers.update(headers)
    while page <= max_pages:
        params = {"pn": page, "pz": page_size, "po": 1, "np": 1, "fltt": 2,
                  "invt": 2, "fid": "f12", "fs": fs, "fields": fields}
        data = None
        for attempt, delay in enumerate(backoff + [0], start=1):
            try:
                r = sess.get(url, params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:50]}"
                if attempt <= len(backoff):
                    time.sleep(delay)
        if data is None:
            # 外层恢复: 长睡后重试同页, 最多 3 轮 (断点续传, 不丢失已抓数据)
            recovered = False
            for outer in range(3):
                print(f"   ⏳ 第 {page} 页失败 ({last_err}), 10s 后恢复重试 ({outer+1}/3)")
                time.sleep(10)
                try:
                    r = sess.get(url, params=params, timeout=20)
                    r.raise_for_status()
                    data = r.json()
                    recovered = True
                    break
                except Exception as e:
                    last_err = f"{type(e).__name__}: {str(e)[:50]}"
            if not recovered:
                print(f"   ⚠️  第 {page} 页恢复 3 轮仍失败, 接受部分快照 ({len(all_items)} 只)")
                break
        if total is None:
            total = data.get("data", {}).get("total", 0)
        items = data.get("data", {}).get("diff", [])
        all_items.extend(items)
        print(f"   第 {page} 页: {len(items)} 条, 累计 {len(all_items)}/{total}")
        # 仅当某页空数据或已拉满 total 时停止 (不依赖 len<page_size, 避免末页误判)
        if not items or (total and len(all_items) >= total):
            break
        page += 1
        time.sleep(0.5)

    df = pd.DataFrame(all_items)
    if df.empty:
        return df
    df = df.rename(columns={"f12": "code", "f14": "name", "f2": "price",
                            "f9": "pe_ttm", "f23": "pb", "f20": "total_mv", "f21": "float_mv"})
    for c in ["price", "pe_ttm", "pb", "total_mv", "float_mv"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # code -> suffix symbol
    def _c2s(code):
        code = str(code).zfill(6)
        if code.startswith(("60", "68", "9")):
            return f"{code}.SH"
        if code.startswith(("0", "3", "2")):
            return f"{code}.SZ"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return None
    df["symbol"] = df["code"].map(_c2s)
    df = df.dropna(subset=["symbol"])
    return df[["symbol", "name", "price", "pe_ttm", "pb", "total_mv", "float_mv"]]


def phase_eastmoney(engine, dry_run: bool = False) -> int:
    """阶段2: Eastmoney 快照补 parquet 截止后的最新月 (按收盘价缩放为逐日估值)."""
    print("\n" + "=" * 70)
    print(f"  阶段2: Eastmoney 快照 (补 >{PARQUET_CUTOFF} 的最新月)")
    print("=" * 70)

    print("\n1️⃣  拉取 Eastmoney 全市场快照...")
    snap = _fetch_eastmoney_snapshot()
    if snap.empty:
        print("   ❌ 未能拉取任何快照数据")
        return 0
    print(f"   快照: {len(snap)} 只, pe_ttm 非空 {snap['pe_ttm'].notna().sum()}, "
          f"total_mv 非空 {snap['total_mv'].notna().sum()}")

    # 取 DB 最新月各日 close + 最新日 close (基准), 用于基一致的逐日缩放.
    # ⚠️ 关键: DB close 是前复权价 (adj_factor<1), 绝不能用 Eastmoney 实时真实价做分母,
    #   否则 ratio = 前复权close/真实价 ≈ adj_factor, 使 pe/pb/mv 被错误缩小到 ~adj_factor 倍.
    # 正确: ratio = close_db(d) / close_db(最新日), 两者同前复权基准 = 真实价格变动比.
    print(f"\n2️⃣  读取 DB 最新月 close (>{PARQUET_CUTOFF}) 及最新日基准 close...")
    with engine.connect() as conn:
        snap_date = conn.execute(
            text("SELECT MAX(trade_date) FROM stock_daily_latest WHERE volume > 0")
        ).scalar()
        rows = conn.execute(text("""
            SELECT symbol, trade_date, close
            FROM stock_daily_latest
            WHERE trade_date > :cutoff AND volume > 0
            ORDER BY symbol, trade_date
        """), {"cutoff": PARQUET_CUTOFF}).fetchall()
        ref_rows = conn.execute(text("""
            SELECT symbol, close AS ref_close
            FROM stock_daily_latest
            WHERE trade_date = :d AND volume > 0
        """), {"d": snap_date}).fetchall()
    if not rows:
        print("   ✅ DB 最新月无数据, 跳过")
        return 0
    db = pd.DataFrame(rows, columns=["symbol", "trade_date", "close"])
    db["trade_date"] = db["trade_date"].astype(str)
    ref = pd.DataFrame(ref_rows)
    print(f"   DB 最新月: {len(db):,} 行, {db['symbol'].nunique()} 只; 基准日 {snap_date}: {len(ref):,} 只")

    # 重置最新月 Eastmoney 负责的 4 列 (清除此前错误缩放值), 随后基一致重填.
    # parquet 阶段(≤cutoff)与 roe 不受影响.
    if not dry_run:
        with engine.begin() as conn:
            r = conn.execute(text("""
                UPDATE stock_daily_latest
                SET pe_ttm = NULL, pb = NULL, total_mv = NULL, float_mv = NULL
                WHERE trade_date > :cutoff AND volume > 0
            """), {"cutoff": PARQUET_CUTOFF})
            print(f"   重置最新月 pe/pb/total_mv/float_mv: {r.rowcount:,} 行置 NULL (将基一致重填)")

    # 合并快照 (仅 pe/pb/mv, 不依赖 snap_price) + 基准 close
    snap_cols = snap[["symbol", "pe_ttm", "pb", "total_mv", "float_mv"]].rename(
        columns={"pe_ttm": "snap_pe", "pb": "snap_pb", "total_mv": "snap_mv", "float_mv": "snap_fmv"}
    )
    merged = db.merge(snap_cols, on="symbol", how="inner").merge(ref, on="symbol", how="left")
    # ratio = 当日前复权close / 基准日前复权close (反映真实价格变动, 基一致)
    ratio = (merged["close"] / merged["ref_close"]).where(merged["ref_close"] > 0)
    # pe/pb/mv 均随价格线性变化 (TTM 盈利/净资产/股本近似不变)
    merged["pe_fill"] = merged["snap_pe"] * ratio
    merged["pb_fill"] = merged["snap_pb"] * ratio
    merged["mv_fill"] = merged["snap_mv"] * ratio
    merged["fmv_fill"] = merged["snap_fmv"] * ratio
    # 重置后最新月均 NULL, 全部待填; 仅丢弃四个字段全空的行 (基准缺失)
    mask = merged[["pe_fill", "pb_fill", "mv_fill", "fmv_fill"]].notna().any(axis=1)
    fills = merged[mask][["symbol", "trade_date", "pe_fill", "pb_fill", "mv_fill", "fmv_fill"]].copy()
    print(f"   待回填 (基一致缩放): {len(fills):,} 行")

    if dry_run or fills.empty:
        if dry_run:
            print(f"   [DRY RUN] 将回填 {len(fills):,} 行 pe/pb/total_mv/float_mv")
        return 0

    print(f"\n3️⃣  写入临时表 tmp_em_fill ({len(fills):,} 行) 并 UPDATE...")
    t0 = time.time()
    fills.columns = ["symbol", "trade_date", "pe_ttm", "pb", "total_mv", "float_mv"]
    fills["trade_date"] = pd.to_datetime(fills["trade_date"]).dt.date
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tmp_em_fill"))
    fills.to_sql("tmp_em_fill", engine, if_exists="replace", index=False, method="multi", chunksize=5000)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS tmp_em_sym_dt ON tmp_em_fill(symbol, trade_date)"))
        result = conn.execute(text("""
            UPDATE stock_daily_latest s
            SET pe_ttm   = COALESCE(NULLIF(s.pe_ttm, 0),   t.pe_ttm,   s.pe_ttm),
                pb       = COALESCE(NULLIF(s.pb, 0),       t.pb,       s.pb),
                total_mv = COALESCE(NULLIF(s.total_mv, 0), t.total_mv, s.total_mv),
                float_mv = COALESCE(NULLIF(s.float_mv, 0), t.float_mv, s.float_mv)
            FROM tmp_em_fill t
            WHERE s.symbol = t.symbol AND s.trade_date = t.trade_date
        """))
        updated = result.rowcount
        conn.execute(text("DROP TABLE IF EXISTS tmp_em_fill"))
    print(f"   ✅ 阶段2完成: {updated:,} 行已更新 ({time.time()-t0:.1f}s)")
    return updated


def phase_forwardfill(engine, dry_run: bool = False) -> int:
    """阶段3: 用 DB 自身每只股票最近非空值前向填充剩余缺口 (主要补 roe 与 Eastmoney 未覆盖的符号)."""
    print("\n" + "=" * 70)
    print("  阶段3: 前向填充剩余缺口 (DB 最近非空值)")
    print("=" * 70)

    if dry_run:
        print("   [DRY RUN] 将对 pe_ttm/pb/roe/total_mv/float_mv 做前向填充")
        return 0

    cols = ["pe_ttm", "pb", "roe", "total_mv", "float_mv"]
    total_updated = 0
    t0 = time.time()
    with engine.begin() as conn:
        for col in cols:
            result = conn.execute(text(f"""
                UPDATE stock_daily_latest t
                SET {col} = src.{col}
                FROM (
                    SELECT DISTINCT ON (symbol) symbol, trade_date, {col}
                    FROM stock_daily_latest
                    WHERE {col} IS NOT NULL AND {col} > 0
                    ORDER BY symbol, trade_date DESC
                ) src
                WHERE t.symbol = src.symbol
                  AND (t.{col} IS NULL OR t.{col} = 0)
            """))
            total_updated += result.rowcount
            print(f"   ✅ {col:12s}: {result.rowcount:,} 行前向填充")
    print(f"   阶段3完成: 共 {total_updated:,} 行 ({time.time()-t0:.1f}s)")
    return total_updated


def main():
    parser = argparse.ArgumentParser(description="回填 stock_daily_latest 基本面数据 (parquet + Eastmoney + 前向填充)")
    parser.add_argument("--diagnose", action="store_true", help="仅诊断")
    parser.add_argument("--phase-parquet", action="store_true", help="阶段1: parquet 批量回填")
    parser.add_argument("--phase-em", action="store_true", help="阶段2: Eastmoney 最新月")
    parser.add_argument("--phase-ff", action="store_true", help="阶段3: 前向填充剩余缺口 (roe 等)")
    parser.add_argument("--all", action="store_true", help="三阶段全跑")
    parser.add_argument("--dry-run", action="store_true", help="试运行")
    args = parser.parse_args()

    engine = _get_engine()
    diagnose(engine)

    if args.diagnose:
        return
    if not any([args.phase_parquet, args.phase_em, args.phase_ff, args.all]):
        return

    dry = args.dry_run
    if args.all or args.phase_parquet:
        phase_parquet(engine, dry_run=dry)
    if args.all or args.phase_em:
        phase_eastmoney(engine, dry_run=dry)
    if args.all or args.phase_ff:
        phase_forwardfill(engine, dry_run=dry)

    if not dry:
        print("\n" + "=" * 70)
        print("  回填后验证")
        print("=" * 70)
        diagnose(engine)


if __name__ == "__main__":
    main()
