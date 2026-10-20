"""Separation check for refusal thresholds on a small held-out query set.

This script does not call an LLM. It prints the Top-1 vector score and BM25
query coverage for every query so thresholds can be chosen independently of
the 20-question test set.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.corpus import load_chunks  # noqa: E402
from app.retrievers import load_retriever, query_coverage  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    chunks = load_chunks(settings.chunks_path)
    queries = [
        json.loads(line)
        for line in (ROOT / "eval" / "calibration.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    retrievers = {
        mode: load_retriever(mode, chunks, settings) for mode in ("bm25", "vector")
    }
    print("| id | expected | BM25 coverage | vector Top-1 |")
    print("| --- | --- | ---: | ---: |")
    for item in queries:
        bm25 = retrievers["bm25"].search(item["question"], settings.top_k)
        vector = retrievers["vector"].search(item["question"], settings.top_k)
        print(
            f"| {item['id']} | {item['expected']} | "
            f"{query_coverage(item['question'], bm25):.3f} | "
            f"{vector[0].score:.3f} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
