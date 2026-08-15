"""md_to_pdf_report 的 Markdown 行内渲染单元测试。

直接测试 render_inline_md（无需 reportlab 渲染），
覆盖历史 bug：** 泄漏到 PDF、全角空格丢失、表格单元格。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# reportlab 未安装时可跳过
try:
    from backend.scripts.md_to_pdf_report import render_inline_md, unescape_html
except ImportError:
    render_inline_md = None
    unescape_html = None

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
