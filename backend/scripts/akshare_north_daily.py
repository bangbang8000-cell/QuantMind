#!/usr/bin/env python3
"""akshare 北向资金日频历史 → QuantDB 重建脚本。

逐股票调用 akshare `stock_hsgt_individual_em`，拉取 2017-03-16 ~ 2024-08-16
的日频北向持股数据，按股票落盘 parquet。2024-08-19 后北向个股明细改为
季度披露，日频止于此，与 data-AH（2025-01 起）互补。

股票池：来自 instrument_detail.parquet 的 BelongHSGT=1 标的（约 3515 只）。

落盘格式:
  {quantdb}/2_base_sector/hsgt_north/daily_freq/{PREFIX_CODE}.parquet
  股票代码使用前缀格式（SH600519 / SZ000001），与 quantdb 日线一致。

用法:
  python backend/scripts/akshare_north_daily.py                    # 全量
  python backend/scripts/akshare_north_daily.py --symbols 600519,000001
  python backend/scripts/akshare_north_daily.py --symbols 600519 --concurrent 2
  python backend/scripts/akshare_north_daily.py --limit 10
  python backend/scripts/akshare_north_daily.py --dry-run          # 仅预览
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
log = logging.getLogger("akshare_north_daily")

QUANTDB_DATA_DIR = Path(
    os.getenv("QM_QUANTDB_DATA_DIR", str(PROJECT_ROOT / "data" / "quantdb"))
)
REL_DIR = "2_base_sector/hsgt_north/daily_freq"
DEFAULT_THREADS = 3
RETRY = 3

# 输出列（akshare stock_hsgt_individual_em → 标准英文）
OUT_COLS = [
    "stock_code", "stock_name", "query_date", "close", "change_pct",
    "holding_quantity", "holding_value", "holding_pct",
    "increase_quantity", "increase_amount", "value_change",
]


def _quantdb_root() -> Path:
    env_val = os.getenv("QM_QUANTDB_DATA_DIR", "").strip()
    if env_val:
        p = Path(env_val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/data/quantdb").is_dir() and any(Path("/data/quantdb").iterdir()):
        return Path("/data/quantdb")
    QUANTDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return QUANTDB_DATA_DIR


def _target_dir() -> Path:
    d = _quantdb_root() / REL_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hsgt_stock_list() -> list[dict]:
    """从 instrument_detail 读取 BelongHSGT=1 的标的列表。

    Returns:
        [{code6, symbol_prefix, name}]，如 {"code6": "600519", "symbol_prefix": "SH600519"}
    """
    inst_dir = _quantdb_root() / "2_base_sector" / "instrument_detail"
    candidates = [
        inst_dir / "instrument_list.parquet",
        inst_dir / "instrument_detail.parquet",
        inst_dir / "instrument.parquet",
    ]
    df = None
    for f in candidates:
        if f.is_file():
            try:
                df = pd.read_parquet(f)
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("读取 %s 失败: %s", f, exc)
    if df is None or df.empty:
        raise FileNotFoundError(
            f"instrument_detail.parquet 不存在: {inst_dir}（先跑 quantdb_daily_sync）"
        )

    # BelongHSGT 可能是 int 1 或 str '1'
    hsgt = df[df["BelongHSGT"].astype(str).isin(["1", "1.0"])]
    if hsgt.empty:
        raise RuntimeError("instrument_detail 无 BelongHSGT=1 标的")

    out = []
    for _, row in hsgt.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        if not symbol:
            continue
        # Symbol 格式：600519.SH 或 000001.SZ（后缀）
        if "." in symbol:
            code6, market = symbol.split(".")[:2]
        else:
            code6, market = symbol, _guess_market(symbol)
        code6 = code6.zfill(6)
        prefix = f"{market.upper()}{code6}"
        out.append({
            "code6": code6,
            "symbol_prefix": prefix,
            "name": str(row.get("Name", row.get("name", row.get("名称", "")))).strip(),
        })
    return out


def _guess_market(code6: str) -> str:
    code6 = code6.zfill(6)
    if code6.startswith(("6", "9")):
        return "SH"
    if code6.startswith(("0", "3", "2")):
        return "SZ"
    return "SH"


def _normalise(df: pd.DataFrame, info: dict) -> pd.DataFrame | None:
    """akshare 输出 → 标准列。"""
    if df is None or df.empty:
        return None
    df = df.copy()
    rename = {
        "持股日期": "query_date",
        "当日收盘价": "close",
        "当日涨跌幅": "change_pct",
        "持股数量": "holding_quantity",
        "持股市值": "holding_value",
        "持股数量占A股百分比": "holding_pct",
        "今日增持股数": "increase_quantity",
        "今日增持资金": "increase_amount",
        "今日持股市值变化": "value_change",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "query_date" not in df.columns or "holding_quantity" not in df.columns:
        return None

    df["query_date"] = pd.to_datetime(df["query_date"], errors="coerce")
    df = df.dropna(subset=["query_date"])
    df["query_date"] = df["query_date"].dt.date

    df["stock_code"] = info["symbol_prefix"]
    df["stock_name"] = info["name"]
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")

    # 百分比 → 比例（东财接口的涨跌幅/持股占比是百分数值，如 0.96 → 0.96%）
    for c in ("close", "change_pct", "holding_value", "holding_pct", "increase_amount", "value_change"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in ("increase_quantity",):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")

    # 固定列顺序，缺失列补默认
    for c in OUT_COLS:
        if c not in df.columns:
            df[c] = 0 if c in ("holding_quantity", "increase_quantity") else None

    df = df[OUT_COLS]
    return df.sort_values("query_date").reset_index(drop=True)


def _fetch_one(info: dict, target_dir: Path, dry_run: bool = False) -> str:
    """抓取单只股票北向日频 → 落盘。返回状态：skipped/synced/failed/no_data。"""
    out_path = target_dir / f"{info['symbol_prefix']}.parquet"
    if out_path.exists() and not dry_run:
        return "skipped"

    import akshare as ak

    last_err = None
    for attempt in range(RETRY):
        try:
            raw = ak.stock_hsgt_individual_em(symbol=info["code6"])
            norm = _normalise(raw, info)
            if norm is None or norm.empty:
                return "no_data"
            if dry_run:
                return f"synced({len(norm)}行)"
            norm.to_parquet(out_path, index=False)
            return "synced"
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(2 ** attempt)  # 指数退避 1s/2s/4s

    log.warning("股票 %s 拉取失败: %s", info["symbol_prefix"], last_err)
    # 记录失败，便于 --retry-failed
    with open(target_dir / "_failed.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{info['symbol_prefix']}\t{info['code6']}\t{info['name']}\n")
    return "failed"


def sync(
    *,
    symbols: list[str] | None = None,
    concurrent: int = DEFAULT_THREADS,
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    """拉取北向日频历史到 daily_freq/。"""
    target_dir = _target_dir()

    stock_list = _hsgt_stock_list()
    if symbols:
        wanted = {s.zfill(6) for s in symbols}
        stock_list = [s for s in stock_list if s["code6"] in wanted]
    if limit > 0:
        stock_list = stock_list[:limit]

    log.info(
        "北向标的 %d 只，并发 %d，目标目录 %s（dry_run=%s）",
        len(stock_list), concurrent, target_dir, dry_run,
    )

    if dry_run:
        return {"total": len(stock_list), "dry_run": True, "dir": str(target_dir)}

    stats = {"synced": 0, "skipped": 0, "failed": 0, "no_data": 0}
    failed_list = []

    # 清除旧失败记录
    failed_file = target_dir / "_failed.txt"
    if failed_file.exists():
        failed_file.unlink()

    done = 0
    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = {pool.submit(_fetch_one, info, target_dir, dry_run): info for info in stock_list}
        for fut in as_completed(futures):
            info = futures[fut]
            done += 1
            try:
                status = fut.result()
            except Exception as exc:  # noqa: BLE001
                status = "failed"
                log.error("股票 %s 异常: %s", info["symbol_prefix"], exc)
            stats[status] = stats.get(status, 0) + 1
            if status == "failed":
                failed_list.append(info["symbol_prefix"])
            if done % 100 == 0 or done == len(stock_list):
                log.info(
                    "进度 %d/%d  synced=%d skipped=%d failed=%d no_data=%d",
                    done, len(stock_list), stats["synced"], stats["skipped"],
                    stats["failed"], stats["no_data"],
                )
            time.sleep(0.1)  # 轻微限速

    return {
        "total": len(stock_list),
        "synced": stats["synced"],
        "skipped": stats["skipped"],
        "failed": stats["failed"],
        "no_data": stats["no_data"],
        "failed_symbols": failed_list[:50],
        "dir": str(target_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="akshare 北向资金日频历史 → QuantDB")
    parser.add_argument("--symbols", default=None, help="指定股票代码，逗号分隔（6位）")
    parser.add_argument("--concurrent", type=int, default=DEFAULT_THREADS, help="并发线程数")
    parser.add_argument("--limit", type=int, default=0, help="最多拉多少只（0=全部，用于验证）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不抓取")
    args = parser.parse_args()

    try:
        result = sync(
            symbols=args.symbols.split(",") if args.symbols else None,
            concurrent=args.concurrent,
            dry_run=args.dry_run,
            limit=args.limit,
        )
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("同步失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
