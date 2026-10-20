import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import jieba
import numpy as np

from .corpus import Chunk

jieba.setLogLevel(logging.WARNING)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]+")

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "有", "为", "对", "被", "把",
    "就", "也", "都", "而", "但", "并", "很", "还", "又", "中", "上", "下", "里",
    "我", "你", "他", "她", "它", "们", "这", "那", "哪", "什么", "如何", "怎么",
    "为什么", "哪些", "请问", "请", "吗", "呢", "啊", "吧", "一个", "一种", "这个",
    "那个", "可以", "是否", "多少", "以及", "其中", "关于",
}


@dataclass(frozen=True)
class Candidate:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if _HAN_RE.fullmatch(raw):
            tokens.extend(jieba.lcut_for_search(raw))
        else:
            tokens.append(raw)
    return [token for token in tokens if token.strip() and token not in STOPWORDS]


def query_coverage(query: str, candidates: list[Candidate]) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    context_tokens = set(tokenize(" ".join(c.chunk.text for c in candidates)))
    return len(query_tokens & context_tokens) / len(query_tokens)


class BM25Retriever:
    name = "bm25"
    label = "关键词检索 (BM25)"

    def __init__(self, chunks: list[Chunk]):
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        self._corpus_tokens = [tokenize(chunk.text) for chunk in chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens) if chunks else None

    def search(self, query: str, top_k: int = 4) -> list[Candidate]:
        if self._bm25 is None:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            Candidate(self.chunks[int(index)], float(scores[int(index)]))
            for index in order
            if scores[int(index)] > 0
        ]


class VectorRetriever:
    name = "vector"
    label = "向量检索 (bge-small-zh)"

    def __init__(
        self,
        chunks: list[Chunk],
        model_name: str,
        index_dir: Path,
        cache_dir: Path | None = None,
        model_path: Path | None = None,
        query_prefix: str = "",
    ):
        self.chunks = chunks
        self.model_name = model_name
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.model_path = Path(model_path) if model_path else None
        self.query_prefix = query_prefix
        self._model = None
        self._embeddings = self._load_or_build()

    def _fingerprint(self) -> str:
        digest = hashlib.sha1()
        digest.update(self.model_name.encode("utf-8"))
        for chunk in self.chunks:
            digest.update(chunk.id.encode("utf-8"))
            digest.update(chunk.text.encode("utf-8"))
        return digest.hexdigest()

    def _load_or_build(self) -> np.ndarray:
        meta_path = self.index_dir / "meta.json"
        embeddings_path = self.index_dir / "embeddings.npy"
        fingerprint = self._fingerprint()
        if meta_path.exists() and embeddings_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (
                meta.get("fingerprint") == fingerprint
                and meta.get("count") == len(self.chunks)
            ):
                return np.load(embeddings_path)

        embeddings = self._embed_texts([chunk.text for chunk in self.chunks])
        np.save(embeddings_path, embeddings)
        meta_path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "model": self.model_name,
                    "count": len(self.chunks),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return embeddings

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            if self.cache_dir is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir) if self.cache_dir else None,
                specific_model_path=(
                    str(self.model_path) if self.model_path else None
                ),
            )
        return self._model

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        vectors = np.asarray(
            list(self._get_model().embed(texts, batch_size=32)), dtype=np.float32
        )
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-8)

    def search(self, query: str, top_k: int = 4) -> list[Candidate]:
        if not self.chunks:
            return []
        query_vector = np.asarray(
            next(iter(self._get_model().embed([self.query_prefix + query]))),
            dtype=np.float32,
        )
        query_vector = query_vector / max(float(np.linalg.norm(query_vector)), 1e-8)
        scores = self._embeddings @ query_vector
        order = np.argsort(scores)[::-1][:top_k]
        return [
            Candidate(self.chunks[int(index)], float(scores[int(index)]))
            for index in order
        ]


def load_retriever(mode: str, chunks: list[Chunk], settings):
    if mode == "bm25":
        return BM25Retriever(chunks)
    if mode == "vector":
        return VectorRetriever(
            chunks,
            settings.embedding_model,
            settings.vector_dir,
            settings.embedding_cache_dir,
            settings.embedding_model_path,
            settings.embedding_query_prefix,
        )
    raise ValueError(f"未知检索方式：{mode}（可选 bm25 / vector）")
