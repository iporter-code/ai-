import argparse
import html

import gradio as gr

from .config import get_settings
from .corpus import load_chunks
from .rag import answer_question, format_result
from .retrievers import load_retriever

MODE_LABELS = {
    "向量检索 (bge-small-zh)": "vector",
    "关键词检索 (BM25)": "bm25",
}


def _debug_block(result) -> str:
    if not result.retrieved:
        return ""
    rows = ["**检索详情**", ""]
    for index, candidate in enumerate(result.retrieved, start=1):
        chunk = candidate.chunk
        rows.append(
            f"{index}. `{chunk.doc_id}`（片段 {chunk.chunk_index + 1}）"
            f" — 分数 {candidate.score:.3f}"
        )
    return "\n".join(rows)


def build_demo(settings):
    chunks = load_chunks(settings.chunks_path)
    docs = {chunk.doc_id for chunk in chunks}
    retrievers: dict[str, object] = {"bm25": load_retriever("bm25", chunks, settings)}

    def get_retriever(mode: str):
        if mode not in retrievers:
            retrievers[mode] = load_retriever(mode, chunks, settings)
        return retrievers[mode]

    def respond(message, history, mode_label, top_k, show_debug):
        message = (message or "").strip()
        if not message:
            return history, ""
        mode = MODE_LABELS.get(mode_label, "vector")
        try:
            retriever = get_retriever(mode)
            result = answer_question(
                message, retriever, settings, int(top_k) if top_k else None
            )
            content = format_result(result)
            if show_debug:
                content += "\n\n" + _debug_block(result)
            first_text = (
                f"{result.first_token_s:.2f}s"
                if result.first_token_s is not None
                else "-"
            )
            content += (
                f"\n\n*首字 {first_text} · 总耗时 {result.latency_s:.2f}s"
                f" · {retriever.label}"
                f" · Top-{int(top_k) if top_k else settings.top_k}*"
            )
        except Exception as exc:
            content = f"**出错了**：{html.escape(str(exc))}"
        history = list(history or [])
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": content})
        return history, ""

    def clear():
        return [], ""

    key_status = "已配置" if settings.llm_api_key else "未配置（请先填写 .env）"
    with gr.Blocks(title="不瞎编的私有知识库助手") as demo:
        gr.Markdown(
            "# 不瞎编的私有知识库助手\n"
            f"语料：**{len(docs)}** 个文档 / **{len(chunks)}** 个片段。"
            "回答只依据检索到的片段，并标注 `[编号]` 来源；资料不足时明确拒答。"
        )
        with gr.Row():
            mode = gr.Radio(
                choices=list(MODE_LABELS),
                value="向量检索 (bge-small-zh)",
                label="检索方式（可运行时切换）",
            )
            top_k = gr.Slider(
                minimum=1, maximum=6, value=settings.top_k, step=1, label="检索片段数"
            )
            show_debug = gr.Checkbox(value=False, label="显示检索详情")
        chatbot = gr.Chatbot(
            height=520, label="对话", buttons=["copy"]
        )
        with gr.Row():
            textbox = gr.Textbox(
                placeholder="输入问题，例如：作者为什么选择 bge-small-zh？",
                scale=8,
                container=False,
            )
            submit = gr.Button("提问", variant="primary", scale=1)
        with gr.Row():
            clear_button = gr.ClearButton(
                components=[chatbot, textbox], value="清空对话"
            )
        gr.Markdown(
            f"*LLM：{settings.llm_model} · Key：{key_status} · "
            f"Embedding：{settings.embedding_model} · "
            "首次使用向量检索需加载本地模型*"
        )

        submit.click(
            respond,
            inputs=[textbox, chatbot, mode, top_k, show_debug],
            outputs=[chatbot, textbox],
        )
        textbox.submit(
            respond,
            inputs=[textbox, chatbot, mode, top_k, show_debug],
            outputs=[chatbot, textbox],
        )
        clear_button.click(clear, outputs=[chatbot, textbox])
    return demo


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Gradio 问答界面")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true", help="生成公网分享链接")
    args = parser.parse_args()

    settings = get_settings()
    demo = build_demo(settings)
    demo.launch(
        server_name="127.0.0.1",
        server_port=args.port,
        share=args.share,
        inbrowser=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
