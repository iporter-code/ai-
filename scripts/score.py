import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE_LABELS = {"doc": "文档题", "trap": "陷阱题", "multi_hop": "多跳题"}


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_bool(value: str) -> bool | None:
    if value is None or value == "":
        return None
    return value.strip().lower() in {"true", "1", "yes"}


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    judged = [
        row
        for row in rows
        if parse_float(row.get("correct")) in {0.0, 1.0}
    ]
    correct = sum(1 for row in judged if parse_float(row["correct"]) == 1.0)
    trap_rows = [row for row in rows if row.get("type") == "trap"]
    hallucinated = sum(
        1 for row in trap_rows if parse_bool(row.get("refused")) is False
    )
    scored = [row for row in rows if row.get("type") != "trap"]
    hit_known = [row for row in scored if row.get("retrieval_hit") in {"0", "1"}]
    hits = sum(1 for row in hit_known if row["retrieval_hit"] == "1")
    latencies = [
        value
        for value in (parse_float(row.get("latency_s")) for row in rows)
        if value is not None
    ]
    answered = [
        row
        for row in scored
        if row.get("answer") and parse_bool(row.get("refused")) is not True
    ]
    with_citation = [row for row in answered if (row.get("citations") or "").strip()]
    citation_ok = 0
    for row in with_citation:
        cited_docs = {
            part.split("#", 1)[0]
            for part in (row.get("citations") or "").split("; ")
            if "#" in part
        }
        source_docs = set((row.get("source_docs") or "").split("|")) - {""}
        if source_docs and cited_docs <= source_docs:
            citation_ok += 1
    first_token_latencies = [
        value
        for value in (
            parse_float(row.get("first_token_s")) or parse_float(row.get("latency_s"))
            for row in rows
        )
        if value is not None
    ]
    return {
        "total": total,
        "judged": len(judged),
        "correct": correct,
        "accuracy": correct / len(judged) if judged else None,
        "trap_total": len(trap_rows),
        "hallucinated": hallucinated,
        "hallucination_rate": hallucinated / len(trap_rows) if trap_rows else None,
        "hit_scored": len(hit_known),
        "hits": hits,
        "hit_rate": hits / len(hit_known) if hit_known else None,
        "avg_first_token": (
            statistics.mean(first_token_latencies) if first_token_latencies else None
        ),
        "avg_latency": statistics.mean(latencies) if latencies else None,
        "answered": len(answered),
        "citation_rate": len(with_citation) / len(answered) if answered else None,
        "citation_doc_accuracy": (
            citation_ok / len(with_citation) if with_citation else None
        ),
        "citation_rows": len(with_citation),
        "errors": sum(
            1
            for row in rows
            if row.get("type") != "trap"
            and not row.get("answer")
            and row.get("refused") in ("", None)
        ),
    }


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def metrics_table(rows: list[dict]) -> str:
    summary = summarize(rows)
    lines = [
        "| 指标 | 数值 | 说明 |",
        "| --- | --- | --- |",
        f"| 答案正确率 | {pct(summary['accuracy'])} "
        f"| {summary['correct']}/{summary['judged']} 道已判定 |",
        f"| 幻觉率 | {pct(summary['hallucination_rate'])} "
        f"| {summary['hallucinated']}/{summary['trap_total']} 道陷阱题被硬答 |",
        f"| 检索命中率 (Top-3) | {pct(summary['hit_rate'])} "
        f"| {summary['hits']}/{summary['hit_scored']} 道非陷阱题 |",
        f"| 首次回答平均延迟 | {fmt(summary['avg_first_token'])} s "
        f"| 首 token，本机实测，共 {summary['total']} 次 |",
        f"| 端到端平均延迟 | {fmt(summary['avg_latency'])} s "
        f"| 含完整生成，共 {summary['total']} 次 |",
        f"| 引用给出率 | {pct(summary['citation_rate'])} "
        f"| {summary['citation_rows']}/{summary['answered']} 道有答案题 |",
        f"| 引用文档准确率 | {pct(summary['citation_doc_accuracy'])} "
        f"| 引用片段均来自 source_docs |",
    ]
    if summary["judged"] < summary["total"]:
        lines.append(
            f"\n> 注意：还有 {summary['total'] - summary['judged']} 题未填 correct。"
        )
    return "\n".join(lines)


def comparison_table(results: list[tuple[str, list[dict]]]) -> str:
    if len(results) < 2:
        return ""
    names = [name for name, _ in results]
    rows = [
        (
            "答案正确率",
            lambda summary: pct(summary["accuracy"]),
        ),
        (
            "幻觉率",
            lambda summary: pct(summary["hallucination_rate"]),
        ),
        (
            "Top-3 检索命中率",
            lambda summary: pct(summary["hit_rate"]),
        ),
        (
            "首次回答平均延迟 (s)",
            lambda summary: fmt(summary["avg_first_token"]),
        ),
        (
            "端到端平均延迟 (s)",
            lambda summary: fmt(summary["avg_latency"]),
        ),
        (
            "引用文档准确率",
            lambda summary: pct(summary["citation_doc_accuracy"]),
        ),
    ]
    lines = [
        "## 方案对比",
        "",
        "| 指标 | " + " | ".join(names) + " |",
        "| --- | " + " | ".join("---" for _ in names) + " |",
    ]
    summaries = [(name, summarize(group)) for name, group in results]
    for label, render in rows:
        lines.append(
            f"| {label} | "
            + " | ".join(render(summary) for _, summary in summaries)
            + " |"
        )
    return "\n".join(lines)


def per_type_table(rows: list[dict]) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row.get("type", "?")].append(row)
    lines = [
        "| 题型 | 题数 | 正确率 | 首 token (s) |",
        "| --- | --- | --- | --- |",
    ]
    for key, group in groups.items():
        summary = summarize(group)
        lines.append(
            f"| {TYPE_LABELS.get(key, key)} | {summary['total']} "
            f"| {pct(summary['accuracy'])} | {fmt(summary['avg_first_token'])} |"
        )
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="根据人工标注的 correct 列计算作业要求的四项指标"
    )
    parser.add_argument("csv", nargs="+", type=Path, help="results_*.csv 文件")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "eval" / "results" / "metrics.md"
    )
    args = parser.parse_args()

    loaded: list[tuple[str, list[dict]]] = []
    for path in args.csv:
        if not path.exists():
            print(f"找不到文件：{path}", file=sys.stderr)
            return 1
        rows = load_rows(path)
        name = path.stem.replace("results_", "")
        loaded.append((name, rows))

    sections = ["# 评测结果汇总", ""]
    comparison = comparison_table(loaded)
    if comparison:
        sections.extend([comparison, ""])

    for name, rows in loaded:
        sections.extend(
            [
                f"## 检索方式：{name}",
                "",
                metrics_table(rows),
                "",
                per_type_table(rows),
                "",
            ]
        )
    output = "\n".join(sections)
    print(output)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output + "\n", encoding="utf-8")
    print(f"\n已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
