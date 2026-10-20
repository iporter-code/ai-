import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.corpus import load_chunks  # noqa: E402
from app.rag import answer_question  # noqa: E402
from app.retrievers import load_retriever  # noqa: E402

REQUIRED_FIELDS = {"id", "type", "question", "standard_answer", "source_docs"}
VALID_TYPES = {"doc", "trap", "multi_hop"}


def normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"找不到评测集 {path}。请按 eval/README.md 的格式自己编写 20 道题。"
        )
    questions = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {line_number} 行不是合法 JSON：{exc}") from exc
        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise ValueError(
                f"{path} 第 {line_number} 行缺少字段：{', '.join(sorted(missing))}"
            )
        if item["type"] not in VALID_TYPES:
            raise ValueError(
                f"{path} 第 {line_number} 行 type 必须是 {sorted(VALID_TYPES)} 之一"
            )
        questions.append(item)
    ids = [item["id"] for item in questions]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} 中存在重复的 id，请检查")
    return questions


def evidence_list(item: dict) -> list[str]:
    evidence = item.get("evidence")
    if isinstance(evidence, str):
        return [evidence] if evidence else []
    if isinstance(evidence, list):
        return [str(part) for part in evidence if str(part).strip()]
    return []


def validate_questions(questions: list[dict], chunks) -> None:
    """Fail fast on count/type/evidence errors before spending LLM calls."""
    counts = {kind: sum(1 for q in questions if q["type"] == kind) for kind in VALID_TYPES}
    if len(questions) != 20 or counts != {"doc": 10, "trap": 5, "multi_hop": 5}:
        raise ValueError(
            f"评测集必须是 20 题（10 doc + 5 trap + 5 multi_hop），"
            f"当前 {len(questions)} 题：{counts}"
        )
    docs = {chunk.doc_id for chunk in chunks}
    corpus_text = "\n".join(chunk.text for chunk in chunks)
    for item in questions:
        missing_docs = set(item.get("source_docs") or []) - docs
        if missing_docs:
            raise ValueError(f"{item['id']} 的 source_docs 不在语料中：{missing_docs}")
        if item["type"] == "trap":
            if item.get("source_docs"):
                raise ValueError(f"{item['id']} 是陷阱题，source_docs 应为空")
            continue
        evidences = evidence_list(item)
        if not evidences:
            raise ValueError(f"{item['id']} 缺少 evidence，无法计算 Top-3 命中")
        for evidence in evidences:
            if normalize(evidence) not in normalize(corpus_text):
                raise ValueError(
                    f"{item['id']} 的 evidence 未在语料中原样出现：{evidence[:40]}"
                )


def is_retrieval_hit(item: dict, candidates) -> bool | None:
    if item.get("type") == "trap":
        return None
    top3 = candidates[:3]
    if not top3:
        return False
    evidences = evidence_list(item)
    if evidences:
        texts = [normalize(candidate.chunk.text) for candidate in top3]
        return all(
            any(normalize(evidence) in text for text in texts)
            for evidence in evidences
        )
    source_docs = set(item.get("source_docs") or [])
    if not source_docs:
        return None
    return any(candidate.chunk.doc_id in source_docs for candidate in top3)


def top3_summary(candidates) -> str:
    return " | ".join(
        f"{candidate.chunk.doc_id}#{candidate.chunk.chunk_index} "
        f"({candidate.score:.3f})"
        for candidate in candidates[:3]
    )


