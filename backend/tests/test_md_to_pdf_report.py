"""md_to_pdf_report 的 Markdown 行内渲染单元测试。

直接测试 render_inline_md（无需 reportlab 渲染），
覆盖历史 bug：** 泄漏到 PDF、全角空格丢失、表格单元格。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# reportlab 未安装时可跳过
try:
    from backend.scripts.md_to_pdf_report import (
        render_inline_md,
        unescape_html,
        classify_semantic,
        is_numeric_cell,
        cell_numeric_value,
        extract_cover_meta,
        build_footer_text,
    )
except ImportError:
    render_inline_md = None
    unescape_html = None
    classify_semantic = None
    is_numeric_cell = None
    cell_numeric_value = None
    extract_cover_meta = None
    build_footer_text = None

import pytest


pytestmark = pytest.mark.skipif(
    render_inline_md is None, reason="reportlab 未安装，跳过渲染函数测试"
)


def test_bold_in_blockquote():
    # 历史 bug：blockquote 行的 ** 直接泄漏进 PDF
    # 调用方（主循环）先 lstrip(">") 再传进来，所以这里模拟剥离后的文本
    assert render_inline_md("**交易日期**: 2026-08-15") == (
        "<b>交易日期</b>: 2026-08-15"
    )


def test_bold_in_bullet():
    assert render_inline_md("- **成长性碾压**：净利润 +88.7%") == (
        "- <b>成长性碾压</b>：净利润 +88.7%"
    )


def test_bold_in_table_cell():
    # 历史 bug：表格单元格的 ** 泄漏（如"| 未持仓 | **观望** |"）
    assert render_inline_md("| **观望** |") == "| <b>观望</b> |"


def test_mixed_bold_italic():
    assert render_inline_md("**加粗** 与 *斜体* 混排") == (
        "<b>加粗</b> 与 <i>斜体</i> 混排"
    )


def test_fullwidth_space_replaced():
    # 历史 bug：全角空格（U+3000）被 reportlab 段落排版丢弃
    assert render_inline_md("2026-08-15　|　21:09") == "2026-08-15  |  21:09"


def test_html_escaped_before_markup():
    # < > & 先转义，防止注入非法标签
    assert render_inline_md("a <b> & c") == "a &lt;b&gt; &amp; c"


def test_bold_wrapping_escaped_content():
    # 转义先于 ** 转换：粗体内部的 & 也要转义
    assert render_inline_md("**A&B**") == "<b>A&amp;B</b>"


def test_unescape_html_only_escapes_no_markdown():
    # 代码块专用：* 是字面量，不能转换
    assert unescape_html("import os\nprint('**x**')") == (
        "import os\nprint('**x**')"
    )


def test_no_asterisk_leak_after_render():
    # 渲染后不应残留任何 * 标记
    assert "*" not in render_inline_md("**粗体** 和 *斜体*")


# ---------- 语义配色（A股红涨绿跌） ----------


def test_semantic_up_keywords():
    for word in ("买入", "增持", "优秀", "偏多", "流入", "多头", "低估"):
        assert classify_semantic(word) == "up", word


def test_semantic_down_keywords():
    for word in ("卖出", "减持", "恶化", "偏空", "流出", "空头", "高估"):
        assert classify_semantic(word) == "down", word


def test_semantic_neutral_keywords():
    for word in ("中性", "震荡", "分歧", "观望", "合理"):
        assert classify_semantic(word) == "neutral", word


def test_semantic_down_wins_over_up():
    # 「高估」类负向词优先级高于正向词
    assert classify_semantic("高估") == "down"


def test_semantic_long_sentence_not_colored():
    # 长句（>20 字符）不配色，避免整段描述被染色
    assert classify_semantic("融资 20 日净卖出累计 15.44 亿元——杠杆资金持续撤离") == ""


def test_semantic_risk_prefix_not_colored():
    assert classify_semantic("风险提示：估值回撤风险") == ""


def test_semantic_english_signal_words():
    # 报告的 SELL/HOLD/BUY 是大写，也要命中
    assert classify_semantic("BUY") == "up"
    assert classify_semantic("SELL") == "down"
    assert classify_semantic("HOLD") == "neutral"
    assert classify_semantic("buy") == "up"
    assert classify_semantic("sell") == "down"
    assert classify_semantic("hold") == "neutral"


# ---------- 数字列右对齐判断 ----------


def test_numeric_cell_plain():
    assert is_numeric_cell("123.45")


def test_numeric_cell_with_units():
    for cell in ("32.3x", "-24.2%", "1.37 亿股", "+56.5%", "66.19 元"):
        assert is_numeric_cell(cell), cell


def test_numeric_cell_with_thousands_separator():
    assert is_numeric_cell("1,200,345")


def test_non_numeric_cell_with_text():
    for cell in ("+24.9% 后回落", "SELL 4 条", "—", "偏空", ""):
        assert not is_numeric_cell(cell), cell


def test_numeric_value_extraction():
    assert cell_numeric_value("-24.2%") == -24.2
    assert cell_numeric_value("+56.5%") == 56.5
    assert cell_numeric_value("—") is None
    assert cell_numeric_value("SELL 4 条") is None


# ---------- 封面元信息 / 页脚 ----------

SAMPLE_MD = """# 工业富联（601138.SH）深度分析报告

> **报告日期**：2026-08-16　**数据截至**：行情 2026-08-14 [API]

> **分析框架**：市场环境 → 基本面 → 估值 → 技术 → 资金筹码 → 行业 → 模型 → 舆情

## 一、投资要点

正文内容。
"""


def test_extract_cover_meta_title():
    title, meta = extract_cover_meta(SAMPLE_MD)
    assert title == "工业富联（601138.SH）深度分析报告"


def test_extract_cover_meta_lines():
    _, meta = extract_cover_meta(SAMPLE_MD)
    # 报告日期+数据截至（同处一行）收 1 条；分析框架行不上封面
    assert len(meta) == 1
    assert "报告日期" in meta[0] and "数据截至" in meta[0]


def test_extract_cover_meta_lines_split_across_lines():
    # 两字段分两行时都收
    md = """# 某股票深度报告

> **报告日期**：2026-08-16

> **数据截至**：行情 2026-08-14

> **分析框架**：市场 → 基本面

正文
"""
    _, meta = extract_cover_meta(md)
    assert len(meta) == 2
    assert meta[0].startswith("**报告日期**")
    assert meta[1].startswith("**数据截至**")


def test_extract_cover_meta_defaults():
    title, meta = extract_cover_meta("没有标题\n\n纯正文\n")
    assert title == "QuantMind 投研分析报告"
    assert meta == []


def test_footer_text_contains_page_numbers():
    footer = build_footer_text(3, 12)
    assert "第 3 页" in footer
    assert "共 12 页" in footer
    assert "不构成投资建议" in footer
