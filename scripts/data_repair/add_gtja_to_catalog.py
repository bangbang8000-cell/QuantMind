"""把 16 个 GTJA 因子加入 catalog，全部 default_selected=true。"""
import json
from pathlib import Path

CATALOG = Path("/app/config/features/model_training_feature_catalog_v1.json")

GTJA_FEATURES = [
    # 正向 6 (IC > 0)
    ("gtja_alpha_016", "GTJA Alpha16: -TSMAX(RANK(CORR(rank(vol),rank(vwap),5)),5)", "正向"),
    ("gtja_alpha_032", "GTJA Alpha32: -SUM(RANK(CORR(rank(high),rank(vol),3)),3)", "正向"),
    ("gtja_alpha_062", "GTJA Alpha62: -CORR(high, rank(vol), 5)", "正向"),
    ("gtja_alpha_083", "GTJA Alpha83: -RANK(COV(rank(high), rank(vol), 5))", "正向 - 最强"),
    ("gtja_alpha_090", "GTJA Alpha90: -RANK(CORR(rank(vwap), rank(vol), 5))", "正向"),
    ("gtja_alpha_099", "GTJA Alpha99: -RANK(COV(rank(close), rank(vol), 5))", "正向"),
    # 反向 6 (IC < 0)
    ("gtja_alpha_036", "GTJA Alpha36: RANK(SUM(CORR(rank(vol),rank(vwap),6),2))", "反向"),
    ("gtja_alpha_070", "GTJA Alpha70: STD(AMOUNT, 6)", "反向/分行情"),
    ("gtja_alpha_074", "GTJA Alpha74: RANK(CORR(SUM(price,20),SUM(MA(vol,40),20),7))+...", "反向"),
    ("gtja_alpha_150", "GTJA Alpha150: (close+high+low)/3 * volume", "反向/分行情"),
    ("gtja_alpha_176", "GTJA Alpha176: CORR(rank(KDJ_RSV_12), rank(vol), 6)", "反向"),
    ("gtja_alpha_179", "GTJA Alpha179: RANK(CORR(vwap,vol,4))*RANK(CORR(rank(low),rank(MA(vol,50)),12))", "反向"),
    # 分行情 4 (70/150 已在反向列表)
    ("gtja_alpha_042", "GTJA Alpha42: -RANK(STD(high,10)) * CORR(high,vol,10)", "分行情（牛市增强）"),
    ("gtja_alpha_095", "GTJA Alpha95: STD(AMOUNT, 20)", "分行情"),
    ("gtja_alpha_158", "GTJA Alpha158: (high-low)/close (基于 EMA(close,15) 推导)", "分行情"),
    ("gtja_alpha_159", "GTJA Alpha159: 多周期 RSV 加权（牛熊反转因子）", "分行情（牛熊 flip）"),
]


def main():
    with open(CATALOG) as f:
        cat = json.load(f)

    # 看是否已有 GTJA 分类
    has_gtja_cat = any(c["id"] == "gtja" for c in cat["categories"])
    if has_gtja_cat:
        # 先移除旧的，重建
        cat["categories"] = [c for c in cat["categories"] if c["id"] != "gtja"]

    # 新增分类
    next_order = max((c.get("order", 0) for c in cat["categories"]), default=0) + 1
    features = []
    for i, (key, desc, kind) in enumerate(GTJA_FEATURES):
        features.append({
            "feature_id": f"feat_gtja_{i:03d}",
            "key": key,
            "description": desc,
            "formula": desc,
            "source": "GTJA Alpha191 (国泰君安) — feature_snapshots/model_features_*.parquet",
            "enabled": True,
            "markets": ["CN"],
            "order_no": i + 1,
            "default_selected": True,
            "coverage_ratio": 0.95,  # 抽样平均
            "tag": kind,
        })

    gtja_cat = {
        "id": "gtja",
        "name": "GTJA Alpha191 (价量因子)",
        "order": next_order,
        "feature_count": len(features),
        "features": features,
    }
    cat["categories"].append(gtja_cat)
    cat["feature_count"] = sum(c["feature_count"] for c in cat["categories"])

    # 更新 metadata
    cat["metadata"]["default_selected_count"] = sum(
        1 for c in cat["categories"] for f in c["features"]
        if f.get("default_selected")
    )
    cat["metadata"]["gtja_added"] = "2026-06-25"
    cat["metadata"]["gtja_count"] = len(features)

    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=2)

    print(f"✅ catalog 更新")
    print(f"   总特征: {cat['feature_count']}")
    print(f"   默认勾选: {cat['metadata']['default_selected_count']}")
    print(f"   GTJA 分类: {len(features)} 个全部 default_selected=true")


if __name__ == "__main__":
    main()
