"""一次性脚本：基于 baseline_56 训练的 SHAP 实证结果，把 catalog 的 default_selected
从 56 个调整为 SHAP top 35（覆盖 96% 重要性）。

实证依据：data/training_jobs/train_baseline_56_v1/shap_summary.csv
执行后效果：默认勾选从 56 → 35，预期 IC 持平，训练速度 +30%
"""
from __future__ import annotations

import json
from pathlib import Path


CATALOG = Path("/app/config/features/model_training_feature_catalog_v1.json")

# SHAP top 35（按重要性降序）
TOP_35_BY_SHAP = [
    # 极强 (top 5, mean_abs_shap > 0.003)
    "liq_turnover_os", "liq_amount", "style_idio_vol_20",
    "ind_strength_20", "mom_kdj_k",
    # 强 (6-10)
    "style_size_percentile", "liq_volume_ratio_5", "vol_upside_20",
    "ind_ret_20d", "vol_parkinson_20",
    # 中强 (11-15)
    "liq_amount_ma_5", "style_bp", "style_beta_20",
    "flow_qsp", "mom_ret_60d",
    # 中 (16-20)
    "style_ep_ttm", "flow_vpin_ma_20", "style_ln_mv_float",
    "vol_downside_20", "ind_relative_volume_20",
    # 中弱 (21-25)
    "liq_volume", "ind_strength_60", "ind_momentum_rank_20",
    "mom_ma_gap_5", "mom_ret_1d",
    # 防御深度 (26-35, 累积到 ~96% 重要性)
    "volume", "mom_ret_20d", "vol_realized_rv", "liq_amihud_20",
    "style_ln_mv_total", "ind_ret_1d", "liq_volume_ma_5",
    "mom_breakout_20d", "mom_rsi_14", "vol_realized_rrv",
]


def main() -> int:
    assert len(TOP_35_BY_SHAP) == 35
    assert len(set(TOP_35_BY_SHAP)) == 35  # 无重复

    with open(CATALOG, "r", encoding="utf-8") as f:
        cat = json.load(f)

    catalog_keys: set[str] = set()
    for c in cat["categories"]:
        for feat in c["features"]:
            catalog_keys.add(feat["key"])

    # 验证所有 top-35 都在 catalog 中
    missing = [k for k in TOP_35_BY_SHAP if k not in catalog_keys]
    if missing:
        print(f"⚠️  以下 top-35 列在 catalog 中找不到: {missing}")
        return 1

    target_set = set(TOP_35_BY_SHAP)

    changed_on = []
    changed_off = []
    for c in cat["categories"]:
        for feat in c["features"]:
            key = feat["key"]
            should_be_on = key in target_set
            was_on = bool(feat.get("default_selected"))
            if should_be_on != was_on:
                feat["default_selected"] = should_be_on
                if should_be_on:
                    changed_on.append(key)
                else:
                    changed_off.append(key)

    total_on = sum(
        1 for c in cat["categories"] for f in c["features"]
        if f.get("default_selected")
    )

    # 更新 metadata
    cat["metadata"]["default_selected_count"] = total_on
    cat["metadata"]["default_selected_set_version"] = "v1.3-shap-top35"
    cat["metadata"]["default_selected_basis"] = (
        "基于 train_baseline_56_v1 跑出的 SHAP 实证结果，"
        "选 top-35（覆盖 96% 累积重要性）。"
        "数据：data/training_jobs/train_baseline_56_v1/shap_summary.csv"
    )

    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=2)

    print(f"\n✅ catalog 更新完成")
    print(f"   default_selected: {total_on} 个（预期 35）")
    print(f"\n新增勾选 ({len(changed_on)}):")
    for k in changed_on:
        print(f"  + {k}")
    print(f"\n取消勾选 ({len(changed_off)}):")
    for k in changed_off:
        print(f"  - {k}")

    # 分类分布
    print(f"\n=== 按类别分布 ===")
    for c in cat["categories"]:
        on = sum(1 for f in c["features"] if f.get("default_selected"))
        if on > 0:
            print(f"  {c['name']:18s}: {on:2d} / {c['feature_count']:3d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
