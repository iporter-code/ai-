from app.config import Settings
from app.corpus import Chunk
from app.rag import (
    REFUSAL_TEXT,
    RAGResult,
    _date_slot_guard,
    _extract_citations,
    _looks_like_refusal,
    _retrieval_gate,
    _verify_citations,
    answer_question,
    format_result,
)
from app.retrievers import Candidate


def make_settings(work_dir) -> Settings:
    return Settings(
        llm_base_url="http://localhost:1/v1",
        llm_api_key="",
        llm_model="test",
        embedding_model="test",
        chunk_size=100,
        chunk_overlap=20,
        top_k=2,
        vector_min_score=0.35,
        bm25_min_coverage=0.25,
        temperature=0,
        raw_dir=work_dir / "raw",
        index_dir=work_dir / "index",
    )


def make_candidate(score: float) -> Candidate:
    chunk = Chunk(
        id="notes.md::0",
        doc_id="notes.md",
        chunk_index=0,
        text="向量模型选用 bge-small-zh，余弦相似度阈值是 0.35。",
    )
    return Candidate(chunk, score)


def test_extract_citations_ignores_out_of_range_and_duplicates():
    candidates = [make_candidate(0.9), make_candidate(0.8)]
    citations = _extract_citations("结论甲 [1]，结论乙 [2]，重复 [1]，越界 [9]。", candidates)
    assert [citation.index for citation in citations] == [1, 2]


def test_extract_citations_supports_chinese_brackets():
    candidates = [make_candidate(0.9), make_candidate(0.8)]
    citations = _extract_citations("结论甲【1】，结论乙［2］。", candidates)
    assert [citation.index for citation in citations] == [1, 2]


def test_verify_citations_remaps_to_supporting_chunk():
    correct = Candidate(
        Chunk(
            id="notes.md::2",
            doc_id="notes.md",
            chunk_index=2,
            text="RAG 标准流水线五步：切、嵌、存、检、答，对应口诀。",
        ),
        0.8,
    )
    wrong = Candidate(
        Chunk(
            id="env.txt::0",
            doc_id="env.txt",
            chunk_index=0,
            text="Windows 下创建虚拟环境，使用 venv 激活。",
        ),
        0.2,
    )
    answer, citations = _verify_citations(
        "RAG 的标准流水线是切、嵌、存、检、答[2]。", [correct, wrong]
    )
    assert "[1]" in answer
    assert [c.chunk.doc_id for c in citations] == ["notes.md"]


def test_verify_citations_drops_unsupported_marker():
    wrong = Candidate(
        Chunk(id="env.txt::0", doc_id="env.txt", chunk_index=0, text="venv 激活命令。"),
        0.2,
    )
    answer, citations = _verify_citations("RAG 五步口诀是切嵌存检答[1]。", [wrong])
    assert citations == []
    assert "[1]" not in answer


def test_refusal_detection():
    assert _looks_like_refusal("INSUFFICIENT_CONTEXT")
    assert _looks_like_refusal("文档中没有相关信息。")
    assert not _looks_like_refusal("阈值是 0.35 [1]。")
    assert not _looks_like_refusal("资料中没有提到猫，但根据 [1] 可知作者养狗。")


def test_vector_gate_rejects_low_similarity(work_dir):
    settings = make_settings(work_dir)
    reason = _retrieval_gate("无关问题", "vector", [make_candidate(0.2)], settings)
    assert reason
    assert "0.35" in reason


def test_vector_gate_accepts_high_similarity(work_dir):
    settings = make_settings(work_dir)
    assert _retrieval_gate("相关问题", "vector", [make_candidate(0.6)], settings) == ""


def test_bm25_gate_rejects_low_coverage(work_dir):
    settings = make_settings(work_dir)
    candidate = Candidate(
        Chunk(id="d::0", doc_id="d", chunk_index=0, text="今天天气很好。"), 5.0
    )
    reason = _retrieval_gate("量子纠缠实验", "bm25", [candidate], settings)
    assert reason


def test_format_result_lists_source_and_snippet():
    candidate = make_candidate(0.8)
    result = RAGResult(
        question="阈值是多少",
        mode="vector",
        answer="阈值是 0.35 [1]。",
        refused=False,
        refusal_reason="",
        citations=_extract_citations("阈值是 0.35 [1]。", [candidate]),
        retrieved=[candidate],
        latency_s=0.1,
    )
    rendered = format_result(result)
    assert "引用来源" in rendered
    assert "notes.md" in rendered
    assert "阈值" in rendered


class FakeRetriever:
    name = "vector"

    def __init__(self, score: float):
        self.score = score

    def search(self, query: str, top_k: int = 4):
        return [make_candidate(self.score)]


