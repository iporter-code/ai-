import argparse
import sys

from .config import get_settings
from .corpus import build_chunks, load_chunks, save_chunks
from .rag import answer_question, format_result
from .retrievers import load_retriever


def _reconfigure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    chunks, empty_docs = build_chunks(
        settings.raw_dir, settings.chunk_size, settings.chunk_overlap
    )
    if not chunks:
        print(f"在 {settings.raw_dir} 中没有找到可导入的 .txt / .md / .pdf 文件。")
        return 1

    save_chunks(chunks, settings.chunks_path)
    docs: dict[str, int] = {}
    for chunk in chunks:
        docs[chunk.doc_id] = docs.get(chunk.doc_id, 0) + 1
    print(f"已导入 {len(docs)} 个文档，切分为 {len(chunks)} 个片段。")
    for doc_id, count in sorted(docs.items()):
        print(f"  - {doc_id}: {count} 段")
    if empty_docs:
        print(f"警告：以下文件没有提取到文本：{', '.join(empty_docs)}")

    if not args.no_vector:
        print("正在构建向量索引（首次运行会下载本地 embedding 模型）……")
        load_retriever("vector", chunks, settings)
        print("向量索引构建完成。")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    settings = get_settings()
    chunks = load_chunks(settings.chunks_path)
    retriever = load_retriever(args.mode, chunks, settings)
    try:
        result = answer_question(args.question, retriever, settings, args.top_k)
    except Exception as exc:
        print(f"调用失败：{exc}")
        return 1
    print(format_result(result))
    first = (
        f"{result.first_token_s:.2f}s"
        if result.first_token_s is not None
        else "-"
    )
    print(
        f"\n首字：{first} | 总耗时：{result.latency_s:.2f}s | "
        f"检索方式：{retriever.label}"
    )
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    settings = get_settings()
    print(f"语料目录：{settings.raw_dir}")
    print(f"索引目录：{settings.index_dir}")
    print(f"LLM：{settings.llm_model} @ {settings.llm_base_url}")
    print(f"LLM Key：{'已配置' if settings.llm_api_key else '未配置'}")
    print(f"Embedding：{settings.embedding_model}")
    print(f"切分：{settings.chunk_size} 字 / 重叠 {settings.chunk_overlap} 字")
    print(f"检索 Top-K：{settings.top_k}")
    print(
        "拒答阈值：向量相似度 < "
        f"{settings.vector_min_score}，BM25 覆盖率 < {settings.bm25_min_coverage}"
    )
    if settings.chunks_path.exists():
        chunks = load_chunks(settings.chunks_path)
        docs = {chunk.doc_id for chunk in chunks}
        print(f"当前索引：{len(docs)} 个文档，{len(chunks)} 个片段")
    else:
        print("当前索引：尚未构建")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="私有知识库问答助手（BM25 / 向量检索）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="导入语料并切分、建索引")
    ingest.add_argument(
        "--no-vector", action="store_true", help="只切分，不构建向量索引"
    )
    ingest.set_defaults(func=cmd_ingest)

    ask = subparsers.add_parser("ask", help="提一个问题")
    ask.add_argument("question", help="问题内容")
    ask.add_argument(
        "--mode", choices=["bm25", "vector"], default="vector", help="检索方式"
    )
    ask.add_argument("--top-k", type=int, default=None, help="检索片段数")
    ask.set_defaults(func=cmd_ask)

    info = subparsers.add_parser("info", help="查看配置与索引状态")
    info.set_defaults(func=cmd_info)
    return parser


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
