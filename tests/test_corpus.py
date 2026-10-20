from pypdf import PdfWriter

from app.corpus import load_document, split_text


def test_split_respects_chunk_size():
    text = "这是一个用于测试的句子，包含足够多的字符。" * 200
    chunks = split_text(text, chunk_size=120, overlap=30)
    assert chunks
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)


def test_split_keeps_overlap_between_neighbors():
    text = "甲" * 60 + "。" + "乙" * 60 + "。" + "丙" * 60 + "。"
    chunks = split_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0][-20:].strip() in chunks[1]


def test_long_paragraph_without_punctuation_is_hard_split():
    text = "无标点内容" * 300
    chunks = split_text(text, chunk_size=100, overlap=10)
    assert chunks
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_empty_text_returns_no_chunks():
    assert split_text("   \n\n  ", chunk_size=100, overlap=10) == []


def test_pdf_document_branch_is_readable(work_dir):
    path = work_dir / "blank.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    assert load_document(path) == ""
