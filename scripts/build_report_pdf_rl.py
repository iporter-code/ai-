import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".packages"))

from pypdf import PdfReader
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
import reportlab.lib.textsplit as rl_textsplit
import reportlab.platypus.paragraph as rl_paragraph

_EXTRA_CANNOT_START = "，。、；：！？）》」』】〕”’…—～%‰℃"
rl_textsplit.ALL_CANNOT_START += _EXTRA_CANNOT_START
rl_paragraph.ALL_CANNOT_START += _EXTRA_CANNOT_START
_CANNOT_START = rl_textsplit.ALL_CANNOT_START

_ORIGINAL_WORD_SPLIT = rl_textsplit.wordSplit
_ORIGINAL_CJK_SPLIT = rl_paragraph.cjkFragSplit


def _pull_punctuation(lines):
    for index in range(1, len(lines)):
        while lines[index][1] and lines[index][1][0] in _CANNOT_START:
            lines[index - 1][1] += lines[index][1][0]
            lines[index][1] = lines[index][1][1:]
    return lines


def _word_split_fixed(text, max_widths, font_name, font_size):
    return _pull_punctuation(
        _ORIGINAL_WORD_SPLIT(text, max_widths, font_name, font_size)
    )


def _pull_cjk_punctuation(lines):
    for index in range(1, len(lines)):
        previous = lines[index - 1]
        current = lines[index]
        while current.words:
            first = current.words[0]
            if not getattr(first, "text", "") or first.text[0] not in _CANNOT_START:
                break
            if not previous.words:
                break
            last = previous.words[-1]
            if not hasattr(last, "text"):
                break
            char = first.text[0]
            width = stringWidth(char, first.fontName, first.fontSize)
            last.text += char
            first.text = first.text[1:]
            previous.currentWidth += width
            current.currentWidth -= width
            previous.extraSpace -= width
            current.extraSpace += width
            if not first.text:
                current.words.pop(0)
    return lines


def _cjk_split_fixed(frags, max_widths, calc_bounds, encoding="utf8"):
    result = _ORIGINAL_CJK_SPLIT(frags, max_widths, calc_bounds, encoding)
    _pull_cjk_punctuation(result.lines)
    return result


rl_textsplit.wordSplit = _word_split_fixed
rl_paragraph.wordSplit = _word_split_fixed
rl_paragraph.cjkFragSplit = _cjk_split_fixed

MD_PATH = ROOT / "docs" / "实验报告.md"
# 报告被查看器占用时，可用 REPORT_PDF_OUT 输出到临时路径
PDF_PATH = Path(os.getenv("REPORT_PDF_OUT") or ROOT / "docs" / "实验报告.pdf")
DOCS_DIR = ROOT / "docs"

FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Song", str(FONT_DIR / "simsun.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("Hei", str(FONT_DIR / "simhei.ttf")))
pdfmetrics.registerFont(TTFont("Code", str(FONT_DIR / "simsun.ttc"), subfontIndex=1))

BLACK = colors.HexColor("#000000")

BODY_FONT_SIZE = 9.0
BODY_LEADING = 12.4
FRONT_PAGES = 0

PAGE_LAND = landscape(A4)
LAND_MARGIN_X = 2.0 * cm
LAND_MARGIN_TOP = 2.0 * cm
LAND_MARGIN_BOTTOM = 1.8 * cm
LAND_CONTENT_WIDTH = PAGE_LAND[0] - 2 * LAND_MARGIN_X
LAND_CONTENT_HEIGHT = PAGE_LAND[1] - LAND_MARGIN_TOP - LAND_MARGIN_BOTTOM


def style(name, **kwargs):
    base = dict(
        fontName="Song",
        fontSize=BODY_FONT_SIZE,
        leading=BODY_LEADING,
        textColor=BLACK,
        wordWrap="CJK",
    )
    base.update(kwargs)
    return ParagraphStyle(name, **base)


