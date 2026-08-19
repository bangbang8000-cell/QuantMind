from backend.services.engine.data_platform.quantdb_factor_dictionary import definition_for


def test_documented_factor_definition_uses_documented_category():
    definition = definition_for("mom_ret_20d")

    assert definition["category_id"] == "momentum"
    assert definition["category_name"] == "动量"
    assert "收益率" in str(definition["display_name"])
    assert "官方帮助文档" in str(definition["explanation"])
    assert "300_factors_lightgbm_design_v2.md" not in str(definition["explanation"])
    assert definition["confidence"] == "documented"


def test_unknown_factor_stays_reviewable():
    definition = definition_for("vendor_extension_signal")

    assert definition["category_id"] == "other"
    assert definition["confidence"] == "needs_review"
