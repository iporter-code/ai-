"""把 record_demo.py 录到的真实运行记录渲染成 3–5 分钟演示视频。

画面是终端样式的回放，但每个字符都来自真实运行：
命令逐字敲出、等待时长用实测的首 token / 总耗时、答案整块落屏（与 CLI 行为一致）。
页脚常驻“真实运行回放 + 日期 + 模型”，避免被当成合成演示。

用法：
    python scripts/build_demo_video.py               # 输出 docs/演示录屏.mp4
    python scripts/build_demo_video.py --fps 30
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RUN_JSON = ROOT / "docs" / "demo_run.json"
OUT_PATH = ROOT / "docs" / "演示录屏.mp4"
FFMPEG = ROOT / ".tools" / "ffmpeg-win-x86_64-v7.1.exe"

W, H = 1920, 1080
FPS = 30

FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD_PATH = Path("C:/Windows/Fonts/msyhbd.ttc")

BG = (11, 14, 20)
BAR = (22, 27, 34)
FG = (230, 237, 243)
DIM = (139, 148, 158)
GREEN = (127, 216, 138)
BLUE = (88, 166, 255)
ORANGE = (240, 136, 62)
YELLOW = (210, 168, 255)
CYAN = (86, 182, 194)

PAD_X = 84
TOP = 132
LINE_H = 46
FONT_SIZE = 30

chars_per_sec = 17.0  # 敲命令的手速


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold and FONT_BOLD_PATH.exists() else FONT_PATH
    return ImageFont.truetype(str(path), size)


FONT = _font(FONT_SIZE)
FONT_SMALL = _font(20)
FONT_BAR = _font(21)
FONT_TITLE = _font(64, bold=True)
FONT_SUB = _font(30)
FONT_BIG = _font(40, bold=True)

MAX_W = W - PAD_X * 2


def visible_len(text: str) -> int:
    """中文按 2 个宽度算，用来粗略判断折行。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def wrap(text: str, width_units: int = 112) -> list[str]:
    if not text:
        return [""]
    out, cur = [], ""
    for ch in text:
        cur += ch
        if visible_len(cur) >= width_units:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


_CHAR_MAP = {
    "\u202f": " ",  # narrow no-break space：msyh 无字形，会显示成方块
    "\u00a0": " ",
    "\u2009": " ",
    "\u2011": "-",  # non-breaking hyphen
    "\u2013": "-",
    "\u2014": "—",
    "\ufeff": "",
}


def normalize(text: str) -> str:
    for bad, good in _CHAR_MAP.items():
        text = text.replace(bad, good)
    return text


def strip_md(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def classify(line: str) -> tuple[str, tuple[int, int, int]]:
    plain = strip_md(line)
    if not plain.strip():
        return "", FG
    if plain.strip() in {"```", "---"}:
        return "─" * 40, (60, 68, 78)
    if plain.startswith("引用来源"):
        return plain, BLUE
    if plain.startswith("文档中没有相关信息"):
        return plain, ORANGE
    if plain.startswith("拒答判定"):
        return plain, DIM
    if plain.startswith(">"):
        return plain, DIM
    if plain.startswith("["):
        return plain, CYAN
    return plain, FG


class Screen:
    """滚动终端缓冲。"""

    def __init__(self) -> None:
        self.lines: list[tuple[str, tuple[int, int, int]]] = []
        self.max_lines = (H - TOP - 96) // LINE_H

    def push(self, text: str, color: tuple[int, int, int] = FG) -> None:
        for piece in text.split("\n"):
            for seg in wrap(piece):
                self.lines.append((seg, color))
        self._trim()

    def _push_line(self, raw: str, color: tuple[int, int, int] | None = None) -> None:
        plain, auto = classify(raw)
        chosen = color or auto
        if not plain and not raw.strip():
            self.lines.append(("", FG))
        else:
            for seg in wrap(plain):
                self.lines.append((seg, chosen))
        self._trim()

    def _trim(self) -> None:
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines:]

    def clear(self) -> None:
        self.lines = []


