import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    vector_min_score: float
    bm25_min_coverage: float
    temperature: float
    raw_dir: Path
    index_dir: Path
    embedding_cache_dir: Path | None = None
    embedding_model_path: Path | None = None
    embedding_query_prefix: str = ""
    strict_slot_check: bool = False

    @property
    def chunks_path(self) -> Path:
        return self.index_dir / "chunks.json"

    @property
    def vector_dir(self) -> Path:
        return self.index_dir / "vector"


def get_settings() -> Settings:
    local_model = ROOT / ".models" / "bge-small-zh-v1.5"
    configured_model_path = os.getenv("EMBEDDING_MODEL_PATH", "").strip()
    if configured_model_path:
        embedding_model_path: Path | None = Path(configured_model_path)
    elif local_model.exists():
        embedding_model_path = local_model
    else:
        embedding_model_path = None
    return Settings(
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "300")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        top_k=int(os.getenv("TOP_K", "4")),
        vector_min_score=float(os.getenv("VECTOR_MIN_SCORE", "0.40")),
        bm25_min_coverage=float(os.getenv("BM25_MIN_COVERAGE", "0.30")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        raw_dir=ROOT / "data" / "raw",
        index_dir=ROOT / "data" / "index",
        embedding_cache_dir=Path(
            os.getenv("FASTEMBED_CACHE_DIR", ROOT / ".cache" / "fastembed")
        ),
        embedding_model_path=embedding_model_path,
        embedding_query_prefix=os.getenv("EMBEDDING_QUERY_PREFIX", ""),
        strict_slot_check=os.getenv("STRICT_SLOT_CHECK", "0").strip().lower()
        in {"1", "true", "yes", "on"},
    )