def citation_summary(citations) -> str:
    return "; ".join(
        f"{citation.chunk.doc_id}#{citation.chunk.chunk_index}"
        for citation in citations
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="按评测集批量跑两种检索方案，输出 CSV/JSON 原始结果"
    )
    parser.add_argument(
        "--questions", type=Path, default=ROOT / "eval" / "questions.jsonl"
    )
    parser.add_argument(
        "--mode", choices=["both", "bm25", "vector"], default="both"
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "eval" / "results")
    parser.add_argument(
        "--out-suffix",
        default=None,
        help="输出文件名后缀；检索-only 默认 _retrieval，避免覆盖正式结果",
    )
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="只测检索命中与延迟，不调用大模型（无需 API Key）",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.5, help="每题之间的暂停秒数"
    )
    args = parser.parse_args()

    settings = get_settings()
    questions = load_questions(args.questions)
    if not questions:
        print(f"评测集 {args.questions} 是空的。")
        return 1
    if "example" in args.questions.stem:
        print("注意：example_questions.jsonl 只是格式示例，不能作为最终评测集。")
    if len(questions) != 20:
        print(f"提示：当前评测集有 {len(questions)} 题，作业要求 20 题。")

    chunks = load_chunks(settings.chunks_path)
    validate_questions(questions, chunks)
    if args.limit:
        questions = questions[: args.limit]
    suffix = args.out_suffix
    if suffix is None:
        suffix = "_retrieval" if args.retrieval_only else ""
    modes = ["bm25", "vector"] if args.mode == "both" else [args.mode]
    retrievers = {
        mode: load_retriever(mode, chunks, settings) for mode in modes
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for mode, retriever in retrievers.items():
        rows = []
        raw_rows = []
        print(f"\n===== 检索方式：{retriever.label} =====")
        for index, item in enumerate(questions, start=1):
            question = item["question"]
            started = time.perf_counter()
            error = ""
            answer = ""
            refused = ""
            citations = ""
            first_token = ""
            raw_answer = ""
            refusal_reason = ""
            from_gate = ""
            candidates = []
            citation_details = []
            try:
                if args.retrieval_only:
                    candidates = retriever.search(question, settings.top_k)
                else:
                    result = answer_question(question, retriever, settings)
                    candidates = result.retrieved
                    answer = result.answer
                    refused = str(result.refused)
                    citations = citation_summary(result.citations)
                    raw_answer = result.raw_answer or result.answer
                    refusal_reason = result.refusal_reason
                    from_gate = str(result.from_gate)
                    citation_details = [
                        {
                            "index": c.index,
                            "doc_id": c.chunk.doc_id,
                            "chunk_index": c.chunk.chunk_index,
                            "chunk_text": c.chunk.text,
                        }
                        for c in result.citations
                    ]
                    if result.first_token_s is not None:
                        first_token = f"{result.first_token_s:.2f}"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            latency = time.perf_counter() - started
            hit = is_retrieval_hit(item, candidates)
            hit_value = "" if hit is None else str(int(hit))

            rows.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "question": question,
                    "source_docs": "|".join(item.get("source_docs") or []),
                    "mode": mode,
                    "refused": refused,
                    "answer": answer,
                    "raw_answer": raw_answer,
                    "refusal_reason": refusal_reason,
                    "from_gate": from_gate,
                    "citations": citations,
                    "citation_details": json.dumps(
                        citation_details, ensure_ascii=False
                    ),
                    "first_token_s": first_token,
                    "latency_s": f"{latency:.2f}",
                    "retrieval_hit": hit_value,
                    "top3": top3_summary(candidates),
                    "correct": "",
                    "notes": error,
                }
            )
            raw_rows.append(
                {
                    **item,
                    "mode": mode,
                    "refused": None if refused == "" else refused == "True",
                    "answer": answer,
                    "raw_answer": raw_answer,
                    "refusal_reason": refusal_reason,
                    "from_gate": None if from_gate == "" else from_gate == "True",
                    "citations": citations,
                    "citation_details": citation_details,
                    "first_token_s": (
                        float(first_token) if first_token else None
                    ),
                    "latency_s": round(latency, 3),
                    "retrieval_hit": hit,
                    "retrieved": [
                        {
                            "chunk_id": candidate.chunk.id,
                            "doc_id": candidate.chunk.doc_id,
                            "chunk_index": candidate.chunk.chunk_index,
                            "score": round(candidate.score, 6),
                            "text": candidate.chunk.text,
                        }
                        for candidate in candidates
                    ],
                    "error": error,
                }
            )
            status = "OK" if not error else f"ERROR: {error[:60]}"
            print(
                f"[{index:02d}/{len(questions)}] {item['id']} "
                f"({item['type']}) {latency:.2f}s {status}"
            )
            if args.sleep and not args.retrieval_only:
                time.sleep(args.sleep)

        csv_path = args.out_dir / f"results_{mode}{suffix}.csv"
        jsonl_path = args.out_dir / f"raw_{mode}{suffix}.jsonl"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for raw in raw_rows:
                handle.write(json.dumps(raw, ensure_ascii=False) + "\n")
        print(f"已写入 {csv_path}")
        print(f"已写入 {jsonl_path}")

    if not args.retrieval_only:
        print(
            "\n下一步：在 CSV 的 correct 列填 1（答对）/ 0（答错），"
            "然后运行 python scripts/score.py eval/results/results_*.csv"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
