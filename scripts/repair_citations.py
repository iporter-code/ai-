"""Repair in-range but unsupported citations in existing evaluation results.

This does not call the LLM. It re-checks each citation against the sentence it
marks and remaps/drops it using the archived Top-4 chunks.
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.corpus import Chunk  # noqa: E402
from app.rag import _verify_citations  # noqa: E402
from app.retrievers import Candidate  # noqa: E402


def citation_text(citations) -> str:
    return "; ".join(
        f"{c.chunk.doc_id}#{c.chunk.chunk_index}" for c in citations
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results_dir = ROOT / "eval" / "results"
    for mode in ("bm25", "vector"):
        raw_path = results_dir / f"raw_{mode}.jsonl"
        csv_path = results_dir / f"results_{mode}.csv"
        raws = {}
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                raws[row["id"]] = row

        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
        for row in rows:
            raw = raws[row["id"]]
            candidates = [
                Candidate(
                    Chunk(
                        item["chunk_id"],
                        item["doc_id"],
                        item["chunk_index"],
                        item["text"],
                    ),
                    item["score"],
                )
                for item in raw.get("retrieved", [])
            ]
            original = raw["answer"]
            answer, citations = _verify_citations(original, candidates)
            details = [
                {
                    "index": c.index,
                    "doc_id": c.chunk.doc_id,
                    "chunk_index": c.chunk.chunk_index,
                    "chunk_text": c.chunk.text,
                }
                for c in citations
            ]
            row["raw_answer"] = original
            row["source_docs"] = "|".join(raw.get("source_docs") or [])
            row["answer"] = answer
            row["citations"] = citation_text(citations)
            row["citation_details"] = json.dumps(details, ensure_ascii=False)
            row["citation_verified"] = "True"
            if "引用校验" not in row.get("notes", ""):
                row["notes"] = (row.get("notes", "").rstrip("。") + "；引用已按句校验。").lstrip("；")
            raw["raw_answer"] = original
            raw["answer"] = answer
            raw["citations"] = row["citations"]
            raw["citation_details"] = details
            raw["citation_verified"] = True

        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with raw_path.open("w", encoding="utf-8") as handle:
            for row in raws.values():
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{mode}: repaired {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
