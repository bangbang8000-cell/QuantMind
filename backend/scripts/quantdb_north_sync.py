#!/usr/bin/env python3
"""北向资金（沪深港通）→ QuantDB 季度同步脚本。

市场规则（2024-08-19 起）：沪股通/深股通北向个股持仓改为季度披露，
每季度第 5 个沪深股通交易日公布上季度末数据。本脚本按季度末日期抓取
HKEX 持仓，落盘为季度快照分区。

落盘格式:
  {quantdb}/2_base_sector/hsgt_north/quarter=YYYYQN/data.parquet
  例: 2026Q2 = 2026-06-30 季度末持仓

列（清洗后）:
  symbol(600036.SH), stock_name, holding_quantity, holding_percentage,
  query_date(实际抓取日), report_date(季度末), market(SH/SZ)

用法:
  python backend/scripts/quantdb_north_sync.py --quarter 2026Q2
  python backend/scripts/quantdb_north_sync.py --latest          # 最近季度
  python backend/scripts/quantdb_north_sync.py --quarters 2025Q1,2025Q2,2025Q3
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import re
import sys
import unicodedata
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
log = logging.getLogger("quantdb_north_sync")

QUANTDB_DATA_DIR = Path(
    os.getenv("QM_QUANTDB_DATA_DIR", str(PROJECT_ROOT / "data" / "quantdb"))
)
REL_DIR = "2_base_sector/hsgt_north"

CRAWLER_PATH = str(Path(__file__).parent / "hsgt_north_crawler.py")

_crawler_mod = None


def _load_crawler():
    global _crawler_mod
    if _crawler_mod is not None:
        return _crawler_mod
    spec = importlib.util.spec_from_file_location("hsgt_north", CRAWLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _crawler_mod = mod
    return mod


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


# ---------------------------------------------------------------------------
# 季度/披露日计算
# ---------------------------------------------------------------------------
def _quarter_of(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def _quarter_end(quarter: str) -> date:
    """季度末日期: 2026Q2 -> 2026-06-30。"""
    mt = re.match(r"(\d{4})Q([1-4])", quarter)
    if not mt:
        raise ValueError(f"无效季度: {quarter}，应为 YYYYQN")
    year, q = int(mt.group(1)), int(mt.group(2))
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[q]


def _nth_cn_trading_day_after(anchor: date, n: int) -> date:
    """anchor 日期后第 n 个沪深股通交易日（含 anchor 当日）。

    季度末数据在第 5 个沪深股通交易日公布，即 quarter_end 起算
    第 5 个交易日。港股通与 A 股交易日历在绝大多数日子一致。
    """
    cal = _load_crawler().HKEXTradingCalendar
    d = anchor
    count = 0
    while count < n:
        if cal.is_trading_day(d.strftime("%Y-%m-%d")):
            count += 1
        d += timedelta(days=1)
    return d - timedelta(days=1)


def _disclosure_days(quarters: list[str]) -> list[tuple[str, date, date]]:
    """返回 [(quarter, report_date=季度末, query_date=披露日)]。

    披露日 = 季度末后第 5 个沪深股通交易日。
    """
    out = []
    for q in quarters:
        report = _quarter_end(q)
        query = _nth_cn_trading_day_after(report, 5)
        out.append((q, report, query))
    return out


def _recent_quarters(n: int = 2) -> list[str]:
    """最近 n 个已结束的季度（按披露日已到判断）。"""
    today = date.today()
    out = []
    q = _quarter_of(today)
    # 若当前季度尚未到披露日，从上一季度开始
    report = _quarter_end(q)
    if today < _nth_cn_trading_day_after(report, 5):
        q = f"{report.year}Q{(report.month - 1) // 3}" if report.month == 3 else f"{report.year}Q{(report.month - 1) // 3}"
        # 上一季度
        if report.month == 3:
            q = f"{report.year - 1}Q4"
        else:
            q = f"{report.year}Q{(report.month - 1) // 3}"
    q_end = _quarter_end(q)
    out.append(q)
    while len(out) < n:
        if q_end.month == 3:
            q = f"{q_end.year - 1}Q4"
        else:
            q = f"{q_end.year}Q{(q_end.month - 1) // 3}"
        q_end = _quarter_end(q)
        out.append(q)
    return list(reversed(out))


# ---------------------------------------------------------------------------
# 名称 → symbol 映射
# ---------------------------------------------------------------------------
def _norm_name(name: object) -> str:
    """归一化股票名称用于匹配：去空格/下划线/全角、NFKC 半角化、去尾部 -U/-W/-UW 后缀。"""
    s = str(name).strip().replace(" ", "").replace("　", "").replace("_", "")
    s = unicodedata.normalize("NFKC", s)  # 全角Ａ/空格 → 半角 A/空格
    s = re.sub(r"-[UWCN]+$", "", s)
    return s


def _load_symbol_map(use_akshare: bool = True) -> dict[str, str]:
    """构建 名称→标准symbol 映射。

    优先本地 instrument_detail（快），缺失/失败时用 akshare 全 A 股
    代码-名称表补充（覆盖新股、ST、名称差异）。
    """
    symbol_map: dict[str, str] = {}
    inst_dir = _quantdb_root() / "2_base_sector" / "instrument_detail"
    df = None
    for f in (inst_dir / "instrument_detail.parquet", inst_dir / "instrument.parquet"):
        if f.is_file():
            try:
                df = pd.read_parquet(f)
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("读取 %s 失败: %s", f, exc)

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or "." not in symbol:
                continue
            n = _norm_name(row.get("Name", ""))
            if n:
                symbol_map.setdefault(n, symbol)

    if use_akshare:
        try:
            import akshare as ak

            ak_df = ak.stock_info_a_code_name()
            for _, row in ak_df.iterrows():
                code6 = str(row.get("code", "")).strip()
                name = row.get("name", "")
                if not code6 or not name:
                    continue
                n = _norm_name(name)
                if n and n not in symbol_map:
                    symbol_map[n] = f"{code6}.{_market_of(code6)}"
            log.info("名称映射: instrument=%d + akshare=%d", len(symbol_map), len(ak_df))
        except Exception as exc:  # noqa: BLE001
            log.warning("akshare 代码表加载失败（仅用本地映射）: %s", exc)

    return symbol_map


_EMBEDDED_CODE = re.compile(r"#\s*(\d{6})")


def _market_of(code6: str) -> str:
    if code6.startswith(("6", "9")):
        return "SH"
    if code6.startswith(("0", "3", "2")):
        return "SZ"
    return "SH"


def _resolve_symbol(row: pd.Series, symbol_map: dict[str, str]) -> tuple[str | None, str]:
    code = str(row["stock_code"]).strip().zfill(6)
    name = str(row.get("stock_name", "")).strip()
    market = str(row.get("market", "")).strip()

    n = _norm_name(name)
    sym = symbol_map.get(n)
    if sym:
        return sym, "name"
    mt = _EMBEDDED_CODE.search(name)
    if mt:
        code6 = mt.group(1)
        return f"{code6}.{_market_of(code6)}", "embedded"

    # 前缀规则兜底：仅科创板 30→688 100% 可靠（科创板代码统一 688xxx）。
    # HKEX 科创板代号 030001 → 真实 688001（code 已 zfill 6，后 3 位即真实尾码）。
    # 注意：HKEX 的 ETF/指数代号前缀同样是 03，必须先排除，否则 50ETF 会被
    # 误映射成 688xxx 股票代码。
    # 其他 HKEX 市场码（70/72/77/90 等）与 A 股 6 位代码无可逆映射，
    # 猜测会产生错误代码污染数据，故放弃。
    if code.startswith("03") and not _is_etf_or_index(name):
        return f"688{code[3:]}.SH", "prefix"
    return None, "unmatched"


def _is_etf_or_index(name: str) -> bool:
    if not name:
        return False
    pat = (
        r"ETF|LOF|基金|红利|增强|指增|中金|永赢|华宝|富国|华夏|易方达|嘉实|南方|"
        r"博时|广发|招商|国泰|华泰|天弘|建信|工银|银华|汇添富|景顺|鹏华|大成|"
        r"诺安|华安|A50|A500|HS300|ZZ500|科创50|消电50|医疗50|中证|国企|央企|"
        r"证券|银行|医药|军工|半导体|食品|新能源|化工|环保|科技|消费|有色|地产|"
        r"保险|央企改革|央企创新|大数据|计算机|芯片|传媒|国防|消费|红利"
    )
    return bool(re.search(pat, name))


# ---------------------------------------------------------------------------
# 抓取 + 落盘
# ---------------------------------------------------------------------------
def _existing_quarters() -> set[str]:
    d = _quantdb_root() / REL_DIR
    if not d.is_dir():
        return set()
    return {p.name[8:] for p in d.glob("quarter=*")}  # quarter=2026Q2 → 2026Q2


def _normalise(df: pd.DataFrame, query_date: date, market: str) -> pd.DataFrame | None:
    """爬虫输出 → 标准列（HKEX 5 位代号暂保留，稍后统一解析）。"""
    if df is None or df.empty:
        return None
    rename = {}
    for col in df.columns:
        if "股份代号" in col or "股份代码" in col:
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

    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df["holding_quantity"] = pd.to_numeric(df["holding_quantity"], errors="coerce").fillna(0).astype("int64")
    if "holding_percentage" in df.columns:
        df["holding_percentage"] = (
            df["holding_percentage"].astype(str).str.replace("%", "", regex=False).str.strip()
        )
        df["holding_percentage"] = pd.to_numeric(df["holding_percentage"], errors="coerce").fillna(0.0) / 100.0
    df["query_date"] = query_date
    df["market"] = market
    out_cols = ["stock_code", "stock_name", "holding_quantity", "holding_percentage", "query_date", "market"]
    df = df[[c for c in out_cols if c in df.columns]]
    return df.dropna(subset=["stock_code"])


async def _fetch_quarter(mod, report_date: date, query_date: date) -> pd.DataFrame:
    """抓取单个季度末持仓（沪深两个市场），返回未清洗的合并 DataFrame。"""
    hkex_date = query_date.strftime("%Y/%m/%d")
    frames = []
    for market in (mod.Market.SH, mod.Market.SZ):
        async with mod.AsyncBeixiangFetcher(market) as fetcher:
            df = await fetcher.fetch_market_data(hkex_date)
        norm = _normalise(df, query_date, market.name)
        if norm is not None and not norm.empty:
            frames.append(norm)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _clean_and_dedup(df: pd.DataFrame, symbol_map: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """清洗单季度抓取结果：代码映射 + 去重 + 剔除 ETF/未匹配。"""
    resolved = df.apply(lambda r: _resolve_symbol(r, symbol_map), axis=1, result_type="expand")
    df["symbol"] = resolved[0]
    df["_match"] = resolved[1]

    summary = {"total": len(df)}
    for method in ("name", "embedded", "prefix", "unmatched"):
        summary[method] = int((df["_match"] == method).sum())

    unm = df[df["symbol"].isna()]
    etf_mask = unm["stock_name"].map(_is_etf_or_index)
    summary["etf"] = int(etf_mask.sum())
    summary["unmatched_keep"] = int(len(unm) - etf_mask.sum())

    keep = df[df["symbol"].notna()].copy()
    # 同一 symbol 持仓重复 → 保留最早（幂等重抓）
    keep = keep.sort_values("query_date")
    keep = keep.drop_duplicates(subset=["symbol"], keep="first")
    return keep, summary


def _write_quarter(quarter: str, report_date: date, df: pd.DataFrame) -> Path:
    target_dir = _quantdb_root() / REL_DIR / f"quarter={quarter}"
    target_dir.mkdir(parents=True, exist_ok=True)
    df["report_date"] = report_date
    out_cols = ["symbol", "stock_name", "holding_quantity", "holding_percentage", "query_date", "report_date", "market"]
    df = df[out_cols].reset_index(drop=True)
    out = target_dir / "data.parquet"
    df.to_parquet(out, index=False)
    return out


def sync(*, quarters: list[str] | None = None, latest: bool = False, dry_run: bool = False) -> dict:
    """按季度同步北向资金。quarters 指定季度；latest 取最近季度。"""
    mod = _load_crawler()

    if latest:
        quarters = _recent_quarters(1)
    if not quarters:
        raise ValueError("需指定 --quarters 或 --latest")

    existing = _existing_quarters()
    todo = [(q, r, d) for q, r, d in _disclosure_days(quarters) if q not in existing]
    log.info("季度 %s，已有 %s，待抓 %s", quarters, sorted(existing), [q for q, _, _ in todo])

    if dry_run:
        return {
            "quarters": quarters,
            "todo": [{"quarter": q, "report_date": r.isoformat(), "query_date": d.isoformat()} for q, r, d in todo],
            "dry_run": True,
        }

    symbol_map = _load_symbol_map()
    log.info("instrument_detail 名称映射: %d 条", len(symbol_map))

    results = []
    for quarter, report_date, query_date in todo:
        try:
            raw = asyncio.run(_fetch_quarter(mod, report_date, query_date))
            if raw.empty:
                results.append({"quarter": quarter, "status": "no_data", "report_date": report_date.isoformat()})
                continue
            clean, summary = _clean_and_dedup(raw, symbol_map)
            out = _write_quarter(quarter, report_date, clean)
            results.append({
                "quarter": quarter,
                "status": "synced",
                "report_date": report_date.isoformat(),
                "query_date": query_date.isoformat(),
                "rows": len(clean),
                "summary": summary,
                "path": str(out),
            })
            log.info("[%s] %s: %d 只 (name=%d embedded=%d prefix=%d etf=%d)",
                     quarter, report_date, len(clean), summary["name"],
                     summary["embedded"], summary["prefix"], summary["etf"])
        except Exception as exc:  # noqa: BLE001
            results.append({"quarter": quarter, "status": "error", "error": str(exc)})
            log.warning("[%s] 抓取失败: %s", quarter, exc)

    return {"quarters": quarters, "results": results, "target_dir": str(_quantdb_root() / REL_DIR)}


def main() -> int:
    parser = argparse.ArgumentParser(description="北向资金季度同步 → QuantDB")
    parser.add_argument("--quarters", default=None, help="季度列表，逗号分隔 (2026Q2)")
    parser.add_argument("--latest", action="store_true", help="同步最近一个季度")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    quarters = [q.strip() for q in args.quarters.split(",") if q.strip()] if args.quarters else None
    if not quarters and not args.latest:
        parser.error("需指定 --quarters 或 --latest")
    try:
        result = sync(quarters=quarters, latest=args.latest, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("同步失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
