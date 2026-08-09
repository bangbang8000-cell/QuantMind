#!/usr/bin/env python3
"""北向资金 data-AH 原始数据导入 → QuantDB 季度快照。

data-AH 目录是 HKEX 北向爬虫早期按股票分目录保存的原始 CSV（目录名=中文
股票名，文件名含 HKEX 代号），覆盖 2025-01-07~2025-12-01。持仓量只在季度末
变化，可提取 2025Q1~Q4 四个季度末快照，填补 HKEX 12 个月窗口之外的历史季度。

导入逻辑：
  1. 逐 CSV 按日期排序，持仓量变化点即季度快照边界
  2. 变化点日期归属季度（披露日所在季度）→ report_date = 季度末
  3. 目录名（中文）匹配 instrument_detail 得标准 symbol
  4. 落盘 {quantdb}/2_base_sector/hsgt_north/quarter=YYYYQN/data.parquet
     与现有 2026Q2 快照同 schema

用法:
  python backend/scripts/quantdb_north_import_dataah.py --dir /media/.../data-AH
  python backend/scripts/quantdb_north_import_dataah.py --dir ... --quarter 2025Q2
  python backend/scripts/quantdb_north_import_dataah.py --dir ... --dry-run
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quantdb_north_import_dataah")

QUANTDB_DATA_DIR = Path(
    os.getenv("QM_QUANTDB_DATA_DIR", str(PROJECT_ROOT / "data" / "quantdb"))
)
REL_DIR = "2_base_sector/hsgt_north"


def _quantdb_root() -> Path:
    env_val = os.getenv("QM_QUANTDB_DATA_DIR", "").strip()
    if env_val:
        return Path(env_val)
    if Path("/data/quantdb").is_dir() and any(Path("/data/quantdb").iterdir()):
        return Path("/data/quantdb")
    QUANTDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTDB_DATA_DIR


def _quarter_end(quarter: str) -> date:
    mt = __import__("re").match(r"(\d{4})Q([1-4])", quarter)
    if not mt:
        raise ValueError(f"无效季度: {quarter}")
    year, q = int(mt.group(1)), int(mt.group(2))
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[q]


def _quarter_of(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _market_of(code6: str) -> str:
    if code6.startswith(("6", "9")):
        return "SH"
    if code6.startswith(("0", "3", "2")):
        return "SZ"
    return "SH"


def _parse_csv(path: Path) -> pd.DataFrame | None:
    """读单个 data-AH CSV → (dt, holding_quantity, holding_percentage)。"""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        log.debug("读取 %s 失败: %s", path, exc)
        return None
    if df.empty:
        return None
    df.columns = [str(c).strip() for c in df.columns]
    date_col = next((c for c in df.columns if "日期" in c), None)
    qty_col = next((c for c in df.columns if "持股量" in c), None)
    pct_col = next((c for c in df.columns if "百分比" in c), None)
    if not date_col or not qty_col:
        return None
    out = pd.DataFrame({
        "dt": pd.to_datetime(df[date_col], errors="coerce"),
        "holding_quantity": pd.to_numeric(df[qty_col], errors="coerce"),
    })
    if pct_col:
        out["holding_percentage"] = (
            df[pct_col].astype(str).str.replace("%", "", regex=False).str.strip()
        )
        out["holding_percentage"] = pd.to_numeric(out["holding_percentage"], errors="coerce").fillna(0.0) / 100.0
    else:
        out["holding_percentage"] = 0.0
    out = out.dropna(subset=["dt", "holding_quantity"])
    return out.sort_values("dt").reset_index(drop=True)


def _extract_quarters(df: pd.DataFrame) -> list[tuple[str, date, float, float]]:
    """持仓量变化点 → [(quarter, report_date, qty, pct)]。"""
    out = []
    prev_qty = None
    for _, r in df.iterrows():
        qty = float(r["holding_quantity"])
        if qty != prev_qty:
            d = r["dt"].date()
            out.append((_quarter_of(d), _quarter_end(_quarter_of(d)), qty, float(r["holding_percentage"])))
            prev_qty = qty
    return out


def import_dataah(*, source_dir: str, quarters: list[str] | None = None,
                  dry_run: bool = False) -> dict:
    """导入 data-AH 目录 → 季度快照。

    已匹配 instrument_detail 的股票用标准 symbol；未匹配的（ST/新股/异体字/
    英文名）也导入，symbol 用文件名里的 HKEX 代号（如 77159），并加
    `unmatched=1` 标记，便于后续用其他源补齐。ETF/指数类跳过。
    """
    from backend.scripts.quantdb_north_sync import _load_symbol_map, _norm_name, _is_etf_or_index

    src = Path(source_dir)
    if not src.is_dir():
        return {"status": "skipped", "reason": f"{src} 不存在"}

    symbol_map = _load_symbol_map()
    log.info("名称映射: %d 条", len(symbol_map))

    csvs = sorted(src.glob("*/*.csv"))
    if not csvs:
        return {"status": "skipped", "reason": f"{src} 下无 CSV"}
    log.info("data-AH CSV: %d 个", len(csvs))

    # 按季度收集 (symbol, stock_name, qty, pct, query_date, report_date, market, unmatched)
    quarter_rows: dict[str, list] = {}
    stats = {"parsed": 0, "matched": 0, "unmatched": 0, "etf": 0}
    unmatched_samples = []

    for path in csvs:
        stock_name = path.parent.name.strip()
        df = _parse_csv(path)
        if df is None or df.empty:
            continue
        stats["parsed"] += 1

        # 目录名 → symbol（名称匹配，跳过 ETF/指数）
        if _is_etf_or_index(stock_name):
            stats["etf"] += 1
            continue

        n = _norm_name(stock_name)
        symbol = symbol_map.get(n)
        unmatched = 0
        if not symbol:
            # 未匹配：从文件名提取 HKEX 代号作 symbol（如 77159 / 90967）
            from backend.scripts.quantdb_north_sync import _EMBEDDED_CODE
            fname = path.name
            code = None
            m = re.search(r"[+_]([A-Z]?)(\d{5})\.csv$", fname)
            if m:
                code = m.group(2)
            else:
                emb = _EMBEDDED_CODE.search(stock_name)
                if emb:
                    code = emb.group(1)
            if code:
                symbol = f"{code}.HK"
                unmatched = 1
                stats["unmatched"] += 1
                if len(unmatched_samples) < 30:
                    unmatched_samples.append(stock_name)
            else:
                stats["etf"] += 1  # 无代号且名称无内嵌代码，归入无法处理
                continue
        else:
            stats["matched"] += 1

        market = _market_of(symbol.split(".")[0]) if "." in symbol and not unmatched else "HK"
        for quarter, report_date, qty, pct in _extract_quarters(df):
            if quarters and quarter not in quarters:
                continue
            if not report_date:
                continue
            query_date = report_date
            quarter_rows.setdefault(quarter, []).append(
                (symbol, stock_name, qty, pct, query_date, report_date, market, unmatched)
            )

    if not quarter_rows:
        return {"status": "ok", "quarters": {}, "stats": stats}

    written = []
    for quarter, rows in quarter_rows.items():
        qdf = pd.DataFrame(rows, columns=[
            "symbol", "stock_name", "holding_quantity", "holding_percentage",
            "query_date", "report_date", "market", "unmatched",
        ])
        # 同 symbol 同季度只保留一条
        qdf = qdf.drop_duplicates(subset=["symbol"], keep="first")
        target_dir = _quantdb_root() / REL_DIR / f"quarter={quarter}"
        if dry_run:
            written.append({"quarter": quarter, "rows": len(qdf), "action": "dry_run"})
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        out = target_dir / "data.parquet"
        # 与已有同季度快照合并
        if out.exists():
            old = pd.read_parquet(out)
            qdf = pd.concat([old, qdf], ignore_index=True).drop_duplicates(subset=["symbol"], keep="first")
        qdf.to_parquet(out, index=False)
        written.append({"quarter": quarter, "rows": len(qdf), "action": "merged" if out.exists() else "written"})
        log.info("[%s] %s: %d 只", quarter, "合并" if written[-1]["action"] == "merged" else "写入", len(qdf))

    return {
        "status": "ok" if not dry_run else "dry_run",
        "stats": stats,
        "unmatched_samples": unmatched_samples,
        "quarters": written,
        "target_dir": str(_quantdb_root() / REL_DIR),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="北向 data-AH → QuantDB 季度快照导入")
    parser.add_argument("--dir", required=True, help="data-AH 目录路径")
    parser.add_argument("--quarter", default=None, help="只导入指定季度，逗号分隔 (2025Q1)")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    quarters = [q.strip() for q in args.quarter.split(",") if q.strip()] if args.quarter else None
    try:
        result = import_dataah(source_dir=args.dir, quarters=quarters, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("导入失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