def draw_base(img: Image.Image, draw: ImageDraw.ImageDraw, meta: dict, step_label: str) -> None:
    draw.rectangle([0, 0, W, 64], fill=BAR)
    draw.text((PAD_X, 20), "RAG DEMO", font=FONT_BAR, fill=GREEN)
    draw.text(
        (PAD_X + 128, 20),
        "不瞎编的私有知识库问答助手 · 终端演示",
        font=FONT_BAR,
        fill=DIM,
    )
    right = f"{meta['docs']} 文档 / {meta['chunks']} 片段"
    draw.text((W - PAD_X - draw.textlength(right, font=FONT_BAR), 20), right, font=FONT_BAR, fill=DIM)

    draw.rectangle([0, H - 58, W, H], fill=BAR)
    foot = f"真实运行回放 · {meta['recorded_at']} · 模型 {meta['llm_model']} · 每条命令与输出均来自本机实际执行"
    draw.text((PAD_X, H - 42), foot, font=FONT_SMALL, fill=DIM)
    if step_label:
        draw.text((W - PAD_X - draw.textlength(step_label, font=FONT_SMALL), H - 42), step_label, font=FONT_SMALL, fill=DIM)


def draw_status(draw: ImageDraw.ImageDraw, text: str, y: int, color=CYAN) -> None:
    draw.text((PAD_X, y), text, font=FONT, fill=color)


def render_terminal(screen: Screen, meta: dict, step_label: str, prompt: str, command: str,
                    typed: int, status: str, cursor: bool) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_base(img, draw, meta, step_label)

    y = TOP
    for text, color in screen.lines:
        if y > H - 90:
            break
        draw.text((PAD_X, y), text, font=FONT, fill=color)
        y += LINE_H

    if command:
        draw.text((PAD_X, y), prompt, font=FONT, fill=GREEN)
        cx = PAD_X + draw.textlength(prompt, font=FONT)
        shown = command[:typed]
        draw.text((cx, y), shown, font=FONT, fill=FG)
        if cursor:
            wpx = draw.textlength(shown, font=FONT)
            draw.rectangle([cx + wpx + 2, y + 6, cx + wpx + 18, y + FONT_SIZE + 10], fill=(200, 210, 220))

    if status:
        draw_status(draw, status, H - 108)
    return img


def render_card(title: str, lines: list[str], meta: dict, footer: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_base(img, draw, meta, "")

    y = 300
    tw = draw.textlength(title, font=FONT_TITLE)
    draw.text(((W - tw) / 2, y), title, font=FONT_TITLE, fill=FG)
    y += 120
    for line in lines:
        lw = draw.textlength(line, font=FONT_SUB)
        draw.text(((W - lw) / 2, y), line, font=FONT_SUB, fill=DIM)
        y += 56
    if footer:
        fw = draw.textlength(footer, font=FONT_SUB)
        draw.text(((W - fw) / 2, H - 200), footer, font=FONT_SUB, fill=GREEN)
    return img


class FrameSink:
    """把 BGR 帧写进 mp4。

    ffmpeg 读写文件被本机安全策略拦住（只能走标准输入输出），所以这里用管道：
    Python 写 rawvideo 到 stdin，ffmpeg 把 mp4 从 stdout 吐回来，由 Python 落盘。
    """

    def __init__(self, out_path: Path, fps: int) -> None:
        self.file = open(out_path, "wb")
        cmd = [
            str(FFMPEG), "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4", "pipe:1",
        ]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self._drainer = threading.Thread(target=self._drain, daemon=True)
        self._drainer.start()

    def _drain(self) -> None:
        assert self.proc.stdout is not None
        while True:
            chunk = self.proc.stdout.read(1 << 20)
            if not chunk:
                break
            self.file.write(chunk)

    def write(self, frame: np.ndarray) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(frame.tobytes())

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        code = self.proc.wait(timeout=600)
        self._drainer.join(timeout=60)
        self.file.close()
        if code != 0:
            err = self.proc.stderr.read().decode("utf-8", "replace") if self.proc.stderr else ""
            raise RuntimeError(f"ffmpeg 退出码 {code}：{err[-400:]}")


class Cv2Sink:
    """用 OpenCV 写普通（非分片）mp4：文件由 Python 进程打开，能正常记录时长。"""

    def __init__(self, out_path: Path, fps: int) -> None:
        import cv2

        self.writer = cv2.VideoWriter(
            str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H)
        )
        if not self.writer.isOpened():
            raise RuntimeError("OpenCV 无法创建视频文件")

    def write(self, frame: np.ndarray) -> None:
        self.writer.write(frame)

    def close(self) -> None:
        self.writer.release()


