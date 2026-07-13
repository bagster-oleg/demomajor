"""Phase-5 embedding generation - reranks the already SQL-filtered
candidate list for fuzzy intent ("для дачи с прицепом", "чтобы зимой
уверенно"), never used as the primary filter. Runs fully local/offline
(fastembed + ONNX), no extra API key needed.
"""
from functools import lru_cache

from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)


def build_embedding_text(description: str | None, extras: str | None) -> str:
    """Real feed descriptions repeat a long dealership marketing footer
    ("MAJOR EXPERT — ЛИДЕР ПО ПРОДАЖЕ..." etc.) on almost every car - that
    boilerplate would dominate the embedding and erase any actual signal.
    Keep only the text before that footer, plus the full extras list where
    the distinguishing equipment/condition details actually are."""
    desc = (description or "").split("MAJOR EXPERT")[0].strip()
    parts = [p for p in (desc, extras) if p]
    return "\n".join(parts)


def embed_text(text: str) -> list[float]:
    return next(iter(_model().embed([text]))).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vec.tolist() for vec in _model().embed(texts)]
