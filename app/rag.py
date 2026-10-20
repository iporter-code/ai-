import re
import time
from dataclasses import dataclass, field

from .config import Settings
from .corpus import Chunk
from .retrievers import Candidate, query_coverage, tokenize

INSUFFICIENT_MARKER = "INSUFFICIENT_CONTEXT"
REFUSAL_TEXT = "文档中没有相关信息，无法回答这个问题。"

_CITATION_RE = re.compile(r"[\[【［〔](\d+)[\]】］〕]")
_REFUSAL_PATTERNS = (
    "无法回答",
    "无法确定",
    "无法从资料",
    "没有相关信息",
    "没有找到相关",
    "资料中没有",
    "文档中没有",
    "资料未提及",
    "文档未提及",
    "未提供相关信息",
    "insufficient_context",
)

SYSTEM_PROMPT = """你是一个严格依据给定资料回答问题的知识库助手。必须遵守以下规则：
1. 只能使用【资料】中出现的信息回答，不得使用资料之外的常识、猜测或补全。
2. 回答中的每个关键结论后面必须用 [编号] 标注依据，编号对应【资料】中的编号。
3. 如果【资料】不足以回答问题，或资料与问题无关，只输出一行：INSUFFICIENT_CONTEXT
4. 不要编造资料中不存在的数字、日期、人名、地点或结论。
5. 用简洁的中文回答。"""


@dataclass(frozen=True)
class Citation:
    index: int
    chunk: Chunk


@dataclass
class RAGResult:
    question: str
    mode: str
    answer: str
    refused: bool
    refusal_reason: str
    citations: list[Citation]
    retrieved: list[Candidate]
    latency_s: float
    from_gate: bool = False
    raw_answer: str = field(default="")
    first_token_s: float | None = None


def _build_context(candidates: list[Candidate]) -> str:
    blocks = []
    for index, candidate in enumerate(candidates, start=1):
        chunk = candidate.chunk
        blocks.append(
            f"[{index}] 文档：{chunk.doc_id}（片段 {chunk.chunk_index + 1}）\n{chunk.text}"
        )
    return "\n\n".join(blocks)


def _extract_citations(answer: str, candidates: list[Candidate]) -> list[Citation]:
    seen: list[int] = []
    for match in _CITATION_RE.finditer(answer):
        index = int(match.group(1)) - 1
        if 0 <= index < len(candidates) and index not in seen:
            seen.append(index)
    return [Citation(index=index + 1, chunk=candidates[index].chunk) for index in seen]


def _sentence_around(text: str, start: int, end: int) -> str:
    left = 0
    for boundary in "。！？!?；;\n":
        pos = text.rfind(boundary, 0, start)
        left = max(left, pos + 1)
    right = len(text)
    for boundary in "。！？!?；;\n":
        pos = text.find(boundary, end)
        if pos != -1:
            right = min(right, pos)
    context = _CITATION_RE.sub("", text[left:right]).strip()
    if not context:
        # 引用正好落在句末且后面没有下一句时，回退到前一段文字。
        context = _CITATION_RE.sub("", text[max(0, start - 260) : start]).strip()
    return context


def _support_score(text: str, chunk_text: str) -> int:
    query_tokens = {
        token for token in tokenize(text) if len(token) >= 2 or token.isdigit()
    }
    chunk_tokens = {
        token for token in tokenize(chunk_text) if len(token) >= 2 or token.isdigit()
    }
    return len(query_tokens & chunk_tokens)


def _verify_citations(
    answer: str, candidates: list[Candidate], min_support: int = 3
) -> tuple[str, list[Citation]]:
    """Keep only citations whose chunk actually overlaps the cited sentence.

    A wrong in-range index is remapped to the best supporting candidate when
    one exists; otherwise the marker is removed. This prevents q02-style
    citations from pointing at an unrelated Python note just because [2] is
    within the Top-4.
    """
    used: list[int] = []

    def replace(match: re.Match) -> str:
        old_index = int(match.group(1)) - 1
        if not 0 <= old_index < len(candidates):
            return ""
        context = _sentence_around(answer, match.start(), match.end())
        scores = [_support_score(context, c.chunk.text) for c in candidates]
        best = max(range(len(candidates)), key=lambda i: scores[i])
        if scores[best] >= min_support and scores[best] > scores[old_index] + 2:
            chosen = best
        elif scores[old_index] >= min_support:
            chosen = old_index
        elif scores[best] >= min_support:
            chosen = best
        else:
            return ""
        index = chosen + 1
        if index in used:
            return ""
        used.append(index)
        return f"[{index}]"

    rewritten = _CITATION_RE.sub(replace, answer)
    citations = [
        Citation(index=index, chunk=candidates[index - 1].chunk) for index in used
    ]
    return rewritten, citations


def _looks_like_refusal(answer: str) -> bool:
    text = answer.strip()
    if not text:
        return True
    if INSUFFICIENT_MARKER in text.upper():
        return True
    lowered = text.lower()
    if any(pattern in lowered for pattern in _REFUSAL_PATTERNS):
        return not _CITATION_RE.search(text)
    return False


