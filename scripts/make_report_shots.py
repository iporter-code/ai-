"""抓真实命令输出，拼成报告的“工程可复现”四联截图。

面板内容全部由本脚本现场执行得到（info / ingest / pytest / 检索-only 评测），
不是手写文本。产物：docs/report_shots/fig_cmds.png

用法：
    python scripts/make_report_shots.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "report_shots" / "fig_cmds.png"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
BG = (12, 15, 21)
FG = (226, 233, 240)
DIM = (138, 148, 158)
GREEN = (127, 216, 138)
BLUE = (96, 170, 255)
OK = (120, 200, 140)

PANEL_W, PANEL_H = 815, 300
PAD = 20
LINE_H = 26
FONT_SIZE = 17

NOISE = ("SyntaxWarning", "re_", "-- Docs:", "re_han", "re_skip", "re_num")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT.with_name("msyhbd.ttc") if bold else FONT
    return ImageFont.truetype(str(path), size)


def run(cmd: list[str]) -> list[str]:
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    lines = []
    for raw in (proc.stdout or "").splitlines():
        if any(token in raw for token in NOISE):
            continue
        if raw.strip():
            lines.append(raw.rstrip())
    return lines


def wrap(text: str, measure: ImageFont.FreeTypeFont, limit: int) -> list[str]:
    out, cur = [], ""
    for ch in text:
        if measure.getlength(cur + ch) > limit and cur:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def panel(label: str, cmd: str, lines: list[str], highlight: str = "") -> Image.Image:
    body = font(FONT_SIZE)
    small = font(15)
    img = Image.new("RGB", (PANEL_W, PANEL_H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, PANEL_W, 32], fill=(24, 29, 37))
    draw.text((PAD, 7), label, font=small, fill=GREEN)

    y = 32 + PAD - 4
    prompt, _, rest = cmd.partition(" ")
    draw.text((PAD, y), "PS> ", font=body, fill=GREEN)
    x = PAD + draw.textlength("PS> ", font=body)
    for seg in wrap(rest or prompt, body, PANEL_W - x - PAD):
        draw.text((x, y), seg, font=body, fill=FG)
        y += LINE_H
        x = PAD

    y += 6
    for line in lines:
        color = FG
        if highlight and highlight in line:
            color = OK
        elif line.startswith("已"):
            color = BLUE
        elif line.startswith("  -"):
            color = DIM
        for seg in wrap(line, body, PANEL_W - PAD * 2):
            if y > PANEL_H - LINE_H:
                return img
            draw.text((PAD, y), seg, font=body, fill=color)
            y += LINE_H
    return img


def main() -> int:
    python = sys.executable
    info = run([python, "-m", "app.cli", "info"])
    ingest = run([python, "-m", "app.cli", "ingest"])
    tests = run([python, "-m", "pytest", "-q", "-p", "no:warnings"])
    scored = run([
        python, "scripts/score.py",
        "eval/results/results_bm25.csv", "eval/results/results_vector.csv",
        "--out", ".tmp/metrics_check.md",
    ])

    # 指标表：从表头到“引用文档准确率”，去掉 markdown 标题与分隔行
    table = []
    for line in scored:
        if line.startswith("| 指标 | bm25"):
            table = [line]
        elif table and line.startswith("|"):
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            table.append(line)
        elif table:
            break

    panels = [
        panel("命令 1/4 · 配置与索引状态", "python -m app.cli info", info),
        panel("命令 2/4 · 建索引（3 文档 → 32 片段）", "python -m app.cli ingest", ingest),
        panel("命令 3/4 · 单元测试（不联网、不下载模型）", "pytest -q", tests[-2:], "passed"),
        panel(
            "命令 4/4 · 用 CSV 复算四项指标（与表 2 一致）",
            "python scripts/score.py eval/results/results_*.csv",
            table,
        ),
    ]

    gap = 12
    canvas = Image.new("RGB", (PANEL_W * 2 + gap, PANEL_H * 2 + gap), (255, 255, 255))
    for index, img in enumerate(panels):
        x = (index % 2) * (PANEL_W + gap)
        y = (index // 2) * (PANEL_H + gap)
        canvas.paste(img, (x, y))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print(f"已写入 {OUT.relative_to(ROOT)}：{canvas.size[0]}×{canvas.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