S_COVER_COURSE = style("CoverCourse", fontName="Hei", fontSize=16, leading=24, alignment=TA_CENTER)
S_COVER_KIND = style("CoverKind", fontName="Hei", fontSize=24, leading=34, alignment=TA_CENTER)
S_COVER_TITLE = style("CoverTitle", fontName="Hei", fontSize=26, leading=38, alignment=TA_CENTER)
S_COVER_SUBTITLE = style("CoverSubtitle", fontName="Song", fontSize=14, leading=24, alignment=TA_CENTER)
S_COVER_LABEL = style("CoverLabel", fontName="Hei", fontSize=12, leading=22, alignment=TA_RIGHT)
S_COVER_VALUE = style("CoverValue", fontSize=12, leading=22, alignment=TA_LEFT)

S_TITLE = style("Title", fontName="Hei", fontSize=17, leading=22, alignment=TA_CENTER, spaceAfter=3)
S_META = style("Meta", fontName="Song", fontSize=9, leading=14, alignment=TA_CENTER, spaceAfter=4)
S_ABS = style("AbstractCompact", fontName="Song", fontSize=8.8, leading=13.6, alignment=TA_JUSTIFY, spaceAfter=2)

S_H2 = style(
    "H2",
    fontName="Hei",
    fontSize=13.2,
    leading=18,
    spaceBefore=9,
    spaceAfter=4,
    keepWithNext=1,
)
S_H3 = style(
    "H3",
    fontName="Hei",
    fontSize=10.6,
    leading=14,
    spaceBefore=6,
    spaceAfter=3,
    keepWithNext=1,
)
S_ABSTRACT_HEAD = style("AbstractHead", fontName="Hei", fontSize=16, leading=24, alignment=TA_CENTER, spaceAfter=14)
S_ABSTRACT = style(
    "Abstract",
    fontSize=10.5,
    leading=18,
    firstLineIndent=21,
    alignment=TA_JUSTIFY,
    spaceAfter=8,
)
S_KEYWORDS = style("Keywords", fontSize=10.5, leading=18, alignment=TA_JUSTIFY, spaceAfter=6)
S_BODY = style("Body", firstLineIndent=21, alignment=TA_JUSTIFY, spaceAfter=4)
S_TABLE_CELL = style("TableCell", fontSize=7.3, leading=9.2, spaceAfter=0)
S_TABLE_HEAD = style("TableHead", fontName="Hei", fontSize=7.3, leading=9.2, spaceAfter=0)
S_TABLE_CELL_S = style("TableCellSmall", fontSize=8.2, leading=10.6, spaceAfter=0)
S_TABLE_HEAD_S = style("TableHeadSmall", fontName="Hei", fontSize=8.2, leading=10.6, spaceAfter=0)
S_CAPTION = style("Caption", fontName="Hei", fontSize=8.8, leading=12, alignment=TA_CENTER, spaceBefore=2, spaceAfter=4)
S_TOC_TITLE = style("TOCTitle", fontName="Hei", fontSize=16, leading=24, alignment=TA_CENTER, spaceAfter=14)


def rich(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r'<font name="Hei">\1</font>', text)
    text = re.sub(r"`(.+?)`", r'<font name="Code">\1</font>', text)
    return text


def parse_markdown(text: str):
    blocks = []
    lines = text.splitlines()
    pending_caption = None
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
            i += 1
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
        elif line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
            i += 1
        elif line.startswith("!["):
            match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            raw_target = match.group(2) if match else ""
            width_ratio = 1.0
            path = raw_target
            if "|" in raw_target:
                path, _, ratio_text = raw_target.partition("|")
                try:
                    width_ratio = float(ratio_text)
                except ValueError:
                    width_ratio = 1.0
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            caption = None
            if i < len(lines) and re.match(r"^图\s*[A-Za-z]?\d+", lines[i].strip()):
                caption = lines[i].strip()
                i += 1
            blocks.append(("image", (path, caption, width_ratio)))
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].strip())
                i += 1
            blocks.append(("quote", quote))
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", (pending_caption, rows)))
            pending_caption = None
        elif re.match(r"^表\s*[A-Za-z]?\d+", line):
            pending_caption = line.strip()
            i += 1
        else:
            parts = [line.strip()]
            i += 1
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith(("#", ">", "|", "!", "- ", "* ", "```"))
                and not re.match(r"^[图表]\s*[A-Za-z]?\d+", lines[i].strip())
            ):
                parts.append(lines[i].strip())
                i += 1
            blocks.append(("p", " ".join(parts)))
    return blocks