def _retrieval_gate(
    question: str, retriever_name: str, candidates: list[Candidate], settings: Settings
) -> str:
    if not candidates:
        return "检索没有返回任何片段"
    if retriever_name == "vector":
        top_score = candidates[0].score
        if top_score < settings.vector_min_score:
            return (
                f"Top-1 向量相似度 {top_score:.3f} 低于阈值 "
                f"{settings.vector_min_score}"
            )
    elif retriever_name == "bm25":
        coverage = query_coverage(question, candidates)
        if coverage < settings.bm25_min_coverage:
            return (
                f"查询词覆盖率 {coverage:.2f} 低于阈值 "
                f"{settings.bm25_min_coverage}"
            )
    return ""


def _call_llm(
    question: str,
    candidates: list[Candidate],
    settings: Settings,
    on_first_token=None,
) -> str:
    if not settings.llm_api_key and "pollinations" not in settings.llm_base_url.lower():
        raise RuntimeError(
            "未配置 LLM_API_KEY。请复制 .env.example 为 .env 并填入 "
            "OpenAI 兼容接口的 Key；Pollinations 可填 not-needed。"
        )
    from openai import APIStatusError, OpenAI

    client = OpenAI(
        api_key=settings.llm_api_key or "not-needed",
        base_url=settings.llm_base_url,
    )
    user_prompt = (
        "【资料】\n"
        f"{_build_context(candidates)}\n\n"
        "【问题】\n"
        f"{question}"
    )
    for attempt in range(4):
        try:
            stream = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.temperature,
                max_tokens=800,
                stream=True,
            )
            parts: list[str] = []
            for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                content = getattr(choices[0].delta, "content", None)
                if not content:
                    continue
                if not parts and on_first_token is not None:
                    on_first_token()
                parts.append(content)
            text = "".join(parts).strip()
            if not text:
                raise RuntimeError("模型返回了空答案")
            return text
        except APIStatusError as exc:
            # Pollinations 免费接口会返回 402/429 并在消息里给出重试秒数。
            if exc.status_code not in {402, 429} or attempt == 3:
                raise
            match = re.search(r"Retry after (\d+)s", str(exc))
            wait_s = int(match.group(1)) + 2 if match else 32
            time.sleep(wait_s)
    raise RuntimeError("LLM 调用重试次数已用完")


def answer_question(
    question: str,
    retriever,
    settings: Settings,
    top_k: int | None = None,
) -> RAGResult:
    started = time.perf_counter()
    candidates = retriever.search(question, top_k or settings.top_k)
    refusal_reason = _retrieval_gate(
        question, retriever.name, candidates, settings
    )
    if refusal_reason:
        return RAGResult(
            question=question,
            mode=retriever.name,
            answer=REFUSAL_TEXT,
            refused=True,
            refusal_reason=refusal_reason,
            citations=[],
            retrieved=candidates,
            latency_s=time.perf_counter() - started,
            from_gate=True,
            first_token_s=time.perf_counter() - started,
        )

    first_token_s: float | None = None

    def mark_first_token() -> None:
        nonlocal first_token_s
        first_token_s = time.perf_counter() - started

    raw_answer = _call_llm(
        question, candidates, settings, on_first_token=mark_first_token
    )
    latency = time.perf_counter() - started

    if _looks_like_refusal(raw_answer):
        return RAGResult(
            question=question,
            mode=retriever.name,
            answer=REFUSAL_TEXT,
            refused=True,
            refusal_reason="模型判断资料不足以回答",
            citations=[],
            retrieved=candidates,
            latency_s=latency,
            raw_answer=raw_answer,
            first_token_s=first_token_s,
        )

    verified_answer, citations = _verify_citations(raw_answer, candidates)
    return RAGResult(
        question=question,
        mode=retriever.name,
        answer=verified_answer,
        refused=False,
        refusal_reason="",
        citations=citations,
        retrieved=candidates,
        latency_s=latency,
        raw_answer=raw_answer,
        first_token_s=first_token_s,
    )


def _snippet(text: str, limit: int = 180) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    if len(snippet) > limit:
        snippet = snippet[:limit] + "…"
    return snippet


def format_result(result: RAGResult) -> str:
    if result.refused:
        lines = [f"**{REFUSAL_TEXT}**"]
        if result.refusal_reason:
            lines.append(f"\n> 拒答判定：{result.refusal_reason}")
        return "\n".join(lines)

    lines = [result.answer.strip(), "", "---", "**引用来源**", ""]
    if result.citations:
        for citation in result.citations:
            chunk = citation.chunk
            lines.append(
                f"[{citation.index}] `{chunk.doc_id}`（片段 {chunk.chunk_index + 1}）"
            )
            lines.append(f"> {_snippet(chunk.text)}")
            lines.append("")
    else:
        lines.append("模型未在回答中标注引用编号，以下为本次检索到的资料：")
        lines.append("")
        for index, candidate in enumerate(result.retrieved[:3], start=1):
            chunk = candidate.chunk
            lines.append(f"[{index}] `{chunk.doc_id}`（片段 {chunk.chunk_index + 1}）")
            lines.append(f"> {_snippet(chunk.text)}")
            lines.append("")
    return "\n".join(lines).strip()
