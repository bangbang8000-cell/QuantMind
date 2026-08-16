"""Convert TradingAgents markdown report to a styled Chinese PDF (研报级设计).

设计规范（对应 SKILL.md §7.4）：
- 封面页：深海军蓝底 + 金色双线 + 白字标题 + 报告日期/数据截至 + 免责声明
- 页眉：金色细线 + 当前章节标题（afterFlowable 跟踪当前页所属章节）
- 页脚：金色细线 + 免责声明 + 「第 X 页 / 共 Y 页」（NumberedCanvas 延迟绘制拿总页数）
- 章节标题（H2）：金色竖线 + 深蓝粗体 + 金色细分隔线
- 表格：深蓝表头白字 + 金色表头底线 + 斑马纹 + 数字列自动右对齐
- A股语义配色（红涨绿跌）：涨/买入/偏多→红，跌/卖出/偏空→绿，中性→琥珀
- 引用块 → 米色金边提示框；分隔线 → 金色细线
- 字体：Noto Sans CJK SC（覆盖全、现代感）；缺省回退文泉驿 / CID 字体
"""

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    SimpleDocTemplate,
)

PAGE_W, PAGE_H = A4

# ---------- 设计 token（金融蓝 + 金色点缀，券商研报风） ----------
C_PRIMARY = colors.HexColor("#1A4D8F")      # 主色·深蓝（表头 / H2 文字）
C_NAVY = colors.HexColor("#0F2A52")         # 深海军蓝（封面背景）
C_ACCENT = colors.HexColor("#C9A227")       # 点缀金（分隔线 / 竖线 / 页眉底线）
C_TEXT = colors.HexColor("#1A1A2E")         # 正文墨色
C_MUTED = colors.HexColor("#5A6472")        # 次级灰（封面元信息 / 页眉页脚）
C_ROW_ALT = colors.HexColor("#F4F7FB")      # 表格斑马纹
C_BORDER = colors.HexColor("#C5CFDC")       # 表格边框
C_CODE_BG = colors.HexColor("#F0F2F5")      # 代码块底色
C_QUOTE_BG = colors.HexColor("#FBF6E6")     # 引用块米色底
C_QUOTE_EDGE = colors.HexColor("#C9A227")   # 引用块金边

# A股语义色（红涨绿跌；评级/信号词映射）
C_UP = colors.HexColor("#C0392B")           # 涨/买入/偏多/优秀
C_DOWN = colors.HexColor("#1E8449")         # 跌/卖出/偏空/恶化
C_NEUTRAL = colors.HexColor("#B07D00")      # 中性/震荡/观望（琥珀）
C_LIGHT_UP = colors.HexColor("#FBEBE9")     # 红底（正数/多方单元格）
C_LIGHT_DOWN = colors.HexColor("#E9F5EE")   # 绿底（负数/空方单元格）
C_LIGHT_NEUTRAL = colors.HexColor("#FBF3DE")  # 琥珀底（中性单元格）

