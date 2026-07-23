"""Phase-5 rerank: reorders (never discards or adds to) the SQL-filtered
candidate list by similarity to the fuzzy leftover part of the user's
query - e.g. "для дачи с прицепом" has no structured field to filter on,
but the description/extras text might mention a tow hitch or high ground
clearance. Applied on top of the deterministic SQL filter, not instead of
it: candidates that don't match the fuzzy intent are just ranked lower,
not dropped.
"""
from app.vector.embed import embed_text

# Regression: a full independent sort by similarity was completely
# discarding whatever order the SQL step had already established (e.g.
# prefer_cheap's cheapest-first, prefer_premium's priciest-first) - a car
# could jump from the bottom of a 300-candidate pool to #1 purely because
# its description happened to read like the fuzzy leftover text, even if
# far cheaper/pricier options were sitting right there. The architecture
# says this rerank is second priority, on top of the deterministic order,
# never instead of it - reordering only *within* small bands (keeping the
# bands themselves in their original relative order) is what actually
# delivers that: cheap candidates stay ahead of pricier ones as a whole,
# while the few most semantically relevant within each price tier surface
# first.
_RERANK_BAND_SIZE = 5


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
    result = []
    for i in range(0, len(candidates), _RERANK_BAND_SIZE):
        band = candidates[i : i + _RERANK_BAND_SIZE]

        scored = []
        unscored = []
        for candidate in band:
            vector = candidate.get("embedding")
            if vector is None:
                unscored.append(candidate)
            else:
                scored.append((_cosine_similarity(query_embedding, list(vector)), candidate))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        # Candidates missing an embedding (e.g. ETL hasn't backfilled them
        # yet) are kept, just pushed after every scored candidate in their
        # band rather than lost.
        result.extend([c for _, c in scored] + unscored)

    return result


def rerank_by_free_text_intent(free_text_intent: str | None, candidates: list[dict]) -> list[dict]:
    if not free_text_intent or not candidates:
        return candidates
    query_embedding = embed_text(free_text_intent)
    return rank_candidates_by_vector(query_embedding, candidates)
