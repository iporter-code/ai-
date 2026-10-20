import numpy as np

from app.corpus import Chunk
from app.retrievers import (
    BM25Retriever,
    Candidate,
    VectorRetriever,
    query_coverage,
    tokenize,
)


def make_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="notes.md::0",
            doc_id="notes.md",
            chunk_index=0,
            text="向量模型选用 BAAI/bge-small-zh-v1.5，embedding 维度是 512。",
        ),
        Chunk(
            id="diary.txt::0",
            doc_id="diary.txt",
            chunk_index=0,
            text="今天去莫干山徒步，全程十二公里，中午吃了笋干面。",
        ),
        Chunk(
            id="diary.txt::1",
            doc_id="diary.txt",
            chunk_index=1,
            text="茶室老板养了一只叫豆豆的柴犬。",
        ),
    ]


def test_tokenize_keeps_chinese_words_and_english_tokens():
    tokens = tokenize("向量检索用 embedding 模型")
    assert "embedding" in tokens
    assert "模型" in tokens
    assert "向量" in tokens


def test_bm25_ranks_relevant_chunk_first():
    retriever = BM25Retriever(make_chunks())
    results = retriever.search("向量模型 embedding 维度", top_k=3)
    assert results
    assert results[0].chunk.doc_id == "notes.md"


def test_bm25_returns_empty_for_unrelated_query():
    retriever = BM25Retriever(make_chunks())
    assert retriever.search("量子纠缠", top_k=3) == []


def test_query_coverage_counts_all_query_terms():
    candidate = Candidate(make_chunks()[1], 1.0)
    assert query_coverage("莫干山 徒步", [candidate]) == 1.0
    partial = query_coverage("莫干山 雪山", [candidate])
    assert 0.0 < partial < 1.0
    assert query_coverage("量子纠缠", [candidate]) == 0.0


class FakeEmbedder:
    def embed(self, texts, batch_size=32):
        for text in texts:
            if "向量" in text:
                yield np.array([1.0, 0.0], dtype=np.float32)
            else:
                yield np.array([0.0, 1.0], dtype=np.float32)


def test_vector_retriever_ranks_by_cosine(work_dir, monkeypatch):
    monkeypatch.setattr(VectorRetriever, "_get_model", lambda self: FakeEmbedder())
    retriever = VectorRetriever(
        make_chunks(), "fake", work_dir / "index", work_dir / "cache"
    )
    results = retriever.search("向量检索", top_k=2)
    assert results[0].chunk.doc_id == "notes.md"
    assert results[0].score > results[1].score