# ---------- 字体（Noto Sans CJK SC 优先，回退文泉驿 / CID） ----------
_FONT_ROOT = Path(__file__).resolve().parents[2] / "docker" / "training" / "fonts"
_FONT_CANDIDATES = [
    str(_FONT_ROOT / "NotoSansCJKSC-Regular.ttf"),
    str(_FONT_ROOT / "NotoSansCJK.ttf"),
    str(_FONT_ROOT / "WQYMicroHei.ttf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]
_BOLD_CANDIDATES = [
    str(_FONT_ROOT / "NotoSansCJKSC-Bold.ttf"),
    str(_FONT_ROOT / "WQYZenHei.ttf"),
]


def _register_cjk_font() -> str:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", path))
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


# ---------- 语义配色（A股红涨绿跌） ----------

_SEMANTIC_KEYWORDS = {
    "up": ("买入", "增持", "优秀", "偏多", "流入", "多头", "低估",
           "buy", "BUY", "bullish", "Bullish"),
    "down": ("卖出", "减持", "恶化", "偏空", "流出", "空头", "高估", "偏高",
             "sell", "SELL", "bearish", "Bearish"),
    "neutral": ("中性", "震荡", "分歧", "观望", "合理", "hold", "HOLD",
                "neutral", "Neutral"),
}

# 含以上关键词但不应配色的长句（如「风险提示：…」全句）
_SEMANTIC_SKIP_PREFIXES = ("风险提示", "数据质量声明", "触发条件")
_SEMANTIC_MAX_LEN = 20


def classify_semantic(text: str) -> str:
    """文本 → 语义类别（'up'/'down'/'neutral'/''，空串=不配色）。

    优先级：负向 > 正向 > 中性；长句和提示类句子不配色，
    避免把整段风险描述染成绿色。"""
    if not text or len(text) > _SEMANTIC_MAX_LEN:
        return ""
    if any(text.startswith(p) for p in _SEMANTIC_SKIP_PREFIXES):
        return ""
    if any(k in text for k in _SEMANTIC_KEYWORDS["down"]):
        return "down"
    if any(k in text for k in _SEMANTIC_KEYWORDS["up"]):
        return "up"
    if any(k in text for k in _SEMANTIC_KEYWORDS["neutral"]):
        return "neutral"
    return ""


_SEMANTIC_TEXT_COLORS = {"up": C_UP, "down": C_DOWN, "neutral": C_NEUTRAL}
_SEMANTIC_BG_COLORS = {
    "up": C_LIGHT_UP,
    "down": C_LIGHT_DOWN,
    "neutral": C_LIGHT_NEUTRAL,
}


# ---------- 数字列右对齐 ----------

_NUM_CELL_RE = re.compile(
    r"^[-+]?\d[\d,]*(?:\.\d+)?(?:\s*(?:%|x|X|pct|亿|万|元|股|手|倍))*$"
)


def is_numeric_cell(text: str) -> bool:
    """判断表格单元格是否纯数值（带可选的单位/百分比后缀，如「1.37 亿股」）。

    数字列右对齐的依据；含说明文字的单元格不算（如「+24.9% 后回落」）。
    """
    t = text.strip().replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace(",", "")
    return bool(_NUM_CELL_RE.match(t))


def cell_numeric_value(text: str) -> float | None:
    """提取单元格开头的数值（用于语义底色的正负判断），无数字返回 None。"""
    t = text.strip().replace("&amp;", "&").replace(",", "")
    m = re.match(r"^([-+]?\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


# ---------- 封面元信息 ----------

def extract_cover_meta(content: str) -> tuple[str, list[str]]:
    """从 md 提取标题 + 封面元信息（含「报告日期/数据截至」的 blockquote 行）。

    两字段可能分两行，也可能同处一行（全角空格分隔）——都收；
    其余 blockquote（分析框架/免责声明）不上封面（封面底部有统一免责声明）。
    """
    title = "QuantMind 投研分析报告"
    meta_lines: list[str] = []
    for line in content.splitlines():
        s = line.rstrip()
        m = re.match(r"^#\s+(.*)", s)
        if m:
            title = m.group(1).strip()
            continue
        if s.startswith(">"):
            stripped = s.lstrip(">").strip()
            if "报告日期" in stripped or "数据截至" in stripped:
                meta_lines.append(stripped)
    return title, meta_lines


def build_footer_text(page: int, total: int) -> str:
    """页脚：免责声明 + 第 X 页 / 共 Y 页。"""
    disc = "本报告由 QuantMind 自动生成，仅供研究参考，不构成投资建议"
    return f"{disc}　|　第 {page} 页 / 共 {total} 页"


# ---------- 章节标题（金色竖线 + 深蓝粗体 + 细分隔线） ----------

def _build_h2(text: str, styles: dict) -> list:
    bar = Table(
        [[""]], colWidths=[0.8 * mm], rowHeights=[7 * mm],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_ACCENT)]),
    )
    para = Paragraph(render_inline_md(text), styles["h2"])
    row = Table(
        [[bar, para]], colWidths=[2.8 * mm, None],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 1.8 * mm),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    return [
        row,
        Spacer(1, 2.5),
        HRFlowable(width="100%", thickness=0.5, color=C_ACCENT),
        Spacer(1, 5),
    ]


def _build_quote(text: str, styles: dict) -> list:
    """引用块 → 米色金边提示框（左侧金色粗竖线 + 浅米底）。"""
    para = Paragraph(render_inline_md(text), styles["blockquote"])
    row = Table(
        [[para]], colWidths=[None],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), C_QUOTE_BG),
            ("LINEBEFORE", (0, 0), (0, -1), 2.2, C_QUOTE_EDGE),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    )
    return [row, Spacer(1, 6)]


def _build_code(text: str, styles: dict) -> Paragraph:
    return Paragraph(
        f'<font face="{FONT_NAME}">'
        + unescape_html(text).replace("\n", "<br/>")
        + "</font>",
        styles["code"],
    )