def test_answer_question_refuses_before_calling_llm(work_dir, monkeypatch):
    settings = make_settings(work_dir)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("低分检索结果不应调用大模型")

    monkeypatch.setattr("app.rag._call_llm", fail_if_called)
    result = answer_question("无关问题", FakeRetriever(0.1), settings)
    assert result.refused
    assert result.from_gate
    assert result.answer == REFUSAL_TEXT


def test_answer_question_maps_model_refusal(work_dir, monkeypatch):
    settings = make_settings(work_dir)
    monkeypatch.setattr(
        "app.rag._call_llm", lambda question, candidates, settings, on_first_token=None, on_delta=None: "INSUFFICIENT_CONTEXT"
    )
    result = answer_question("陷阱问题", FakeRetriever(0.9), settings)
    assert result.refused
    assert not result.from_gate


def test_answer_question_keeps_valid_citation(work_dir, monkeypatch):
    settings = make_settings(work_dir)
    monkeypatch.setattr(
        "app.rag._call_llm", lambda question, candidates, settings, on_first_token=None, on_delta=None: "阈值是 0.35 [1]。"
    )
    result = answer_question("阈值是多少", FakeRetriever(0.9), settings)
    assert not result.refused
    assert [citation.index for citation in result.citations] == [1]
    assert result.citations[0].chunk.doc_id == "notes.md"


def test_format_result_warns_when_no_citation():
    result = RAGResult(
        question="阈值是多少",
        mode="vector",
        answer="阈值是 0.35。",
        refused=False,
        refusal_reason="",
        citations=[],
        retrieved=[make_candidate(0.8)],
        latency_s=0.1,
    )
    rendered = format_result(result)
    assert "未经出处验证" in rendered


def test_format_result_shows_refusal():
    result = RAGResult(
        question="作者养了几只猫",
        mode="vector",
        answer=REFUSAL_TEXT,
        refused=True,
        refusal_reason="模型判断资料不足以回答",
        citations=[],
        retrieved=[make_candidate(0.5)],
        latency_s=0.1,
    )
    rendered = format_result(result)
    assert REFUSAL_TEXT in rendered
    assert "拒答判定" in rendered


def _chunk(text: str, doc_id: str = "notes.md", index: int = 0, score: float = 0.8):
    return Candidate(
        Chunk(id=f"{doc_id}::{index}", doc_id=doc_id, chunk_index=index, text=text),
        score,
    )


def test_date_slot_guard_blocks_far_domain_date_question():
    """q17 复现：资料只有“作业 10 月 21 日截止”，没有“期末考试”日期。"""
    candidates = [
        _chunk("作业 1 于 10 月 21 日截止，提交到课程平台。"),
        _chunk("向量检索用 bge-small-zh，维度 512。", index=1),
    ]
    reason = _date_slot_guard("这门课的期末考试安排在几月几日？", candidates)
    assert reason
    assert "期末考试" in reason


def test_date_slot_guard_allows_supported_date_question():
    candidates = [_chunk("期末考试安排在 2027 年 1 月 8 日，闭卷。")]
    assert _date_slot_guard("期末考试安排在几月几日？", candidates) == ""


def test_date_slot_guard_ignores_non_date_questions():
    candidates = [_chunk("作业 1 于 10 月 21 日截止。")]
    assert _date_slot_guard("BM25 的 k1 控制什么？", candidates) == ""


def test_slot_check_can_refuse_before_calling_llm(work_dir, monkeypatch):
    from dataclasses import replace

    settings = replace(make_settings(work_dir), strict_slot_check=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("槽位不匹配时不应调用大模型")

    monkeypatch.setattr("app.rag._call_llm", fail_if_called)

    class FarDomainRetriever:
        name = "vector"

        def search(self, query: str, top_k: int = 4):
            return [_chunk("作业 1 于 10 月 21 日截止，提交到课程平台。", score=0.9)]

    result = answer_question("这门课的期末考试安排在几月几日？", FarDomainRetriever(), settings)
    assert result.refused
    assert result.from_gate
    assert "期末考试" in result.refusal_reason


def test_answer_question_forwards_streaming_deltas(work_dir, monkeypatch):
    settings = make_settings(work_dir)

    def fake_llm(question, candidates, settings, on_first_token=None, on_delta=None):
        for piece in ("阈值", "是 0.35 [1]。"):
            if on_delta is not None:
                on_delta(piece)
        if on_first_token is not None:
            on_first_token()
        return "阈值是 0.35 [1]。"

    monkeypatch.setattr("app.rag._call_llm", fake_llm)
    seen: list[str] = []
    result = answer_question("阈值是多少", FakeRetriever(0.9), settings, on_delta=seen.append)
    assert "".join(seen) == "阈值是 0.35 [1]。"
    assert not result.refused