def parse_meta(blocks):
    meta = {"name": "", "student_id": "", "date": "", "abstract": "", "keywords": ""}
    lines = []
    for kind, value in blocks:
        if kind == "quote":
            lines.extend(value)
    abstract_parts = []
    for line in lines:
        for key, pattern in (
            ("name", r"姓名[：:]\s*([^\s　]+)"),
            ("student_id", r"学号[：:]\s*([^\s　]+)"),
            ("date", r"日期[：:]\s*([^\s　]+)"),
        ):
            match = re.search(pattern, line)
            if match:
                meta[key] = match.group(1)
        if "摘要" in line:
            abstract_parts.append(re.sub(r"^\*\*摘要\*\*[：:]\s*", "", line))
        if "关键词" in line:
            meta["keywords"] = re.sub(r"^\*\*关键词\*\*[：:]\s*", "", line)
    meta["abstract"] = "".join(abstract_parts)
    return meta


def pretty_date(value: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if not match:
        return value or "________"
    return f"{match.group(1)} 年 {int(match.group(2))} 月 {int(match.group(3))} 日"


def roman(number: int) -> str:
    values = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    result = ""
    for value, symbol in values:
        while number >= value:
            result += symbol
            number -= value
    return result or "I"


def make_table(rows, content_width):
    if not rows:
        return None
    cols = max(len(row) for row in rows)
    if cols == 2:
        widths = [0.24, 0.76]
    elif cols == 3:
        widths = [0.22, 0.39, 0.39]
    elif cols == 5:
        widths = [0.055, 0.275, 0.225, 0.215, 0.23]
    elif cols == 6:
        widths = [0.12, 0.18, 0.20, 0.14, 0.18, 0.18]
    else:
        widths = [1 / cols] * cols

    cell_style = S_TABLE_CELL_S if cols == 5 else S_TABLE_CELL
    head_style = S_TABLE_HEAD_S if cols == 5 else S_TABLE_HEAD
    padding = 2.2 if cols == 5 else 3
    data = []
    for r, row in enumerate(rows):
        line = []
        for c in range(cols):
            value = row[c] if c < len(row) else ""
            line.append(Paragraph(rich(value), head_style if r == 0 else cell_style))
        data.append(line)

    table = Table(
        data,
        colWidths=[content_width * w for w in widths],
        repeatRows=1,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1.1, BLACK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BLACK),
                ("LINEBELOW", (0, -1), (-1, -1), 1.1, BLACK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
                ("TOPPADDING", (0, 0), (-1, 0), padding + 1),
                ("BOTTOMPADDING", (0, 0), (-1, 0), padding + 1),
            ]
        )
    )
    return table