def make_sink(out_path: Path, fps: int, encoder: str):
    if encoder == "cv2":
        return Cv2Sink(out_path, fps)
    if encoder == "ffmpeg":
        return FrameSink(out_path, fps)
    try:  # auto：优先 OpenCV（普通 mp4），退回复用管道编码
        return Cv2Sink(out_path, fps)
    except Exception:
        return FrameSink(out_path, fps)


def patch_frag_duration(path: Path, seconds: float) -> None:
    """分片 mp4 的 mvhd/tkhd/mdhd 时长是 0（ffmpeg 边生成边写，不知道总长）。

    这里按已知总时长把这三个字段补上，播放器与资源管理器就能显示正确长度。
    字段偏移按 ISO/IEC 14496-12 的 v0 布局：version+flags 占 8..12，
    creation 12、modification 16、timescale 20、duration 24（mdhd 多一个 language）。
    """
    data = bytearray(path.read_bytes())

    def children(start: int, end: int):
        off = start
        while off + 8 <= end:
            size = int.from_bytes(data[off:off + 4], "big")
            kind = bytes(data[off + 4:off + 8])
            if size < 8 or off + size > end:
                return
            yield kind, off, size
            off += size

    boxes = {kind: (off, size) for kind, off, size in children(0, len(data))}
    if b"moov" not in boxes:
        return
    moov_off, moov_size = boxes[b"moov"]

    def set_duration(box_off: int, timescale_off: int | None, duration_off: int, scale: int) -> None:
        if data[box_off + 8] != 0:  # v1 用 64 位字段，这里只处理 v0
            return
        if timescale_off is None:  # tkhd 没有自己的 timescale，用 mvhd 的
            timescale = scale
        else:
            timescale = int.from_bytes(
                data[box_off + timescale_off:box_off + timescale_off + 4], "big"
            ) or scale
        value = int(round(seconds * timescale))
        data[box_off + duration_off:box_off + duration_off + 4] = value.to_bytes(4, "big")

    for kind, off, size in children(moov_off + 8, moov_off + moov_size):
        if kind == b"mvhd":
            set_duration(off, 20, 24, 1000)
            movie_scale = int.from_bytes(data[off + 20:off + 24], "big") or 1000
            break
    else:
        return

    for kind, off, size in children(moov_off + 8, moov_off + moov_size):
        if kind != b"trak":
            continue
        for sub, sub_off, sub_size in children(off + 8, off + size):
            if sub == b"tkhd":
                set_duration(sub_off, None, 28, movie_scale)
            elif sub == b"mdia":
                for leaf, leaf_off, leaf_size in children(sub_off + 8, sub_off + sub_size):
                    if leaf == b"mdhd":
                        set_duration(leaf_off, 20, 24, movie_scale)

    path.write_bytes(bytes(data))


