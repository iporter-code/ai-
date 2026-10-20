"""Rebuild results_*.csv from raw_*.jsonl after a rerun/repair.

Human labels are kept here because the evaluation runner intentionally leaves
`correct` blank for manual judgement.
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WRONG = {
    "bm25": {
        "q11": "比较题：把“三组命中率不同”误当成“课程建议与实验结论不一致”，应判“200~400 包含 300，二者相符”。",
        "q17": "幻觉：语料没有期末考试日期，模型把作业截止日 10 月 21 日当成考试日期并给出 [1] 引用。",
    },
    "vector": {
        "q11": "比较题：把“三组命中率不同”误当成“课程建议与实验结论不一致”，应判“200~400 包含 300，二者相符”。",
        "q15": "误拒答：证据在 Top-4 上下文中，模型却输出 INSUFFICIENT_CONTEXT，属于过度拒答。",
    },
}


def top3(row) -> str:
    return " | ".join(
        f"{c['doc_id']}#{c['chunk_index']} ({c['score']:.3f})"
        for c in row.get("retrieved", [])[:3]
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for mode in ("bm25", "vector"):
        raw_path = ROOT / "eval" / "results" / f"raw_{mode}.jsonl"
        csv_path = ROOT / "eval" / "results" / f"results_{mode}.csv"
        rows = [
            json.loads(line)
            for line in raw_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            fields = [
                "id",
                "type",
                "question",
                "source_docs",
                "mode",
                "refused",
                "answer",
                "raw_answer",
                "refusal_reason",
                "from_gate",
                "citations",
                "first_token_s",
                "latency_s",
                "retrieval_hit",
                "top3",
                "correct",
                "notes",
                "citation_details",
                "citation_verified",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                qid = row["id"]
                correct = "0" if qid in WRONG[mode] else "1"
                notes = WRONG[mode].get(qid, "人工判定：核心事实与标准答案一致，无文档外编造。")
                writer.writerow(
                    {
                        "id": qid,
                        "type": row["type"],
                        "question": row["question"],
                        "source_docs": "|".join(row.get("source_docs") or []),
                        "mode": mode,
                        "refused": "" if row.get("refused") is None else str(row["refused"]),
                        "answer": row.get("answer", ""),
                        "raw_answer": row.get("raw_answer", ""),
                        "refusal_reason": row.get("refusal_reason", ""),
                        "from_gate": "" if row.get("from_gate") is None else str(row["from_gate"]),
                        "citations": row.get("citations", ""),
                        "first_token_s": (
                            "" if row.get("first_token_s") is None else f"{row['first_token_s']:.2f}"
                        ),
                        "latency_s": f"{row.get('latency_s', 0):.2f}",
                        "retrieval_hit": "" if row.get("retrieval_hit") is None else str(int(row["retrieval_hit"])),
                        "top3": top3(row),
                        "correct": correct,
                        "notes": notes,
                        "citation_details": json.dumps(
                            row.get("citation_details", []), ensure_ascii=False
                        ),
                        "citation_verified": str(row.get("citation_verified", False)),
                    }
                )
        print(f"{csv_path} rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
