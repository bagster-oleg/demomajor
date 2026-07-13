from app.llm.parse_query import _clamp_to_known


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
