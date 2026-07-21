from unittest.mock import MagicMock, patch

import pytest

from app.api.schemas import CarFilter
from app.llm.parse_query import (
    _clamp_to_known,
    _normalize_synonym,
    _DRIVE_TYPE_SYNONYMS,
    _FUEL_TYPE_SYNONYMS,
    _TRANSMISSION_SYNONYMS,
    parse_query,
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


def test_clamp_folds_yo_and_ye_for_color():
    # Feed colors don't use "ё" ("Черный"), but a user or the model might
    # type "чёрный" - must still match, not get dropped as unknown.
    assert _clamp_to_known("чёрный", ["Черный", "Белый"]) == "Черный"
    assert _clamp_to_known("Чёрный", ["Черный", "Белый"]) == "Черный"


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


@pytest.mark.parametrize(
    "user_value", ["электрокар", "электромобиль", "электрический", "на электричестве"]
)
def test_fuel_type_synonyms_normalize_to_elektro(user_value):
    assert _normalize_synonym(user_value, _FUEL_TYPE_SYNONYMS) == "электро"


@pytest.mark.parametrize("user_value", ["дизельный", "дизель"])
def test_fuel_type_synonyms_normalize_to_dizel(user_value):
    assert _normalize_synonym(user_value, _FUEL_TYPE_SYNONYMS) == "дизель"


def _fake_tool_response(tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_car_filter"
    block.input = tool_input
    response = MagicMock()
    response.content = [block]
    return response


def test_refine_query_merges_only_the_changed_field():
    base = CarFilter(city="Москва", mark_ids=["Kia"], price_max=1_000_000)
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"price_max": 700_000}
        )
        updated, dropped = refine_query(
            base,
            "а подешевле?",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=["Kia"],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert updated.price_max == 700_000
    # Untouched fields survive from the base filter - the model wasn't
    # asked to (and didn't) repeat them.
    assert updated.mark_ids == ["Kia"]
    assert updated.city == "Москва"
    assert dropped == []


def test_refine_query_explicit_null_clears_a_constraint():
    base = CarFilter(city="Москва", price_max=1_000_000)
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"price_max": None}
        )
        updated, _dropped = refine_query(
            base,
            "сними ограничение по цене",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
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
        updated, _dropped = refine_query(
            base,
            "сними ограничение по цене",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
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
        updated, dropped = refine_query(
            base,
            "хочу что-то спортивное",
            known_cities=["Москва"],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=["автомат", "механика"],
            known_colors=[],
            known_fuel_types=[],
        )

    # Clamped to None rather than silently filtering on a value that can
    # never match anything - the clamp safety net applies on the refine
    # path too, not just the initial parse.
    assert updated.transmission_type is None
    assert dropped == ["коробка передач"]


def test_parse_query_reports_dropped_field_when_brand_not_in_stock():
    # Regression: "мерседес джип" - no Mercedes in stock. mark_ids gets
    # clamped to None (correct - never filter on a brand that can't
    # exist), but that must be reported as a dropped constraint, not
    # silently treated as "no brand preference". Otherwise the SQL step
    # can find SUVs by body_type alone and the response claims a perfect
    # match despite having ignored the brand entirely.
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"mark_ids": ["Mercedes-Benz"], "body_type": "Внедорожник 5 дв."}
        )
        filt, dropped = parse_query(
            "мерседес джип",
            known_cities=[],
            known_body_types=["Внедорожник 5 дв."],
            known_marks=["Kia", "Hyundai"],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert filt.mark_ids is None
    assert filt.body_type == "Внедорожник 5 дв."
    assert dropped == ["марка"]


def test_parse_query_electric_car_request_clamps_to_known_fuel_type():
    # Regression: "хочу электрокар но так что бы семейная вместительная"
    # returned Cadillac/Rolls-Royce/BMW petrol-diesel giants because
    # fuel_type didn't exist as a field at all - the model's raw
    # "электрокар" must normalize+clamp to the real DB value "электро".
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"fuel_type": "электрокар", "family_friendly": True}
        )
        filt, dropped = parse_query(
            "хочу электрокар но так что бы семейная вместительная",
            known_cities=[],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=["электро", "гибрид", "дизель", "бензин"],
        )

    assert filt.fuel_type == "электро"
    assert filt.family_friendly is True
    assert dropped == []


def test_parse_query_or_marks_partial_drop_when_one_brand_not_in_stock():
    # "Kia или Lamborghini" - Kia is real stock, Lamborghini isn't. The
    # surviving mark should stay in mark_ids, but the drop must still be
    # reported (partial fulfilment isn't the same as "user got exactly
    # what they asked for").
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"mark_ids": ["Kia", "Lamborghini"]}
        )
        filt, dropped = parse_query(
            "kia или ламборгини",
            known_cities=[],
            known_body_types=[],
            known_marks=["Kia", "Hyundai"],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert filt.mark_ids == ["Kia"]
    assert dropped == ["марка"]


def test_parse_query_exclude_color_silently_clamped_without_affecting_exact_match():
    # Excluding a color that isn't real stock changes nothing (there was
    # never anything to exclude), so unlike mark_ids this must NOT be
    # reported as a dropped constraint.
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"exclude_colors": ["Черный", "Розовый"]}
        )
        filt, dropped = parse_query(
            "любой цвет кроме черного и розового",
            known_cities=[],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=["Черный", "Белый"],
            known_fuel_types=[],
        )

    assert filt.exclude_colors == ["Черный"]
    assert dropped == []


def test_parse_query_required_features_unknown_label_reported_as_dropped():
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"required_features": ["панорамная крыша", "телепорт"]}
        )
        filt, dropped = parse_query(
            "хочу панорамную крышу и телепорт",
            known_cities=[],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert filt.required_features == ["панорамная крыша"]
    assert dropped == ["дополнительные опции"]


def test_parse_query_exclude_mark_ids_silently_clamped_without_affecting_exact_match():
    # Excluding a brand that isn't real stock changes nothing - must not be
    # reported as a dropped constraint (unlike a positive mark_ids miss).
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {"exclude_mark_ids": ["Kia", "Lamborghini"]}
        )
        filt, dropped = parse_query(
            "не хочу kia или ламборгини",
            known_cities=[],
            known_body_types=[],
            known_marks=["Kia", "Hyundai"],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert filt.exclude_mark_ids == ["Kia"]
    assert dropped == []


def test_parse_query_passes_through_new_boolean_and_freeform_fields():
    with patch("app.llm.parse_query.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _fake_tool_response(
            {
                "recent_only": True,
                "low_mileage": True,
                "not_registered_in_russia": True,
                "complectation_keyword": "Premium",
            }
        )
        filt, dropped = parse_query(
            "новая машина с маленьким пробегом, серый привоз, комплектация Premium",
            known_cities=[],
            known_body_types=[],
            known_marks=[],
            known_drive_types=[],
            known_transmissions=[],
            known_colors=[],
            known_fuel_types=[],
        )

    assert filt.recent_only is True
    assert filt.low_mileage is True
    assert filt.not_registered_in_russia is True
    assert filt.complectation_keyword == "Premium"
    assert dropped == []
