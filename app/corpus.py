import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf"}


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    chunk_index: int
    text: str


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def load_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return _read_text(path)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def _tail(text: str, overlap: int) -> str:
    if overlap <= 0:
        return ""
    return text[-overlap:].strip()


def split_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size // 2))

    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
            continue
        buffer = ""
        for sentence in _split_sentences(paragraph):
            if len(sentence) > chunk_size:
                if buffer:
                    units.append(buffer)
                    buffer = ""
                units.extend(
                    sentence[i : i + chunk_size]
                    for i in range(0, len(sentence), chunk_size)
                )
            elif len(buffer) + len(sentence) <= chunk_size:
                buffer += sentence
            else:
                if buffer:
                    units.append(buffer)
                buffer = sentence
        if buffer:
            units.append(buffer)

    chunks: list[str] = []
    current = ""
    for unit in units:
        separator = "\n" if current else ""
        if len(current) + len(separator) + len(unit) <= chunk_size:
            current += separator + unit
            continue
        if current:
            chunks.append(current)
            carry = _tail(current, overlap)
        else:
            carry = ""
        candidate = f"{carry}\n{unit}" if carry else unit
        current = candidate if len(candidate) <= chunk_size else unit
    if current:
        chunks.append(current)
    return chunks


def build_chunks(
    raw_dir: Path, chunk_size: int = 500, overlap: int = 80
) -> tuple[list[Chunk], list[str]]:
    chunks: list[Chunk] = []
    empty_docs: list[str] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        doc_id = path.relative_to(raw_dir).as_posix()
        text = load_document(path)
        pieces = split_text(text, chunk_size, overlap)
        if not pieces:
            empty_docs.append(doc_id)
        for index, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    id=f"{doc_id}::{index}",
                    doc_id=doc_id,
                    chunk_index=index,
                    text=piece,
                )
            )
    return chunks, empty_docs


def save_chunks(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(chunk) for chunk in chunks]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_chunks(path: Path) -> list[Chunk]:
    if not path.exists():
        raise FileNotFoundError(
            f"找不到切分索引 {path}，请先运行：python -m app.cli ingest"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Chunk(**item) for item in payload]
