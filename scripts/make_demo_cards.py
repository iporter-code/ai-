from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo_cards"
OUT.mkdir(exist_ok=True)
FONT = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

W, H = 1920, 1080
BG = "#0f172a"
ACCENT = "#38bdf8"
WHITE = "#f8fafc"
MUTED = "#94a3b8"


def card(name, title, rows, footer=""):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_BOLD, 66)
    row_font = ImageFont.truetype(FONT, 40)
    small_font = ImageFont.truetype(FONT, 30)
    draw.rectangle((0, 0, W, 12), fill=ACCENT)
    draw.text((100, 90), title, font=title_font, fill=WHITE)
    draw.line((100, 190, 1820, 190), fill="#334155", width=3)
    y = 250
    for label, value, color in rows:
        draw.text((110, y), label, font=row_font, fill=color)
        draw.text((620, y), value, font=row_font, fill=WHITE)
        y += 92
    if footer:
        draw.text((100, 940), footer, font=small_font, fill=MUTED)
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    print(path)


card(
    "metrics.png",
    "20 题正式评测",
    [
        ("BM25 正确率", "100%  (20/20)", ACCENT),
        ("向量 正确率", "95%  (19/20)", ACCENT),
        ("幻觉率（5 陷阱）", "BM25 0%  /  向量 0%", "#86efac"),
        ("Top-3 命中率", "BM25 86.7%  /  向量 93.3%", "#fbbf24"),
        ("首 token 延迟", "BM25 13.36 s  /  向量 10.96 s", "#fbbf24"),
    ],
    "口径：答案正确率含陷阱题正确拒答；检索命中按 evidence 片段判断；延迟为本机实测。",
)

card(
    "lessons.png",
    "三个结论",
    [
        ("1  检索是 1", "生成是后面的 0，证据不硬，回答就没有意义", ACCENT),
        ("2  高命中 ≠ 高正确", "向量 q11 的 Top-3 更全，却仍把“包含”判成“不一致”", "#fbbf24"),
        ("3  拒答要两层", "分数闸门挡域外问题，生成约束挡“词面相关但答不了”", "#86efac"),
    ],
    "完整代码、20 题 CSV/JSONL、metrics.md 和实验报告见仓库。",
)
