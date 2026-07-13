from unittest.mock import MagicMock, patch

import pytest

from app.api.schemas import CarFilter
from app.llm.parse_query import (
    _clamp_to_known,
    _normalize_synonym,
    _DRIVE_TYPE_SYNONYMS,
    _TRANSMISSION_SYNONYMS,
    refine_query,
)


def test_clamp_exact_match_passthrough():
    assert _clamp_to_known("автомат", ["автомат", "механика"]) == "автомат"


def test_clamp_case_insensitive_match_returns_canonical():
    assert _clamp_to_known("АВТОМАТ", ["автомат", "механика"]) == "автомат"


def test_clamp_unknown_value_drops_to_none():
    # The Anthropic API doesn't hard-enforce tool-schema enums, so a model
    # can still emit a value like "Автоматическая" that isn't one of the
    # real values in the DB - that must not silently become a SQL filter
    # that can never match anything.
    assert _clamp_to_known("Автоматическая", ["автомат", "механика"]) is None


def test_clamp_none_passthrough():
    assert _clamp_to_known(None, ["автомат"]) is None


def test_clamp_with_empty_known_list_passes_through_unchanged():
    assert _clamp_to_known("что угодно", []) == "что угодно"


@pytest.mark.parametrize(
    "user_value",
    ["АКПП", "акпп", "автоматическая", "автоматическая коробка", "робот", "вариатор", "CVT"],
)
def test_transmission_synonyms_normalize_to_avtomat(user_value):
    assert _normalize_synonym(user_value, _TRANSMISSION_SYNONYMS) == "автомат"


@pytest.mark.parametrize("user_value", ["МКПП", "механическая", "ручная"])
def test_transmission_synonyms_normalize_to_mehanika(user_value):
    assert _normalize_synonym(user_value, _TRANSMISSION_SYNONYMS) == "механика"


def test_full_pipeline_akpp_clamps_to_known_avtomat():
    # end-to-end: a raw "АКПП" from the model should survive normalization
    # + clamping and land on the real DB value "автомат".
    normalized = _normalize_synonym("АКПП", _TRANSMISSION_SYNONYMS)
    assert _clamp_to_known(normalized, ["автомат", "механика"]) == "автомат"


@pytest.mark.parametrize("user_value", ["полный привод", "4x4", "4WD"])
def test_drive_type_synonyms_normalize_to_4wd(user_value):
    assert _normalize_synonym(user_value, _DRIVE_TYPE_SYNONYMS) == "4WD"


def _fake_tool_response(tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_car_filter"
    block.input = tool_input
    response = MagicMock()
    response.content = [block]
    return response


def test_refine_query_merges_only_the_changed_field():
    base = CarFilter(city="Москва", mark_id="Kia", price_max=1_000_000)
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"price_max": 700_000}
        )
        updated = refine_query(
            base,
            "а подешевле?",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=["Kia"],
            known_drive_types=[],
            known_transmissions=[],
        )

    assert updated.price_max == 700_000
    # Untouched fields survive from the base filter - the model wasn't
    # asked to (and didn't) repeat them.
    assert updated.mark_id == "Kia"
    assert updated.city == "Москва"


def test_refine_query_explicit_null_clears_a_constraint():
    base = CarFilter(city="Москва", price_max=1_000_000)
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"price_max": None}
        )
        updated = refine_query(
            base,
            "сними ограничение по цене",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
        )

    assert updated.price_max is None
    assert updated.city == "Москва"


def test_refine_query_string_literal_null_is_treated_as_real_none():
    # Regression: caught live when a refinement ("сними ограничение по
    # цене") made the model emit the literal string "null" instead of
    # JSON null for price_max (its schema type didn't allow null at the
    # time). model_copy(update=...) doesn't validate/coerce, so the string
    # "null" flowed straight into a SQL query bound against a numeric
    # column and crashed with a 503. Must come out as real None, not "null".
    base = CarFilter(city="Москва", price_max=1_000_000)
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"price_max": "null"}
        )
        updated = refine_query(
            base,
            "сними ограничение по цене",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
        )

    assert updated.price_max is None
    assert not isinstance(updated.price_max, str)


def test_refine_query_clamps_new_value_against_known_list():
    base = CarFilter(city="Москва")
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        # Not a real DB value and not in the synonym table either - a
        # value the model shouldn't emit given the enum, but the API
        # doesn't hard-enforce that.
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"transmission_type": "Спортивная"}
        )
        updated = refine_query(
            base,
            "хочу что-то спортивное",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=["автомат", "механика"],
        )

    # Clamped to None rather than silently filtering on a value that can
    # never match anything - the clamp safety net applies on the refine
    # path too, not just the initial parse.
    assert updated.transmission_type is None
