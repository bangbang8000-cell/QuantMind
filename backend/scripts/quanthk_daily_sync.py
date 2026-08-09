#!/usr/bin/env python3
"""港股数据同步入口 — 按勾选数据集分发到对应同步脚本。

支持的数据集（与后台 catalog 对应）:
  daily_forward / index_daily / valuation / sector / f10 / income / balance /
  cashflow / dividend / splits / 4_analyst 系列   → 雅虎源（global_market_sync）
  akshare_valuation / akshare_financial / akshare_profile → akshare 源
  index_daily                                        → akshare 指数（akshare_index_sync）

用法:
  python backend/scripts/quanthk_daily_sync.py --days 5
  python backend/scripts/quanthk_daily_sync.py --datasets daily_forward,index_daily --days 5
"""

from __future__ import annotations

import sys
from typing import Any

from backend.scripts.global_market_sync import run as _yahoo_run

# akshare 港股基本面数据集 → akshare_hk_fundamental 的 field
AKSHARE_HK_FIELDS = {
    "akshare_valuation": "valuation",
    "akshare_financial": "financial",
    "akshare_profile": "profile",
    "dividend": "dividend",
}

# 雅虎数据段（global_market_sync 处理）
_YAHOO_DATASETS = {
    "daily_forward", "index_daily", "valuation", "sector", "f10",
    "income", "balance", "cashflow", "splits",
    "recommendations", "upgrades_downgrades", "earnings_history",
    "earnings_dates", "earnings_estimate", "revenue_estimate",
    "growth_estimates", "analyst_price_targets", "major_holders",
    "mutual_fund_holders", "calendar", "insider_transactions", "options_chain",
}


def run(*, days: int = 5, symbols: str | None = None, datasets: list[str] | None = None,
        fast: bool = False, **kwargs: Any) -> dict:
    """同步港股数据。datasets 为勾选的数据集名；None 时全量同步雅虎数据。

    按数据集分发到对应数据源脚本。hsgt_south（南向资金/港股通）走独立
    爬虫同步脚本，落盘 {quanthk}/2_base_sector/hsgt_south。
    """
    if not datasets:
        return _yahoo_run("HK", days=days, symbols=symbols, fast=fast)

    result: dict = {"market": "HK", "days": days, "datasets": datasets}

    # 南向资金（港股通）— 独立爬虫，按数据源勾选控制
    if "hsgt_south" in datasets:
        try:
            from backend.shared.data_source_config import is_source_enabled

            enabled = is_source_enabled("HK", "hsgt_south")
        except Exception:  # noqa: BLE001
            enabled = True
        if enabled:
            from backend.scripts.quanthk_south_sync import sync as south_sync

            try:
                result["sources"] = {"hsgt_south": south_sync(days=days)}
            except Exception as exc:  # noqa: BLE001
                result["sources"] = {"hsgt_south": {"status": "error", "error": str(exc)}}
        else:
            result["sources"] = {"hsgt_south": {"status": "skipped", "reason": "未勾选南向资金"}}

    yahoo_ds = [d for d in datasets if d in _YAHOO_DATASETS]
    if yahoo_ds:
        result["yahoo"] = _yahoo_run("HK", days=days, symbols=symbols, fast=fast)

    # akshare 港股基本面（估值/财务/资料/分红）
    akshare_fields = []
    for ds in datasets:
        if ds in AKSHARE_HK_FIELDS:
            akshare_fields.append(AKSHARE_HK_FIELDS[ds])
    if akshare_fields:
        from backend.scripts.akshare_hk_fundamental import sync as ak_fund_sync

        result["akshare_fundamental"] = {}
        for field in akshare_fields:
            try:
                result["akshare_fundamental"][field] = ak_fund_sync(field)
            except Exception as exc:  # noqa: BLE001
                result["akshare_fundamental"][field] = {"error": str(exc)}

    # akshare 指数（index_daily）
    if "index_daily" in datasets:
        from backend.scripts.akshare_index_sync import sync as ak_index_sync

        try:
            result["akshare_index"] = ak_index_sync("HK")
        except Exception as exc:  # noqa: BLE001
            result["akshare_index"] = {"error": str(exc)}

    # 港股 CCASS 机构持仓（ccass_top50）
    if "ccass_top50" in datasets:
        from backend.scripts.quanthk_ccass_sync import run as ccass_sync

        try:
            result["ccass"] = ccass_sync(days=days)
        except Exception as exc:  # noqa: BLE001
            result["ccass"] = {"error": str(exc)}

    return result


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="港股数据同步")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--datasets", default=None, help="逗号分隔数据集名")
    args, _ = parser.parse_known_args()

    ds = [d.strip() for d in args.datasets.split(",") if d.strip()] if args.datasets else None
    result = run(days=args.days, symbols=args.symbols, datasets=ds)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
