from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture.png"
FONT = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

W, H = 1800, 980
BG = "#ffffff"
INK = "#111111"
EDGE = "#222222"
FILL = "#F2F2F2"
FILL_ALT = "#E6E6E6"
FILL_EMPH = "#D9D9D9"
GRAY = "#333333"

image = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(image)
title_font = ImageFont.truetype(FONT_BOLD, 42)
box_font = ImageFont.truetype(FONT_BOLD, 30)
small_font = ImageFont.truetype(FONT, 23)
label_font = ImageFont.truetype(FONT, 22)


def box(x, y, w, h, title, subtitle="", accent=False):
    fill = FILL_EMPH if accent else FILL
    edge = INK
    width = 6 if accent else 3
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=fill, outline=edge, width=width)
    lines = title.split("\n")
    line_h = 40
    total_h = line_h * len(lines) + (34 if subtitle else 0)
    ty = y + (h - total_h) / 2
    for line in lines:
        tw = draw.textbbox((0, 0), line, font=box_font)[2]
        draw.text((x + (w - tw) / 2, ty), line, font=box_font, fill=INK)
        ty += line_h
    if subtitle:
        tw = draw.textbbox((0, 0), subtitle, font=small_font)[2]
        draw.text((x + (w - tw) / 2, ty + 2), subtitle, font=small_font, fill=GRAY)


def arrow(points, color=EDGE, width=4):
    draw.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = (x2, y2)
    left = (x2 - ux * 18 + px * 10, y2 - uy * 18 + py * 10)
    right = (x2 - ux * 18 - px * 10, y2 - uy * 18 - py * 10)
    draw.polygon([tip, left, right], fill=color)


def label(x, y, text, color=GRAY):
    draw.text((x, y), text, font=label_font, fill=color)


draw.text((60, 32), "① 离线：导入与索引", font=title_font, fill=INK)
draw.text((60, 420), "② 在线：检索与生成", font=title_font, fill=INK)

box(50, 140, 260, 110, "data/raw", "PDF / MD / TXT")
box(350, 140, 250, 110, "解析与切分", "300 字 / 重叠 50 字")
box(640, 140, 260, 110, "片段库", "chunks.json · 27 段")
box(970, 90, 300, 105, "BM25 索引", "jieba + BM25Okapi")
box(970, 235, 300, 105, "向量索引", "bge-small-zh · 512 维")

arrow([(310, 195), (345, 195)])
arrow([(600, 195), (635, 195)])
arrow([(900, 180), (965, 145)])
arrow([(900, 215), (965, 285)])

# Online lane
box(80, 500, 270, 110, "用户问题", "中文自然语言提问")
box(400, 500, 270, 110, "检索路由", "BM25 / 向量 可切换")
box(730, 500, 280, 110, "Top-K 片段", "附文档名与片段号")
box(1080, 490, 330, 130, "拒答闸门", "向量 0.40 / BM25 0.30", accent=True)
arrow([(350, 555), (395, 555)])
arrow([(670, 555), (725, 555)])
arrow([(1010, 555), (1075, 555)])
label(805, 455, "选中一路检索结果")

# Generation branch
box(1090, 720, 310, 110, "LLM 生成", "只用资料 · 强制引用")
box(1450, 720, 300, 110, "回答", "文档名 + 原文片段")
box(1450, 490, 300, 110, "明确拒答", "文档中没有相关信息", accent=True)
arrow([(1245, 620), (1245, 715)])
arrow([(1400, 775), (1445, 775)])
arrow([(1410, 545), (1445, 545)])

label(1150, 652, "资料足够")
label(1320, 450, "资料不足")
label(60, 920, "图注：检索是 1，生成是后面的 0；加粗框为两层拒答中的检索闸门与最终拒答。")

image.save(OUT, "PNG", optimize=True)
print(OUT)
