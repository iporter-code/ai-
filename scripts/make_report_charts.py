"""从 eval/results 的真实数据画报告用的图表（PIL 手绘，不依赖 matplotlib）。

产物：
    docs/report_shots/fig_metrics.png   两种检索四项指标对比 + 延迟对比
    docs/report_shots/fig_latency.png   20 题逐题首 token 延迟

用法：
    python scripts/make_report_charts.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score import summarize as official_summary  # noqa: E402

RESULTS = ROOT / "eval" / "results"
SHOTS = ROOT / "docs" / "report_shots"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")

INK = (32, 38, 48)
MUTED = (110, 120, 132)
GRID = (226, 231, 237)
BM25 = (76, 120, 168)
VECTOR = (232, 138, 66)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def load_rows(name: str) -> list[dict]:
    path = RESULTS / name
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def summary(mode: str) -> dict:
    """直接复用 score.py 的口径，避免图表和 metrics.md 出现两套数字。"""
    rows = load_rows(f"results_{mode}.csv")
    s = official_summary(rows)
    return {
        "acc": (s["accuracy"] or 0) * 100,
        "halluc": (s["hallucination_rate"] or 0) * 100,
        "hit3": (s["hit_rate"] or 0) * 100,
        "cite": (s["citation_rate"] or 0) * 100,
        "first": s["avg_first_token"] or 0,
        "e2e": s["avg_latency"] or 0,
    }


def draw_grouped(draw, box, groups, series, colors, ymax, fmt="{:.0f}%", unit=""):
    """在 box=(x, y, w, h) 内画分组柱状图。"""
    x0, y0, w, h = box
    left, bottom = x0 + 46, y0 + h - 34
    plot_w, plot_h = w - 60, h - 44

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = bottom - plot_h * frac
        draw.line([(left, y), (left + plot_w, y)], fill=GRID, width=1)
        draw.text((x0, y - 8), f"{ymax * frac:.0f}{unit}", font=font(15), fill=MUTED)

    n = len(groups)
    group_w = plot_w / n
    bar_w = min(44.0, group_w / (len(series) + 1.3))
    for gi, label in enumerate(groups):
        gx = left + group_w * gi + group_w / 2
        for si, values in enumerate(series):
            value = values[gi]
            bh = plot_h * (value / ymax) if ymax else 0
            bx = gx - (len(series) * bar_w) / 2 + si * bar_w + 3
            draw.rectangle(
                [bx, bottom - bh, bx + bar_w - 6, bottom], fill=colors[si]
            )
            text = fmt.format(value)
            tw = draw.textlength(text, font=font(14))
            draw.text((bx + (bar_w - 6 - tw) / 2, bottom - bh - 20), text,
                      font=font(14), fill=INK)
        lw = draw.textlength(label, font=font(16))
        draw.text((gx - lw / 2, bottom + 8), label, font=font(16), fill=INK)

    draw.line([(left, bottom), (left + plot_w, bottom)], fill=(150, 160, 172), width=1)


def chart_metrics(bm: dict, vec: dict) -> Image.Image:
    W, H = 1642, 390
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 左：四项比率
    groups = ["答案正确率", "幻觉率", "Top-3 命中率", "引用给出率"]
    series = [
        [bm["acc"], bm["halluc"], bm["hit3"], bm["cite"]],
        [vec["acc"], vec["halluc"], vec["hit3"], vec["cite"]],
    ]
    draw_grouped(draw, (30, 16, 900, 350), groups, series, [BM25, VECTOR], 100)

    # 右：延迟
    groups2 = ["首 token", "端到端"]
    series2 = [[bm["first"], bm["e2e"]], [vec["first"], vec["e2e"]]]
    draw_grouped(
        draw, (960, 16, 320, 350), groups2, series2, [BM25, VECTOR],
        12, fmt="{:.1f}", unit="s",
    )

    # 图例
    lx = 1330
    for i, (name, color) in enumerate([("BM25", BM25), ("向量检索", VECTOR)]):
        y = 120 + i * 34
        draw.rectangle([lx, y, lx + 18, y + 18], fill=color)
        draw.text((lx + 26, y - 2), name, font=font(17), fill=INK)
    draw.text((lx, 210), "语料 3 篇 / 32 片段", font=font(15), fill=MUTED)
    draw.text((lx, 234), "题目 10 文档 + 5 多跳 + 5 陷阱", font=font(15), fill=MUTED)
    draw.text((lx, 258), "延迟为本机含免费接口排队", font=font(15), fill=MUTED)
    return img


def chart_latency(bm_rows: list[dict], vec_rows: list[dict]) -> Image.Image:
    W, H = 1642, 340
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    left, bottom = 80, H - 46
    plot_w, plot_h = W - 130, H - 96
    vmax = 22.0
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = bottom - plot_h * frac
        draw.line([(left, y), (left + plot_w, y)], fill=GRID)
        draw.text((26, y - 8), f"{vmax * frac:.0f}s", font=font(14), fill=MUTED)

    n = len(bm_rows)
    step = plot_w / n
    bar = step * 0.34
    for i in range(n):
        pair = [(bm_rows[i], left + step * i + step * 0.12, BM25),
                (vec_rows[i], left + step * i + step * 0.12 + bar, VECTOR)]
        for row, x, color in pair:
            v = float(row["first_token_s"] or 0)
            bh = plot_h * min(v, vmax) / vmax
            draw.rectangle([x, bottom - bh, x + bar - 3, bottom], fill=color)
        label = bm_rows[i]["id"]
        lw = draw.textlength(label, font=font(13))
        draw.text((left + step * i + step / 2 - lw / 2, bottom + 8), label,
                  font=font(13), fill=MUTED)

    draw.line([(left, bottom), (left + plot_w, bottom)], fill=(150, 160, 172))

    lx = 90
    for i, (name, color) in enumerate([("BM25", BM25), ("向量检索", VECTOR)]):
        x = lx + i * 140
        draw.rectangle([x, 44, x + 16, 58], fill=color)
        draw.text((x + 24, 41), name, font=font(15), fill=INK)
    return img


def main() -> int:
    bm = summary("bm25")
    vec = summary("vector")
    SHOTS.mkdir(parents=True, exist_ok=True)

    chart_metrics(bm, vec).save(SHOTS / "fig_metrics.png")
    chart_latency(load_rows("results_bm25.csv"), load_rows("results_vector.csv")).save(
        SHOTS / "fig_latency.png"
    )
    print("已生成 fig_metrics.png / fig_latency.png")
    print(
        "BM25  正确率 %.0f%% 幻觉率 %.0f%% 命中率 %.0f%% 首字 %.2fs"
        % (bm["acc"], bm["halluc"], bm["hit3"], bm["first"])
    )
    print(
        "向量  正确率 %.0f%% 幻觉率 %.0f%% 命中率 %.0f%% 首字 %.2fs"
        % (vec["acc"], vec["halluc"], vec["hit3"], vec["first"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
