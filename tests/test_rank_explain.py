import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.llm.rank_explain import _compact_candidate, rank_and_explain


def test_compact_candidate_converts_decimal_to_json_safe_float():
    row = {
        "unique_id": "123",
        "mark_id": "Kia",
        "folder_id": "Rio",
        "modification_id": None,
        "complectation_name": None,
        "body_type": "Седан",
        "drive_type": None,
        "transmission_type": "автомат",
        "year": 2020,
        "run": 50000,
        "owners_number": "Один владелец",
        "state": "Отличное",
        "price": Decimal("950000.00"),
        "currency": "RUR",
        "max_discount": Decimal("60000.00"),
        "tradein_discount": Decimal("0"),
        "credit_discount": Decimal("0"),
        "insurance_discount": Decimal("0"),
        "city": "Москва",
        "poi_id": "где-то",
    }

    compact = _compact_candidate(row)

    # Must not raise - this is what caught the original Decimal bug.
    json.dumps(compact, ensure_ascii=False)
    assert compact["price"] == 950000.0
    assert isinstance(compact["price"], float)


def _fake_select_and_explain_response(results: list[dict]):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "select_and_explain"
    block.input = {"results": results}
    response = MagicMock()
    response.content = [block]
    return response


def test_rank_and_explain_returns_all_candidates_not_just_a_top_pick():
    candidates = [{"unique_id": str(i)} for i in range(5)]
    with patch("app.llm.rank_explain.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = (
            _fake_select_and_explain_response(
                [{"unique_id": str(i), "explanation": f"ok {i}"} for i in range(5)]
            )
        )
        results = rank_and_explain("любой запрос", candidates)

    assert len(results) == 5


def test_rank_and_explain_recovers_a_candidate_the_model_dropped():
    # Selection already happened in SQL - if the model forgets one of the
    # candidates it was given, that car must still show up rather than
    # silently vanishing.
    candidates = [{"unique_id": "a"}, {"unique_id": "b"}]
    with patch("app.llm.rank_explain.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = (
            _fake_select_and_explain_response([{"unique_id": "a", "explanation": "ok a"}])
        )
        results = rank_and_explain("любой запрос", candidates)

    assert {r["unique_id"] for r in results} == {"a", "b"}
    recovered = next(r for r in results if r["unique_id"] == "b")
    assert recovered["explanation"]
