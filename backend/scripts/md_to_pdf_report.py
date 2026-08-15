"""Convert TradingAgents markdown report to a styled Chinese PDF."""

import os
import re
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    SimpleDocTemplate,
)
from reportlab.lib import colors

# 使用 TTF 内嵌中文字体（比 UnicodeCIDFont 更可靠：字体嵌入 PDF，
# 任何 PDF 渲染器（含浏览器 pdfjs）都能正确显示中文）
# 首选文泉驿（TrueType 轮廓 + 34,600 字形全 GBK 覆盖），
# 正文用 MicroHei、粗体用 ZenHei（addMapping 使 <b> 真正加粗）
# 字体路径按脚本位置相对项目根解析（docker/training/fonts/），
# 容器内（/app/backend/...）和宿主机直跑都可用
_FONT_ROOT = Path(__file__).resolve().parents[2] / "docker" / "training" / "fonts"
_FONT_CANDIDATES = [
    str(_FONT_ROOT / "WQYMicroHei.ttf"),
    str(_FONT_ROOT / "NotoSansCJK.ttf"),
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
]

_BOLD_CANDIDATES = [
    str(_FONT_ROOT / "WQYZenHei.ttf"),
]


def _register_cjk_font() -> str:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", path))
                # 注册粗体字重：<b> 标签真正加粗
                for bold_path in _BOLD_CANDIDATES:
                    if Path(bold_path).exists():
                        try:
                            pdfmetrics.registerFont(TTFont("CJK-Bold", bold_path))
                            from reportlab.lib.fonts import addMapping

                            addMapping("CJK", 0, 0, "CJK")
                            addMapping("CJK", 1, 0, "CJK-Bold")
                            addMapping("CJK", 0, 1, "CJK")
                            addMapping("CJK", 1, 1, "CJK-Bold")
                            break
                        except Exception as exc:
                            print(f"注册粗体失败 {bold_path}: {exc}")
                return "CJK"
            except Exception as exc:
                print(f"注册字体失败 {path}: {exc}")
    # 回退到 CID 字体
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


FONT_NAME = _register_cjk_font()


def unescape_html(text: str) -> str:
    # 仅转义，不做 Markdown 解析（代码块用：代码里的 * 是字面量，不能转换）
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_inline_md(text: str) -> str:
    """转义 HTML 特殊字符并应用行内 Markdown 标记（**粗体** / *斜体*）。

    - 全角空格（U+3000）替换为普通空格（reportlab 段落排版会丢失全角空格）
    - 先转义再注入 <b>/<i> 标签（比转义后 replace 还原更安全）
    - 所有分支统一走这里：正文/列表/表格/引用/标题内的 ** 都会被转换
    """
    text = text.replace("　", "  ")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


def main(md_path: str, pdf_path: str) -> None:
    content = Path(md_path).read_text(encoding="utf-8")

    styles = {
        "h1": ParagraphStyle(
            "h1",
            fontName=FONT_NAME,
            fontSize=18,
            leading=26,
            spaceAfter=8,
            textColor=colors.HexColor("#1a1a2e"),
            alignment=1,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=FONT_NAME,
            fontSize=14,
            leading=20,
            spaceBefore=12,
            spaceAfter=4,
            textColor=colors.HexColor("#1a4d8f"),
        ),
        "blockquote": ParagraphStyle(
            "blockquote",
            fontName=FONT_NAME,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#555555"),
            leftIndent=6 * mm,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "body", fontName=FONT_NAME, fontSize=10, leading=16, spaceAfter=6
        ),
        "table": ParagraphStyle("table", fontName=FONT_NAME, fontSize=9, leading=13),
        "th": ParagraphStyle(
            "th", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.white
        ),
        "code": ParagraphStyle(
            "code",
            fontName=FONT_NAME,
            fontSize=9,
            leading=14,
            backColor=colors.HexColor("#f0f0f0"),
            spaceAfter=6,
        ),
    }

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="QuantMind 投研分析报告",
    )

    story: list = []
    in_code = False
    code_buf: list[str] = []
    table_buf: list[list[str]] = []
    in_table = False

    def flush_code():
        nonlocal code_buf, in_code
        if code_buf:
            story.append(
                Paragraph(
                    f'<font face="{FONT_NAME}">'
                    + unescape_html("\n".join(code_buf)).replace("\n", "<br/>")
                    + "</font>",
                    styles["code"],
                )
            )
            code_buf = []
        in_code = False

    def flush_table():
        nonlocal table_buf, in_table
        if table_buf:
            header = table_buf[0]
            data = table_buf[1:]
            # normalize rows
            ncol = max(len(r) for r in table_buf)
            rows = [
                [
                    Paragraph(
                        render_inline_md(r[c] if c < len(r) else "").replace("|", ""),
                        styles["table"],
                    )
                    for c in range(ncol)
                ]
                for r in data
            ]
            header_ps = [Paragraph(render_inline_md(h), styles["th"]) for h in header]
            t = Table([header_ps] + rows, repeatRows=1)
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d8f")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f5f8fc")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 8))
            table_buf = []
        in_table = False

    for line in content.splitlines():
        s = line.rstrip()
        # code block
        if s.strip().startswith("```"):
            if in_code:
                flush_code()
            else:
                flush_table()
                in_code = True
            continue
        if in_code:
            code_buf.append(s)
            continue
        # table: detect | header | then --- | then rows
        if s.strip().startswith("|") and "|" in s:
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if not in_table:
                in_table = True
                table_buf = [cells]
            else:
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    continue  # separator row
                table_buf.append(cells)
            continue
        else:
            if in_table:
                flush_table()
        # headings
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            key = "h1" if level == 1 else "h2"
            story.append(Paragraph(render_inline_md(text), styles[key]))
            continue
        # blockquote
        if s.startswith(">"):
            story.append(
                Paragraph(render_inline_md(s.lstrip(">").strip()), styles["blockquote"])
            )
            continue
        # hr
        if s.strip() in ("---", "***", "___"):
            story.append(Spacer(1, 6))
            continue
        # bullet list
        if re.match(r"^[-*]\s+", s):
            story.append(
                Paragraph(
                    "• " + render_inline_md(re.sub(r"^[-*]\s+", "", s)),
                    styles["body"],
                )
            )
            continue
        # numbered list
        if re.match(r"^\d+\.\s+", s):
            story.append(Paragraph(render_inline_md(s), styles["body"]))
            continue
        # ordinary paragraph
        if s.strip():
            story.append(Paragraph(render_inline_md(s), styles["body"]))

    if in_table:
        flush_table()
    if in_code:
        flush_code()

    element_count = len(story)
    doc.build(story)
    # 注意：reportlab 的 doc.build() 会原地清空 story 列表，
    # 所以必须在 build 之前统计元素个数
    print(f"PDF 已生成: {pdf_path}（{element_count} 个元素）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