def build(run: dict, out_path: Path, fps: int, encoder: str = "auto") -> float:
    meta = {
        "recorded_at": run["recorded_at"],
        "docs": run["docs"],
        "chunks": run["chunks"],
        "llm_model": run["llm_model"],
    }

    sink = make_sink(out_path, fps, encoder)
    screen = Screen()
    frames = 0
    total_s = 0.0

    def emit(image: Image.Image, seconds: float) -> None:
        nonlocal frames, total_s
        n = max(1, int(round(seconds * fps)))
        arr = np.asarray(image, dtype=np.uint8)[:, :, ::-1]  # RGB -> BGR
        arr = np.ascontiguousarray(arr)
        for _ in range(n):
            sink.write(arr)
        frames += n
        total_s += n / fps

    qa_steps = [step for step in run["steps"] if step["kind"] == "qa"]
    info_step = next(step for step in run["steps"] if step["kind"] == "command")

    # 片头
    emit(
        render_card(
            "不瞎编的私有知识库问答助手",
            [
                f"语料 {meta['docs']} 篇 · {meta['chunks']} 个片段 · 两种检索可运行时切换",
                "答案标注「文档名 + 片段号 + 原文」；资料不足时明确拒答",
                "",
                "接下来：索引信息 → 2 道文档/多跳题 → 2 道陷阱题（应当拒答）",
            ],
            meta,
            footer=f"录制时间 {meta['recorded_at']}",
        ),
        9.0,
    )
    emit(
        render_card(
            "本次演示的 5 个问题",
            [
                f"q14  向量  {qa_steps[0]['question']}",
                f"q10  BM25  {qa_steps[1]['question']}",
                f"q13  BM25  {qa_steps[2]['question']}",
                f"q19  向量  {qa_steps[3]['question']}  ← 陷阱题",
                f"q18  向量  {qa_steps[4]['question']}  ← 陷阱题",
            ],
            meta,
            footer="前 3 道应当答对并给出出处，后 2 道应当明确拒答",
        ),
        8.0,
    )

    prompt = "PS C:\\ai-demo> "
    labels = [f"step {i + 1}/{len(qa_steps) + 1}" for i in range(len(qa_steps) + 1)]

    # 第 1 幕：info
    cmd = info_step["cmd"]
    screen.push("")
    dur = len(cmd) / chars_per_sec
    for i in range(len(cmd) + 1):
        emit(render_terminal(screen, meta, labels[0], prompt, cmd, i, "", True), 1 / chars_per_sec)
    for _ in range(6):
        emit(render_terminal(screen, meta, labels[0], prompt, cmd, len(cmd), "", not _ % 2), 0.12)
    for line in info_step["output"]:
        screen._push_line(line)
        emit(render_terminal(screen, meta, labels[0], prompt, "", 0, "", False), 0.35)
    emit(render_terminal(screen, meta, labels[0], prompt, "", 0, "", True), 4.5)

    # 第 2..N 幕：问答
    for index, step in enumerate(qa_steps):
        label = labels[index + 1]
        mode = step["mode"]
        cmd = normalize(f'python -m app.cli ask "{step["question"]}" --mode {mode}')

        screen.push("", )
        screen.push(f"— {step['note']} " + "─" * max(4, 46 - visible_len(step["note"])), (70, 80, 92))
        emit(render_terminal(screen, meta, label, prompt, "", 0, "", False), 1.2)

        for i in range(len(cmd) + 1):
            emit(render_terminal(screen, meta, label, prompt, cmd, i, "", True), 1 / chars_per_sec)
        emit(render_terminal(screen, meta, label, prompt, cmd, len(cmd), "", False), 0.6)

        first = step["first_token_s"] or step["latency_s"]
        total = max(step["latency_s"], first)

        # 等待阶段：用实测首 token 时间，进度条随时间推进
        wait_frames = max(1, int(round(first * fps * 0.5)))
        per = first / wait_frames
        for i in range(wait_frames):
            elapsed = per * (i + 1)
            dots = "." * (1 + i % 3)
            text = f"▊ 检索完成，等待模型首字{dots}  {elapsed:0.1f}s"
            emit(render_terminal(screen, meta, label, prompt, "", 0, text, False), per)

        rest = max(total - first, 0.8)
        gen_frames = max(1, int(round(rest * fps * 0.5)))
        per_g = rest / gen_frames
        for i in range(gen_frames):
            elapsed = first + per_g * (i + 1)
            dots = "." * (1 + i % 3)
            text = f"▊ 正在生成{dots}  首字 {first:0.1f}s · 已用 {elapsed:0.1f}s"
            emit(render_terminal(screen, meta, label, prompt, "", 0, text, False), per_g)

        # 答案整块落屏（与 CLI 一致）
        screen._push_line("")
        for raw in step["formatted"].split("\n"):
            screen._push_line(raw)
            emit(render_terminal(screen, meta, label, prompt, "", 0, "", False), 0.22)

        tail = f"首字 {first:0.2f}s · 总耗时 {step['latency_s']:.2f}s · {step['mode_label']}"
        screen._push_line("")
        screen._push_line(tail)
        emit(render_terminal(screen, meta, label, prompt, "", 0, "", False), 1.0)

        # 真实检索结果（分数来自本次运行，不是事后补的）
        screen._push_line("")
        screen._push_line(f"检索详情 Top-{len(step['retrieved'])}", (86, 96, 110))
        for rank, item in enumerate(step["retrieved"], start=1):
            screen._push_line(
                f"  {rank}. {item['doc']} 片段{item['chunk']}  分数 {item['score']:.3f}"
            )
            emit(render_terminal(screen, meta, label, prompt, "", 0, "", False), 0.5)
        emit(render_terminal(screen, meta, label, prompt, "", 0, "", True), 9.0)

        if index == 2:
            screen.clear()
        if index == 3:
            screen.clear()
            emit(
                render_card(
                    "接下来两道题，语料里没有答案",
                    [
                        "q19  Chroma 的版本号 —— 日记只提到 chroma，没写版本",
                        "q18  莫干山民宿 —— 语料里完全没有这趟旅行",
                        "",
                        "系统应当回答「文档中没有相关信息」，而不是硬编",
                    ],
                    meta,
                    footer="一道靠提示词拒答，一道被检索闸门当场挡住",
                ),
                7.0,
            )

    # 片尾：指标
    # 片尾：对比与失败案例（数据来自 eval/results/metrics.md 与报告 4.2）
    emit(
        render_card(
            "两种检索各擅长什么",
            [
                "BM25     专有名词、版本号、命令原文 —— q10 的 Set-ExecutionPolicy Top-1 直接命中",
                "向量     语义改写、跨文档多跳 —— q14 同时召回两篇文档的两个片段",
                "",
                "但 20 题里两者正确率都是 90%、Top-3 命中都是 86.7%",
                "检索分数只能保证「材料相关」，不能保证「模型会用」",
            ],
            meta,
            footer="精确事实优先 BM25，口语化/跨片段优先向量",
        ),
        10.0,
    )
    emit(
        render_card(
            "最失败的 case：q17",
            [
                "问：这门课的期末考试安排在几月几日？",
                "",
                "资料里只有「作业 1 于 10 月 21 日截止」，没有期末考试日期",
                "BM25 覆盖率 0.333 过了闸门 → 模型把作业截止日答成了考试日期",
                "",
                "这是「不瞎编」这个目标上唯一一次硬编，幻觉率 20% 就来自这一题",
            ],
            meta,
            footer="根因：近域陷阱 + 缺实体/槽位约束 + 无引用未触发拒答",
        ),
        10.0,
    )
    emit(
        render_card(
            "20 题评测结果",
            [
                "答案正确率    BM25 90%（18/20）    向量 90%（18/20）",
                "幻觉率        BM25 20%（1/5）      向量 0%（0/5）",
                "Top-3 命中    BM25 86.7%           向量 86.7%",
                "首 token      BM25 9.76s           向量 8.77s",
            ],
            meta,
            footer="逐题结果见 eval/results/metrics.md",
        ),
        9.0,
    )
    emit(
        render_card(
            "三个结论",
            [
                "1. 检索是 1，生成是后面的 0 —— 证据进不了上下文，模型再强也没用",
                "2. 高命中不等于高正确 —— q11 证据齐全仍然答错",
                "3. 拒答要两层 —— 阈值挡域外，提示词挡近域陷阱",
            ],
            meta,
            footer="演示结束 · 谢谢观看",
        ),
        9.0,
    )
    emit(
        render_card(
            "怎么复现",
            [
                "python -m app.cli ingest                     # 建索引（3 文档 → 32 片段）",
                "python -m app.cli ask \"问题\" --mode bm25|vector",
                "python -m app.ui                             # Gradio 界面，可运行时切换检索",
                "python scripts/evaluate.py --mode both       # 两种检索各跑 20 题",
                "python -m pytest -q                          # 33 项单测，不联网",
            ],
            meta,
            footer="详见 README.md",
        ),
        9.0,
    )

    sink.close()
    return total_s, "cv2" if isinstance(sink, Cv2Sink) else "ffmpeg"

def main() -> int:
    parser = argparse.ArgumentParser(description="渲染演示视频")
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument(
        "--encoder", choices=["auto", "cv2", "ffmpeg"], default="auto",
        help="auto=cv2 优先（普通 mp4），失败则用 ffmpeg 管道（分片 mp4）",
    )
    args = parser.parse_args()

    if not RUN_JSON.exists():
        print("缺少 docs/demo_run.json，请先运行 python scripts/record_demo.py")
        return 1
    run = json.loads(RUN_JSON.read_text(encoding="utf-8"))

    out = Path(args.out)
    tmp = out.with_name("_demo_render.mp4")  # OpenCV 对中文路径不稳，先写 ASCII 名再改名
    duration, kind = build(run, tmp, args.fps, args.encoder)
    if kind == "ffmpeg":
        patch_frag_duration(tmp, duration)
    if out.exists():
        out.unlink()
    tmp.replace(out)

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"已生成 {out}：{int(duration // 60)}:{int(duration % 60):02d}，{size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
