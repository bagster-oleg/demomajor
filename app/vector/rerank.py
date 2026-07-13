"""Phase-5 rerank: reorders (never discards or adds to) the SQL-filtered
candidate list by similarity to the fuzzy leftover part of the user's
query - e.g. "для дачи с прицепом" has no structured field to filter on,
but the description/extras text might mention a tow hitch or high ground
clearance. Applied on top of the deterministic SQL filter, not instead of
it: candidates that don't match the fuzzy intent are just ranked lower,
not dropped.
"""
from app.vector.embed import embed_text


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_candidates_by_vector(query_embedding: list[float], candidates: list[dict]) -> list[dict]:
    """Pure ordering logic, kept separate from embed_text() so it's
    testable without loading the actual embedding model."""
    scored = []
    unscored = []
    for candidate in candidates:
        vector = candidate.get("embedding")
        if vector is None:
            unscored.append(candidate)
        else:
            scored.append((_cosine_similarity(query_embedding, list(vector)), candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    # Candidates missing an embedding (e.g. ETL hasn't backfilled them yet)
    # are kept, just pushed after every scored candidate rather than lost.
    return [c for _, c in scored] + unscored


def rerank_by_free_text_intent(free_text_intent: str | None, candidates: list[dict]) -> list[dict]:
    if not free_text_intent or not candidates:
        return candidates
    query_embedding = embed_text(free_text_intent)
    return rank_candidates_by_vector(query_embedding, candidates)