def build_flat_story(content: str, styles: dict) -> list:
    """逐行渲染 markdown → platypus 元素列表。

    每个 H1/H2 flowable 挂 `_qm_heading` 属性（页眉跟踪用），
    H2 块用 KeepTogether 包住防跨页拆分。
    """
    story: list = []
    in_code = False
    code_buf: list[str] = []
    table_buf: list[list[str]] = []
    in_table = False

    def flush_code():
        nonlocal code_buf, in_code
        if code_buf:
            story.append(_build_code("\n".join(code_buf), styles))
            code_buf = []
        in_code = False

    def flush_table():
        nonlocal table_buf, in_table
        if table_buf:
            header = table_buf[0]
            data = table_buf[1:]
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

            # 数字列右对齐：该列全部数据单元格均为纯数值才右对齐
            numeric_cols = [bool(data)] * ncol
            for c in range(ncol):
                if not all(is_numeric_cell(r[c]) for r in data if c < len(r)):
                    numeric_cols[c] = False

            # 语义配色：数据单元格按关键词着色，纯数值按正负着色
            semantic_cells: dict[tuple[int, int], str] = {}
            for r_idx, row in enumerate(data, start=1):
                for c_idx in range(min(ncol, len(row))):
                    kind = classify_semantic(row[c_idx])
                    if not kind:
                        val = cell_numeric_value(row[c_idx])
                        if val is not None:
                            kind = "up" if val > 0 else "down"
                    if kind:
                        semantic_cells[(r_idx, c_idx)] = kind

            t = Table([header_ps] + rows, repeatRows=1)
            cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, C_ACCENT),
                ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_ROW_ALT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
            for col in range(ncol):
                if numeric_cols[col]:
                    cmds.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
            for (row_i, col_i), kind in semantic_cells.items():
                cmds.append(
                    ("BACKGROUND", (col_i, row_i), (col_i, row_i), _SEMANTIC_BG_COLORS[kind])
                )
                cmds.append(
                    ("TEXTCOLOR", (col_i, row_i), (col_i, row_i), _SEMANTIC_TEXT_COLORS[kind])
                )
            t.setStyle(TableStyle(cmds))
            story.append(t)
            story.append(Spacer(1, 8))
            table_buf = []
        in_table = False

    for line in content.splitlines():
        s = line.rstrip()
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
        if in_table:
            flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                para = Paragraph(render_inline_md(text), styles["h1"])
                para._qm_heading = text
                story.append(para)
            else:
                kt = KeepTogether(_build_h2(text, styles))
                kt._qm_heading = text
                story.append(kt)
            continue
        if s.startswith(">"):
            story.extend(_build_quote(s.lstrip(">").strip(), styles))
            continue
        if s.strip() in ("---", "***", "___"):
            story.append(
                HRFlowable(
                    width="100%", thickness=0.6, color=C_ACCENT,
                    spaceBefore=2, spaceAfter=4,
                )
            )
            continue
        if re.match(r"^[-*]\s+", s):
            story.append(
                Paragraph(
                    "• " + render_inline_md(re.sub(r"^[-*]\s+", "", s)),
                    styles["body"],
                )
            )
            continue
        if re.match(r"^\d+\.\s+", s):
            story.append(Paragraph(render_inline_md(s), styles["body"]))
            continue
        if s.strip():
            story.append(Paragraph(render_inline_md(s), styles["body"]))

    if in_table:
        flush_table()
    if in_code:
        flush_code()
    return story


