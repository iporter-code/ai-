import pytest

from app.corpus import Chunk
from app.retrievers import Candidate
from scripts.evaluate import is_retrieval_hit, validate_questions


def make_questions():
    questions = []
    for index in range(20):
        kind = "doc" if index < 10 else ("trap" if index < 15 else "multi_hop")
        item = {
            "id": f"q{index + 1}",
            "type": kind,
            "question": "问题",
            "standard_answer": "答案",
            "source_docs": [] if kind == "trap" else ["d.md"],
            "evidence": [] if kind == "trap" else ["证据句"],
        }
        questions.append(item)
    return questions


def test_validate_questions_accepts_exact_mix():
    chunks = [Chunk("d.md::0", "d.md", 0, "这里有一句证据句。")]
    validate_questions(make_questions(), chunks)


def test_validate_questions_rejects_bad_evidence():
    chunks = [Chunk("d.md::0", "d.md", 0, "这里没有目标句子。")]
    with pytest.raises(ValueError):
        validate_questions(make_questions(), chunks)


def test_retrieval_hit_uses_top3():
    chunk = Chunk("d.md::0", "d.md", 0, "证据句在片段里。")
    item = {"type": "doc", "source_docs": ["d.md"], "evidence": ["证据句"]}
    assert is_retrieval_hit(item, [Candidate(chunk, 1.0)])
    assert not is_retrieval_hit(item, [])
