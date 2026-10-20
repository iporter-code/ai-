"""跑一遍演示用的真实问答，把输出与时间戳记下来，供 build_demo_video.py 出片。

不伪造任何内容：问题、检索结果、模型输出、首 token 与总耗时全部来自本机真实运行，
包括两道陷阱题的真实拒答。产物：
  docs/demo_run.json  结构化日志（含逐字时间戳）
  docs/demo_run.log   纯文本日志（可直接 grep 复核）

用法：
    python scripts/record_demo.py            # 5 道题，Pollinations 免费接口
    python scripts/record_demo.py --sleep 0  # 付费/本地接口可去掉限速等待
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.corpus import load_chunks  # noqa: E402
from app.rag import answer_question, format_result  # noqa: E402
from app.retrievers import load_retriever  # noqa: E402

JSON_PATH = ROOT / "docs" / "demo_run.json"
LOG_PATH = ROOT / "docs" / "demo_run.log"

# 与 eval/questions.jsonl 一致：2 道多跳/文档题 + 2 道陷阱题（含 1 道闸门拒答）
STEPS = [
    ("q14", "vector", "向量检索演示：跨两篇文档的多跳题"),
    ("q10", "bm25", "关键词检索演示：命令类精确命中"),
    ("q13", "bm25", "跨文档对比：两种检索的弱点与命中率"),
    ("q19", "vector", "陷阱题 A：资料没有 Chroma 版本号（生成层拒答）"),
    ("q18", "vector", "陷阱题 B：资料没有莫干山内容（检索闸门拒答）"),
]


def _questions() -> dict[str, dict]:
    rows = {}
    for line in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def _run_info() -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "info"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "kind": "command",
        "cmd": "python -m app.cli info",
        "output": (proc.stdout or "").strip().splitlines(),
        "elapsed": round(time.perf_counter() - started, 2),
    }


def _run_question(qid: str, mode: str, note: str, settings, chunks, cache) -> dict:
    row = _questions()[qid]
    question = row["question"]
    retriever = cache.get(mode)
    if retriever is None:
        retriever = load_retriever(mode, chunks, settings)
        cache[mode] = retriever

    deltas: list[list] = []
    started = time.perf_counter()

    def on_delta(piece: str) -> None:
        deltas.append([round(time.perf_counter() - started, 3), piece])

    result = answer_question(question, retriever, settings, on_delta=on_delta)
    elapsed = round(time.perf_counter() - started, 3)
    formatted = format_result(result)

    return {
        "kind": "qa",
        "id": qid,
        "note": note,
        "type": row["type"],
        "question": question,
        "mode": mode,
        "mode_label": retriever.label,
        "formatted": formatted,
        "answer": result.answer,
        "refused": result.refused,
        "refusal_reason": result.refusal_reason,
        "from_gate": result.from_gate,
        "citations": len(result.citations),
        "first_token_s": None if result.first_token_s is None else round(result.first_token_s, 3),
        "latency_s": round(result.latency_s, 3),
        "elapsed": elapsed,
        "deltas": deltas,
        "retrieved": [
            {
                "doc": candidate.chunk.doc_id,
                "chunk": candidate.chunk.chunk_index + 1,
                "score": round(float(candidate.score), 3),
            }
            for candidate in result.retrieved
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="录制演示用的真实问答输出")
    parser.add_argument("--sleep", type=int, default=32, help="两次 LLM 调用之间的等待秒数")
    args = parser.parse_args()

    settings = get_settings()
    chunks = load_chunks(settings.chunks_path)
    docs = {chunk.doc_id for chunk in chunks}
    print(f"索引：{len(docs)} 个文档 / {len(chunks)} 个片段")

    steps: list[dict] = [_run_info()]
    cache: dict[str, object] = {}
    log_lines: list[str] = []

    for index, (qid, mode, note) in enumerate(STEPS):
        if index and args.sleep:
            print(f"等待 {args.sleep}s，避免免费接口限流……")
            time.sleep(args.sleep)
        print(f"[{index + 1}/{len(STEPS)}] {qid} · {mode} · {note}")
        step = _run_question(qid, mode, note, settings, chunks, cache)
        steps.append(step)
        state = "拒答" if step["refused"] else f"{step['citations']} 条引用"
        print(
            f"    首字 {step['first_token_s']}s / 总耗时 {step['latency_s']}s · {state}"
        )
        log_lines.append(
            f"### {qid} [{mode}] {note}\n问：{step['question']}\n{step['formatted']}\n"
            f"首字 {step['first_token_s']}s · 总耗时 {step['latency_s']}s · "
            f"拒答={step['refused']} · 闸门={step['from_gate']}\n"
        )

    payload = {
        "recorded_at": time.strftime("%Y-%m-%d %H:%M"),
        "docs": len(docs),
        "chunks": len(chunks),
        "llm_model": settings.llm_model,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "vector_min_score": settings.vector_min_score,
        "bm25_min_coverage": settings.bm25_min_coverage,
        "steps": steps,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG_PATH.write_text(
        f"演示录制日志（{payload['recorded_at']}，{len(docs)} 文档 / {len(chunks)} 片段）\n\n"
        + "\n".join(log_lines),
        encoding="utf-8",
    )
    print(f"已写入 {JSON_PATH.relative_to(ROOT)} 和 {LOG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
