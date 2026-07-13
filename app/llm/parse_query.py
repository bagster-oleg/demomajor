from app.api.schemas import CarFilter
from app.config import settings
from app.llm.client import get_client
from app.llm.prompts import PARSE_QUERY_SYSTEM

TOOL_NAME = "extract_car_filter"


def _enum_or_string(known_values: list[str]) -> dict:
    schema = {"type": "string"}
    if known_values:
        schema["enum"] = known_values
    return schema


def _build_tool_schema(
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
) -> dict:
    return {
        "name": TOOL_NAME,
        "description": "Извлечь структурированный фильтр автомобиля из запроса клиента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": _enum_or_string(known_cities),
                "price_min": {"type": "number"},
                "price_max": {"type": "number"},
                "year_min": {"type": "integer"},
                "year_max": {"type": "integer"},
                "run_max": {"type": "integer", "description": "максимальный пробег, км"},
                "mark_id": _enum_or_string(known_marks),
                "body_type": _enum_or_string(known_body_types),
                "drive_type": _enum_or_string(known_drive_types),
                "transmission_type": _enum_or_string(known_transmissions),
                "doors_count": {"type": "integer"},
                "owners_count_max": {"type": "integer"},
                "free_text_intent": {
                    "type": "string",
                    "description": "нечёткая часть запроса, не сводимая к остальным полям",
                },
            },
        },
    }


# Synonyms customers actually type, mapped to the canonical label our
# transmission_type/drive_type heuristic derives during ETL (see
# app/etl/feed_parser.py). Applied before clamping, so "АКПП" or
# "автоматическая коробка" resolve to the same real DB value as "автомат"
# instead of being dropped as unknown.
_TRANSMISSION_SYNONYMS = {
    "акпп": "автомат",
    "мкпп": "механика",
    "автоматическая": "автомат",
    "автоматическая коробка": "автомат",
    "автоматическую": "автомат",
    "автомат": "автомат",
    "робот": "автомат",
    "роботизированная": "автомат",
    "вариатор": "автомат",
    "cvt": "автомат",
    "механика": "механика",
    "механическая": "механика",
    "ручная": "механика",
    "ручку": "механика",
}

_DRIVE_TYPE_SYNONYMS = {
    "полный привод": "4WD",
    "полный": "4WD",
    "4x4": "4WD",
    "4wd": "4WD",
    "awd": "AWD",
    "передний привод": "FWD",
    "передний": "FWD",
    "fwd": "FWD",
}


def _normalize_synonym(value: str | None, synonyms: dict[str, str]) -> str | None:
    if value is None:
        return None
    return synonyms.get(value.strip().lower(), value)


def _clamp_to_known(value: str | None, known_values: list[str]) -> str | None:
    """The Anthropic API does not hard-enforce JSON schema `enum` values -
    it's a strong hint, not a guarantee. Since city/body_type/mark_id/
    drive_type/transmission_type must only ever be real DB values (an
    unfiltered SQL query on a bogus value silently returns zero rows), drop
    anything the model returns that doesn't match one of the known values,
    rather than filtering on a value that can't possibly exist."""
    if value is None or not known_values:
        return value
    for known in known_values:
        if value.strip().lower() == known.strip().lower():
            return known
    return None


def parse_query(
    query: str,
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
) -> CarFilter:
    tool = _build_tool_schema(
        known_cities, known_body_types, known_marks, known_drive_types, known_transmissions
    )

    response = get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=PARSE_QUERY_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": query}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            filt = CarFilter(**block.input)
            filt.city = _clamp_to_known(filt.city, known_cities)
            filt.body_type = _clamp_to_known(filt.body_type, known_body_types)
            filt.mark_id = _clamp_to_known(filt.mark_id, known_marks)
            filt.drive_type = _clamp_to_known(
                _normalize_synonym(filt.drive_type, _DRIVE_TYPE_SYNONYMS), known_drive_types
            )
            filt.transmission_type = _clamp_to_known(
                _normalize_synonym(filt.transmission_type, _TRANSMISSION_SYNONYMS),
                known_transmissions,
            )
            return filt

    raise RuntimeError("LLM did not call extract_car_filter")
