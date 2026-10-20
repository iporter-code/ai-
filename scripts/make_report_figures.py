"""生成报告用的插图：从 demo_run.json 渲染两张终端画面并拼成 fig_screen.png。

与视频帧不同，这里按报告版面（A4 正文宽度约 16.5cm）直接确定像素尺寸，
文字不经过缩放，打印出来才清楚。内容仍全部来自 docs/demo_run.json 的真实运行。

用法：
    python scripts/make_report_figures.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RUN_JSON = ROOT / "docs" / "demo_run.json"
OUT = ROOT / "docs" / "report_shots" / "fig_screen.png"

FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")

PANEL_W, PAD = 815, 22
FONT_SIZE, LINE_H = 20, 30
GAP = 12

BG = (12, 15, 21)
FG = (228, 234, 241)
DIM = (140, 149, 159)
GREEN = (127, 216, 138)
BLUE = (96, 170, 255)
ORANGE = (240, 140, 70)
CYAN = (86, 182, 194)

_CHAR_MAP = {"\u202f": " ", "\u00a0": " ", "\u2009": " ", "\u2011": "-", "\u2013": "-"}


def normalize(text: str) -> str:
    for bad, good in _CHAR_MAP.items():
        text = text.replace(bad, good)
    return text


def strip_md(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.replace("```", "")


def wrap(text: str, font, limit: int) -> list[str]:
    """按像素宽度折行，避免中英混排时溢出面板。"""
    if not text:
        return [""]
    lines, cur = [], ""
    for ch in text:
        if font.getlength(cur + ch) > limit and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def color_of(line: str) -> tuple[int, int, int]:
    plain = strip_md(line)
    if plain.startswith("引用来源"):
        return BLUE
    if plain.startswith("文档中没有相关信息"):
        return ORANGE
    if plain.startswith(("[1]", "[2]", "[3]", "[4]")):
        return CYAN
    if plain.startswith((">", "拒答判定", "首字")):
        return DIM
    if plain.startswith("检索详情") or re.match(r"^\s+\d\.", plain):
        return DIM
    return FG


def build_panel(label: str, body_lines: list[str], width: int, height: int | None = None) -> Image.Image:
    font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
    small = ImageFont.truetype(str(FONT_PATH), 17)
    inner = width - PAD * 2

    rendered: list[tuple[str, tuple[int, int, int]]] = []
    for raw in body_lines:
        plain = strip_md(raw)
        if plain.strip() == "---":
            continue
        for seg in wrap(plain, font, inner):
            rendered.append((seg, color_of(raw)))

    height = max(height or 0, PAD * 2 + 34 + LINE_H * len(rendered))
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 34], fill=(24, 29, 37))
    draw.text((PAD, 8), label, font=small, fill=GREEN)
    y = 34 + PAD
    for text, color in rendered:
        draw.text((PAD, y), text, font=font, fill=color)
        y += LINE_H
    return img


def qa_lines(step: dict, max_citations: int | None = None, with_retrieval: bool = True) -> list[str]:
    """把一次真实运行排成终端行；max_citations 用来在版面不够时只留首条引用。"""
    out = [f'PS> python -m app.cli ask "{step["question"]}" --mode {step["mode"]}']

    body = step["formatted"].split("\n")
    if max_citations is not None:
        # 引用块形如：[n] `文档`（片段 i） + 若干 > 原文行，按 "[n]" 头切分
        head, blocks = [], []
        for line in body:
            if re.match(r"^\[\d+\]", line.strip()):
                blocks.append([line])
            elif blocks:
                blocks[-1].append(line)
            else:
                head.append(line)
        kept = blocks[:max_citations]
        out.extend(head)
        for block in kept:
            out.extend(block)
        dropped = blocks[max_citations:]
        if dropped:
            names = []
            for block in dropped:
                match = re.match(r"^\[(\d+)\]\s*([^（(]+)", strip_md(block[0]))
                if match:
                    names.append(f"片段 {match.group(2).strip()}")
            out.append(f"（另有 {len(dropped)} 条引用，见 demo_run.log）")
    else:
        out.extend(body)

    tail = f'首字 {step["first_token_s"]:.2f}s · 总耗时 {step["latency_s"]:.2f}s · {step["mode_label"]}'
    out.extend(["", tail])
    if with_retrieval:
        out.extend(["", f"检索详情 Top-{len(step['retrieved'])}"])
        for rank, item in enumerate(step["retrieved"], start=1):
            out.append(f"  {rank}. {item['doc']} 片段{item['chunk']}  分数 {item['score']:.3f}")
    return out


def main() -> int:
    run = json.loads(RUN_JSON.read_text(encoding="utf-8"))
    steps = {step["id"]: step for step in run["steps"] if step["kind"] == "qa"}

    # 左：q14 向量多跳（留首条引用）；右：q18 陷阱题，被检索闸门当场拒答
    left_step, right_step = steps["q14"], steps["q18"]
    left_lines = qa_lines(left_step, max_citations=1, with_retrieval=False)
    right_lines = qa_lines(right_step)

    left = build_panel(
        f'q14 · 向量检索 · {left_step["citations"]} 条引用 · 首字 {left_step["first_token_s"]:.1f}s',
        left_lines,
        PANEL_W,
    )
    right = build_panel(
        f'q18 · 陷阱题 · 检索闸门拒答 · {right_step["latency_s"]:.2f}s',
        right_lines,
        PANEL_W,
    )

    height = max(left.height, right.height)
    left = build_panel(
        f'q14 · 向量检索 · {left_step["citations"]} 条引用 · 首字 {left_step["first_token_s"]:.1f}s',
        left_lines,
        PANEL_W,
        height,
    )
    right = build_panel(
        f'q18 · 陷阱题 · 检索闸门拒答 · {right_step["latency_s"]:.2f}s',
        right_lines,
        PANEL_W,
        height,
    )

    canvas = Image.new("RGB", (PANEL_W * 2 + GAP, height), (255, 255, 255))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (PANEL_W + GAP, 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print(f"已写入 {OUT.relative_to(ROOT)}：{canvas.size[0]}×{canvas.size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
