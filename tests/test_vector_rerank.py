from app.vector.embed import build_embedding_text
from app.vector.rerank import rank_candidates_by_vector


def test_build_embedding_text_strips_marketing_footer():
    description = (
        "Отличный кроссовер для дачи, есть фаркоп.\n\n"
        "MAJOR EXPERT — ЛИДЕР ПО ПРОДАЖЕ АВТО С ПРОБЕГОМ В МОСКВЕ\n"
        "✅ Более 2 500 проверенных автомобилей с пробегом\n"
    )
    text = build_embedding_text(description, "Фаркоп, полный привод")
    assert "MAJOR EXPERT" not in text
    assert "фаркоп" in text.lower()
    assert "Фаркоп, полный привод" in text


def test_build_embedding_text_handles_missing_fields():
    assert build_embedding_text(None, None) == ""
    assert build_embedding_text(None, "Экстра") == "Экстра"
    assert build_embedding_text("Описание", None) == "Описание"


def test_rank_candidates_orders_by_cosine_similarity_descending():
    query = [1.0, 0.0]
    candidates = [
        {"unique_id": "a", "embedding": [0.0, 1.0]},  # orthogonal - worst
        {"unique_id": "b", "embedding": [1.0, 0.0]},  # identical - best
        {"unique_id": "c", "embedding": [0.7, 0.7]},  # middling
    ]
    ranked = rank_candidates_by_vector(query, candidates)
    assert [c["unique_id"] for c in ranked] == ["b", "c", "a"]


def test_rank_candidates_keeps_but_deprioritizes_missing_embeddings():
    query = [1.0, 0.0]
    candidates = [
        {"unique_id": "no-embedding", "embedding": None},
        {"unique_id": "match", "embedding": [1.0, 0.0]},
    ]
    ranked = rank_candidates_by_vector(query, candidates)
    # Nothing is dropped - the fuzzy rerank sits on top of the SQL filter,
    # it never removes a candidate the SQL step already approved.
    assert len(ranked) == 2
    assert ranked[0]["unique_id"] == "match"
    assert ranked[-1]["unique_id"] == "no-embedding"


def test_rank_candidates_never_drops_any_candidate():
    query = [1.0, 0.0, 0.0]
    candidates = [{"unique_id": str(i), "embedding": [0.1 * i, 1.0, 0.0]} for i in range(5)]
    ranked = rank_candidates_by_vector(query, candidates)
    assert {c["unique_id"] for c in ranked} == {c["unique_id"] for c in candidates}
