import pytest

from app.llm.parse_query import _clamp_to_known, _normalize_synonym, _DRIVE_TYPE_SYNONYMS, _TRANSMISSION_SYNONYMS


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