def main(md_path: str, pdf_path: str) -> None:
    content = Path(md_path).read_text(encoding="utf-8")
    title, meta_lines = extract_cover_meta(content)

    styles = {
        "h1": ParagraphStyle(
            "h1", fontName=FONT_NAME, fontSize=18, leading=26, spaceAfter=8,
            textColor=C_TEXT, alignment=TA_CENTER,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=FONT_NAME, fontSize=14, leading=20,
            spaceBefore=4, spaceAfter=3, textColor=C_PRIMARY,
        ),
        "blockquote": ParagraphStyle(
            "blockquote", fontName=FONT_NAME, fontSize=9.5, leading=15,
            textColor=C_MUTED, leftIndent=2 * mm,
        ),
        "body": ParagraphStyle(
            "body", fontName=FONT_NAME, fontSize=10, leading=16, spaceAfter=6
        ),
        "table": ParagraphStyle("table", fontName=FONT_NAME, fontSize=9, leading=13),
        "th": ParagraphStyle(
            "th", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.white
        ),
        "code": ParagraphStyle(
            "code", fontName=FONT_NAME, fontSize=9, leading=14,
            backColor=C_CODE_BG, spaceAfter=6,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", fontName=FONT_NAME, fontSize=30, leading=42,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontName=FONT_NAME, fontSize=10.5, leading=18,
            textColor=colors.HexColor("#D8E2F0"), alignment=TA_CENTER,
        ),
        "cover_disc": ParagraphStyle(
            "cover_disc", fontName=FONT_NAME, fontSize=9, leading=14,
            textColor=colors.HexColor("#8FA3C0"), alignment=TA_CENTER,
        ),
    }

    story = build_flat_story(content, styles)

    # 封面 flowables 插到最前
    cover_flowables: list = [
        Spacer(1, 58 * mm),
        HRFlowable(
            width=46 * mm, thickness=0.8, color=C_ACCENT,
            spaceBefore=0, spaceAfter=4 * mm,
        ),
        Paragraph(render_inline_md(title), styles["cover_title"]),
        Spacer(1, 5 * mm),
        HRFlowable(
            width=46 * mm, thickness=0.8, color=C_ACCENT,
            spaceBefore=0, spaceAfter=10 * mm,
        ),
    ]
    for line in meta_lines:
        cover_flowables.append(Paragraph(render_inline_md(line), styles["cover_meta"]))
    cover_flowables += [
        Spacer(1, 46 * mm),
        Paragraph(
            "本报告由 QuantMind 投研分析管线自动生成<br/>"
            "仅供学习研究参考，不构成任何投资建议",
            styles["cover_disc"],
        ),
        PageBreak(),
    ]
    story = cover_flowables + story

    # 页眉跟踪：afterFlowable 记录当前页所属章节（按页号，两遍构建各自重建）
    tracker: dict[int, str] = {}

    def _after_flowable(flowable):
        text = getattr(flowable, "_qm_heading", None)
        if text:
            tracker[doc.canv.getPageNumber()] = text

    # 两遍构建：第一遍拿总页数，第二遍页脚带「共 Y 页」；最后一次构建生效
    total_pages = 1

    from reportlab.pdfgen import canvas as _pdfcanvas

    class NumberedCanvas(_pdfcanvas.Canvas):
        """延迟绘制页眉/页脚：先收集每页状态，save() 时统一画（总页数已知）。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_header_footer(num_pages)
                super().showPage()
            super().save()

        def _draw_header_footer(self, total: int):
            page = self._pageNumber
            if page == 1:
                return  # 封面不画页眉页脚
            w, h = PAGE_W, PAGE_H
            # 页眉：金色细线 + 当前章节
            self.setStrokeColor(C_ACCENT)
            self.setLineWidth(0.6)
            self.line(18 * mm, h - 15 * mm, w - 18 * mm, h - 15 * mm)
            heading = tracker.get(page, "")
            if heading:
                self.setFillColor(C_MUTED)
                self.setFont(FONT_NAME, 7.5)
                self.drawString(18 * mm, h - 13.2 * mm, heading[:38])
            # 页脚：金色细线 + 免责声明 + 页码
            self.setStrokeColor(C_ACCENT)
            self.setLineWidth(0.6)
            self.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
            self.setFillColor(C_MUTED)
            self.setFont(FONT_NAME, 7.5)
            self.drawCentredString(w / 2, 9.5 * mm, build_footer_text(page, total))

    def _canvasmaker(filename, **kwargs):
        return NumberedCanvas(filename, **kwargs)

    def _cover_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_NAVY)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, PAGE_H - 10 * mm, PAGE_W, 1.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_NAME, 11)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 24 * mm, "QuantMind · 量化投研")
        canvas.setFillColor(colors.HexColor("#8FA3C0"))
        canvas.setFont(FONT_NAME, 7.5)
        canvas.drawCentredString(
            PAGE_W / 2, 12 * mm,
            "本报告由 AI 自动生成，仅供研究参考，不构成投资建议",
        )
        canvas.restoreState()

    for _ in range(2):
        tracker.clear()
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=title,
            author="QuantMind 投研分析",
        )
        doc.afterFlowable = _after_flowable
        doc.build(
            list(story),
            onFirstPage=_cover_page,
            onLaterPages=lambda c, d: None,
            canvasmaker=_canvasmaker,
        )
        total_pages = doc.page

    print(f"PDF 已生成: {pdf_path}（{len(story)} 个元素，{total_pages} 页）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