class ReportDoc(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="compact", frames=[frame], onPage=self.compact_footer
                ),
            ]
        )

    @staticmethod
    def compact_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Song", 8.5)
        canvas.setFillColor(BLACK)
        canvas.drawCentredString(A4[0] / 2, 0.8 * cm, f"— {doc.page} —")
        canvas.restoreState()

    @staticmethod
    def front_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Song", 9)
        canvas.setFillColor(BLACK)
        canvas.drawCentredString(A4[0] / 2, 1.05 * cm, f"— {roman(max(1, doc.page - 1))} —")
        canvas.restoreState()

    @staticmethod
    def main_header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Song", 9)
        canvas.setFillColor(BLACK)
        canvas.drawString(doc.leftMargin, A4[1] - 1.45 * cm, "大模型前沿课程实验报告")
        canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 1.45 * cm, "不瞎编的私有知识库问答助手")
        canvas.setStrokeColor(BLACK)
        canvas.setLineWidth(0.5)
        canvas.line(
            doc.leftMargin,
            A4[1] - 1.62 * cm,
            A4[0] - doc.rightMargin,
            A4[1] - 1.62 * cm,
        )
        canvas.setFont("Song", 9)
        canvas.drawCentredString(A4[0] / 2, 1.05 * cm, f"— {max(1, doc.page - FRONT_PAGES)} —")
        canvas.restoreState()

    @staticmethod
    def landscape_header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Song", 9)
        canvas.setFillColor(BLACK)
        canvas.drawString(LAND_MARGIN_X, PAGE_LAND[1] - 1.45 * cm, "大模型前沿课程实验报告")
        canvas.drawRightString(
            PAGE_LAND[0] - LAND_MARGIN_X,
            PAGE_LAND[1] - 1.45 * cm,
            "不瞎编的私有知识库问答助手",
        )
        canvas.setStrokeColor(BLACK)
        canvas.setLineWidth(0.5)
        canvas.line(
            LAND_MARGIN_X,
            PAGE_LAND[1] - 1.62 * cm,
            PAGE_LAND[0] - LAND_MARGIN_X,
            PAGE_LAND[1] - 1.62 * cm,
        )
        canvas.setFont("Song", 9)
        canvas.drawCentredString(
            PAGE_LAND[0] / 2, 1.05 * cm, f"— {max(1, doc.page - FRONT_PAGES)} —"
        )
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name in ("H2", "H3"):
            level = 0 if name == "H2" else 1
            text = flowable.getPlainText()
            self.notify("TOCEntry", (level, text, max(1, self.page - FRONT_PAGES)))


def build_cover(title, meta):
    story = [
        Spacer(1, 3.0 * cm),
        Paragraph("大模型前沿课程", S_COVER_COURSE),
        Spacer(1, 1.0 * cm),
        Paragraph("实 验 报 告", S_COVER_KIND),
        Spacer(1, 2.4 * cm),
        Paragraph(rich(title), S_COVER_TITLE),
        Spacer(1, 0.55 * cm),
        Paragraph("——基于 BM25 与 bge-small-zh 的检索增强问答系统", S_COVER_SUBTITLE),
        Spacer(1, 4.6 * cm),
    ]
    info_rows = [
        ("姓　　名", meta["name"] if meta["name"] not in ("", "________") else ""),
        ("学　　号", meta["student_id"] if meta["student_id"] not in ("", "________") else ""),
        ("日　　期", pretty_date(meta["date"])),
    ]
    table = Table(
        [
            [Paragraph(label, S_COVER_LABEL), Paragraph(value, S_COVER_VALUE)]
            for label, value in info_rows
        ],
        colWidths=[3.0 * cm, 5.6 * cm],
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("LINEBELOW", (1, 0), (1, -1), 0.6, BLACK),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (1, 0), (1, -1), 8),
            ]
        )
    )
    story.append(table)
    return story


def build_abstract(meta):
    return [
        Paragraph("摘　要", S_ABSTRACT_HEAD),
        Paragraph(rich(meta["abstract"] or "（摘要待补充）"), S_ABSTRACT),
        Spacer(1, 0.35 * cm),
        Paragraph(
            f'<font name="Hei">关键词：</font>{escape(meta["keywords"] or "（待补充）")}',
            S_KEYWORDS,
        ),
    ]


def build_toc():
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            name="TOCLevel0",
            fontName="Hei",
            fontSize=12,
            leading=22,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=3,
            textColor=BLACK,
        ),
        ParagraphStyle(
            name="TOCLevel1",
            fontName="Song",
            fontSize=11,
            leading=19,
            leftIndent=24,
            firstLineIndent=0,
            textColor=BLACK,
        ),
    ]
    toc.dotsMinLevel = 0
    return [Paragraph("目　录", S_TOC_TITLE), toc]


def table_flow(value, content_width):
    caption, rows = value
    table = make_table(rows, content_width)
    if table is None:
        return []
    flow = []
    if caption:
        flow.append(Paragraph(rich(caption), S_CAPTION))
    flow.append(table)
    return flow


