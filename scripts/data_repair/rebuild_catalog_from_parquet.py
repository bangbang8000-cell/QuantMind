"""一次性脚本：基于新版 parquet schema 重建 model_training_feature_catalog_v1.json。

背景：替换了 feature_snapshots 之后，parquet 从 194-197 漂移列变成 152 统一列。
旧 catalog 的 78 列里有 18 列已经不存在，要从 catalog 删；多了 92 列要加进 catalog。

策略：
- 用新 parquet schema 作 truth source，全 152 列加入 catalog
- 按列名前缀（mom_/vol_/liq_/flow_/...）映射到合适分类
- 已有列保留原描述/分类
- 新增列默认 default_selected=false（避免改变 baseline 行为）
- 手工指定 8 个高价值新列设 default_selected=true
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

import pyarrow.parquet as pq


PARQUET = Path("/app/db/feature_snapshots/model_features_2026.parquet")
META = Path("/app/db/feature_snapshots/model_features_2026.metadata.json")
CATALOG = Path("/app/config/features/model_training_feature_catalog_v1.json")


# 按前缀映射到分类 id
PREFIX_TO_CAT: dict[str, tuple[str, str]] = {
    "open": ("ohlcv", "基础行情"),
    "high": ("ohlcv", "基础行情"),
    "low": ("ohlcv", "基础行情"),
    "close": ("ohlcv", "基础行情"),
    "volume": ("ohlcv", "基础行情"),
    "factor": ("ohlcv", "基础行情"),
    "mom_": ("momentum", "动量"),
    "vol_": ("volatility", "波动率"),
    "liq_": ("liquidity", "成交量与流动性"),
    "flow_": ("fund_flow", "资金流"),
    "style_": ("style", "风格因子"),
    "ind_": ("industry", "行业因子"),
    "micro_": ("microstructure", "微观结构"),
    "fund_": ("fundamental", "基本面"),
    "pv_": ("priceflow", "量价关系"),
    "tech_": ("technical", "技术形态"),
    "alpha_": ("alpha", "Alpha因子"),
    "trend_": ("trend", "趋势质量"),
    "prel_": ("priceflow", "量价关系"),
    "kline_": ("technical", "技术形态"),
    "consec": ("momentum", "动量"),
}

# 显示顺序
CAT_ORDER = [
    "ohlcv", "momentum", "volatility", "liquidity", "fund_flow",
    "style", "industry", "microstructure", "fundamental",
    "priceflow", "technical", "alpha", "trend", "other",
]


def categorize(key: str) -> tuple[str, str]:
    for pref, (cid, cname) in PREFIX_TO_CAT.items():
        if key == pref or key.startswith(pref):
            return cid, cname
    return "other", "其它"


def main() -> int:
    pf = pq.ParquetFile(str(PARQUET))
    parquet_cols = [c for c in pf.schema_arrow.names if c not in ("symbol", "trade_date")]
    print(f"parquet 特征列 (排除 symbol/trade_date): {len(parquet_cols)}")

    with open(META, "r", encoding="utf-8") as f:
        meta = json.load(f)
    coverage_map = {k: v.get("coverage_ratio", 0.0) for k, v in meta.get("feature_coverage", {}).items()}

    # 旧 catalog 拿描述
    with open(CATALOG, "r", encoding="utf-8") as f:
        old_cat = json.load(f)
    existing_features: dict[str, dict] = {}
    for c in old_cat.get("categories", []):
        for feat in c.get("features", []):
            existing_features[feat["key"]] = feat

    # 已勾选（旧 default_selected 集合）
    old_default_on = {feat["key"] for c in old_cat.get("categories", [])
                       for feat in c.get("features", []) if feat.get("default_selected")}

    # 构建新分类（按 CAT_ORDER 顺序）
    categories: OrderedDict[str, dict] = OrderedDict()
    for col in parquet_cols:
        cid, cname = categorize(col)
        if cid not in categories:
            categories[cid] = {
                "id": cid,
                "name": cname,
                "order": 0,  # later
                "feature_count": 0,
                "features": [],
            }

        old_feat = existing_features.get(col, {})
        # 新增列默认不勾选（避免改变 baseline）；已有列保留旧 default
        default_on = old_feat.get("default_selected", False) if old_feat else False

        feat = {
            "feature_id": old_feat.get("feature_id") or f"feat_{cid}_{len(categories[cid]['features']):03d}",
            "key": col,
            "description": old_feat.get("description") or f"因子: {col}",
            "formula": old_feat.get("formula") or "",
            "source": old_feat.get("source") or "feature_snapshots/model_features_*.parquet",
            "enabled": True,
            "markets": old_feat.get("markets") or ["CN"],
            "order_no": old_feat.get("order_no") or len(categories[cid]["features"]) + 1,
            "default_selected": default_on,
            "coverage_ratio": round(coverage_map.get(col, 0.0), 4),
        }
        categories[cid]["features"].append(feat)

    # 手工增加 high-value 新列默认勾选（A 股语境下的关键因子）
    must_default_on = {
        "mom_sharpe_20",          # 旧 PRESET 也有，新版仍存在，确保保留
        "liq_amount_ma_5",        # 流动性短期均量
        "liq_volume_ma_5",        # 量能短期
        "style_smb",              # Fama-French Small-Minus-Big
        "style_hml",              # High-Minus-Low (价值)
        "style_mkt_premium",      # 市场溢价
        "style_size_percentile",  # 市值分位
        "flow_qsp",               # 强势盘指标
        "ind_strength_60",        # 行业 60 日强度
        "ind_relative_volume_20", # 行业相对量
    }
    for cat_obj in categories.values():
        for feat in cat_obj["features"]:
            if feat["key"] in must_default_on:
                feat["default_selected"] = True

    # 按 CAT_ORDER 排序
    ordered_cats = []
    for i, cid in enumerate(CAT_ORDER):
        if cid in categories:
            cat = categories[cid]
            cat["order"] = i + 1
            cat["feature_count"] = len(cat["features"])
            ordered_cats.append(cat)
    # 把 CAT_ORDER 没列出的（理论上没有）追加到末尾
    for cid, cat in categories.items():
        if cid not in CAT_ORDER:
            cat["order"] = len(ordered_cats) + 1
            cat["feature_count"] = len(cat["features"])
            ordered_cats.append(cat)

    total_features = sum(c["feature_count"] for c in ordered_cats)
    total_default = sum(1 for c in ordered_cats for f in c["features"] if f.get("default_selected"))

    new_cat = {
        "version": "v1.1",
        "version_name": "QM Feature Set v1.1 (post-parquet-replace 20260625)",
        "description": "基于新 parquet schema (152 列统一 schema, qm_feature_set_v1_20260402) 重建",
        "feature_count": total_features,
        "categories": ordered_cats,
        "source": str(CATALOG),
        "metadata": {
            "default_selected_count": total_default,
            "default_selected_note": "前端默认勾选受 default_selected=true 控制",
            "default_selected_set_version": "v1.2",
            "parquet_schema": meta.get("feature_set_version"),
            "rebuild_date": "2026-06-25",
            "rebuild_reason": "替换为新版 parquet (152 列统一 schema，2016-2026 schema 不漂移)",
            "removed_keys": sorted(set(existing_features) - set(parquet_cols)),
            "added_keys": sorted(set(parquet_cols) - set(existing_features)),
        }
    }

    print(f"\n新 catalog 总特征: {total_features}")
    print(f"默认勾选: {total_default}")
    print(f"\n类别分布:")
    for c in ordered_cats:
        on = sum(1 for f in c["features"] if f.get("default_selected"))
        print(f"  {c['name']:18s} ({c['id']:18s}): {c['feature_count']:3d} 列, default_on {on}")

    # 写文件
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(new_cat, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已写入: {CATALOG}")

    print(f"\n删除的旧 key ({len(new_cat['metadata']['removed_keys'])}):")
    for k in new_cat["metadata"]["removed_keys"]:
        print(f"  - {k}")
    print(f"\n新增 key 数: {len(new_cat['metadata']['added_keys'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
