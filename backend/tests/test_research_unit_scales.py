"""research_features_service 单位换算表测试。

覆盖 _apply_unit_scales 的两条路径（camelCase 投影 / snake_case 全量），
以及 flowSuperNet 与同类别 flow* 字段的量纲一致性（bug #19 回归）。
"""
import os
import sys

project_root = os.path.join(os.path.dirname(__file__), "../../")
sys.path.append(project_root)

from backend.services.api.routers.research_features_service import (  # noqa: E402
    _apply_unit_scales,
)


def test_apply_unit_scales_scales_flow_super_net_camel():
    """flowSuperNet 元 → 百万元（与 flowNetAmount 同量纲）。"""
    values = {"flowSuperNet": -6_840_376.0, "flowNetAmount": -274_109_797.7}
    _apply_unit_scales(values)
    assert abs(values["flowSuperNet"] - (-6.840376)) < 1e-9
    assert abs(values["flowNetAmount"] - (-274.1097977)) < 1e-9


def test_apply_unit_scales_scales_flow_super_net_snake():
    """snake_case 键 flow_super_net 同样缩放。"""
    values = {"flow_super_net": 1_000_000.0}
    _apply_unit_scales(values)
    assert values["flow_super_net"] == 1.0


def test_apply_unit_scales_mv_to_yi():
    """totalMv 元 → 亿元。"""
    values = {"totalMv": 1_677_597_000_000.0}
    _apply_unit_scales(values)
    assert values["totalMv"] == 16775.97


def test_apply_unit_scales_untouched_fields_unchanged():
    """未在换算表的字段保持原值。"""
    values = {"momRet1d": 0.0147, "someOther": 42}
    _apply_unit_scales(values)
    assert values["momRet1d"] == 0.0147
    assert values["someOther"] == 42