def build_body(blocks, content_width, include_appendix=False):
    story = []
    in_appendix = False
    i = 0
    while i < len(blocks):
        kind, value = blocks[i]
        if kind in ("h1", "quote"):
            i += 1
            continue
        if kind in ("h2", "h3"):
            if kind == "h2" and str(value).startswith("附录"):
                if include_appendix and not in_appendix:
                    in_appendix = True
                else:
                    break
            heading_style = S_H2 if kind == "h2" else S_H3
            group = [Paragraph(rich(str(value)), heading_style)]
            # 连续标题（如「3 评测结果」+「3.1 四项指标」）必须一起走，
            # 否则上级标题会孤零零留在页底。
            j = i + 1
            while j < len(blocks) and blocks[j][0] in ("h2", "h3"):
                sub_kind, sub_value = blocks[j]
                group.append(
                    Paragraph(rich(str(sub_value)), S_H2 if sub_kind == "h2" else S_H3)
                )
                j += 1
            if j < len(blocks):
                next_kind, next_value = blocks[j]
                if next_kind == "table":
                    group.extend(table_flow(next_value, content_width))
                    story.append(KeepTogether(group))
                    story.append(Spacer(1, 8))
                    i = j + 1
                    continue
                if next_kind == "p":
                    group.append(Paragraph(rich(str(next_value)), S_BODY))
                    story.append(KeepTogether(group))
                    i = j + 1
                    continue
            story.append(KeepTogether(group))
            i = j
            continue
        if kind == "p":
            story.append(Paragraph(rich(str(value)), S_BODY))
        elif kind == "table":
            flow = table_flow(value, content_width)
            if flow:
                story.append(KeepTogether(flow))
                story.append(Spacer(1, 8))
        elif kind == "image":
            path, caption, *rest = value
            width_ratio = rest[0] if rest else 1.0
            image_path = DOCS_DIR / path
            if not image_path.exists():
                i += 1
                continue
            with PILImage.open(image_path) as pil_image:
                pixel_width, pixel_height = pil_image.size
            width_limit = LAND_CONTENT_WIDTH if in_appendix else content_width
            max_width = width_limit * 0.96 * width_ratio
            max_height = LAND_CONTENT_HEIGHT - 2.6 * cm if in_appendix else None
            scale = max_width / pixel_width
            if max_height is not None:
                scale = min(scale, max_height / pixel_height)
            img = Image(str(image_path))
            img.drawWidth = pixel_width * scale
            img.drawHeight = pixel_height * scale
            if in_appendix:
                framed = Table([[img]], colWidths=[img.drawWidth], hAlign="CENTER")
                framed.setStyle(
                    TableStyle(
                        [
                            ("BOX", (0, 0), (-1, -1), 0.6, BLACK),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )
                flow = [Spacer(1, 2), framed]
            else:
                flow = [Spacer(1, 4), img]
            if caption:
                flow.append(Paragraph(rich(caption), S_CAPTION))
            story.append(KeepTogether(flow))
            if in_appendix:
                story.append(Spacer(1, 10))
        i += 1
    return story


def build():
    text = MD_PATH.read_text(encoding="utf-8")
    blocks = parse_markdown(text)
    meta = parse_meta(blocks)
    title = next((value for kind, value in blocks if kind == "h1"), "实验报告")

    doc = ReportDoc(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.4 * cm,
        title=title,
        author=meta["name"] if meta["name"] not in ("", "________") else "",
        subject="大模型前沿课程实验报告",
    )
    content_width = doc.width

    story = [
        Paragraph(rich(title), S_TITLE),
        Paragraph(
            f"姓名：{meta['name'] or '________'}　"
            f"学号：{meta['student_id'] or '________'}　"
            f"日期：{meta['date'] or '________'}",
            S_META,
        ),
        Paragraph(rich("**摘要**：" + (meta["abstract"] or "（摘要待补充）")), S_ABS),
        Paragraph(
            rich("**关键词**：" + (meta["keywords"] or "（待补充）")), S_ABS
        ),
        Spacer(1, 4),
    ]
    story.extend(build_body(blocks, content_width, include_appendix=False))

    doc.build(story)
    pages = len(PdfReader(str(PDF_PATH)).pages)
    print(f"{PDF_PATH} pages={pages} size={PDF_PATH.stat().st_size}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    build()
