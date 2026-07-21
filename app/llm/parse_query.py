from app.api.schemas import CarFilter
from app.config import settings
from app.llm.client import get_client
from app.llm.prompts import PARSE_QUERY_SYSTEM, REFINE_QUERY_SYSTEM

TOOL_NAME = "extract_car_filter"


def _enum_or_string(known_values: list[str]) -> dict:
    schema: dict = {"type": ["string", "null"]}
    if known_values:
        # `enum` constrains the value to exactly these entries - `null` has
        # to be listed explicitly too, or the type-level "null" option
        # would be rejected by validators that check enum membership.
        schema["enum"] = [*known_values, None]
    return schema


def _build_tool_schema(
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
    known_colors: list[str],
    known_fuel_types: list[str],
) -> dict:
    return {
        "name": TOOL_NAME,
        "description": "Извлечь структурированный фильтр автомобиля из запроса клиента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": _enum_or_string(known_cities),
                "price_min": {"type": ["number", "null"]},
                "price_max": {"type": ["number", "null"]},
                "year_min": {"type": ["integer", "null"]},
                "year_max": {"type": ["integer", "null"]},
                "run_max": {"type": ["integer", "null"], "description": "максимальный пробег, км"},
                "mark_id": _enum_or_string(known_marks),
                "body_type": _enum_or_string(known_body_types),
                "color": _enum_or_string(known_colors),
                "drive_type": _enum_or_string(known_drive_types),
                "transmission_type": _enum_or_string(known_transmissions),
                "fuel_type": _enum_or_string(known_fuel_types),
                "doors_count": {"type": ["integer", "null"]},
                "owners_count_max": {"type": ["integer", "null"]},
                "engine_volume_min": {
                    "type": ["number", "null"],
                    "description": "минимальный объём двигателя в литрах, например 1.6",
                },
                "engine_volume_max": {
                    "type": ["number", "null"],
                    "description": "максимальный объём двигателя в литрах",
                },
                "power_hp_min": {
                    "type": ["integer", "null"],
                    "description": "минимальная мощность двигателя, л.с.",
                },
                "power_hp_max": {
                    "type": ["integer", "null"],
                    "description": "максимальная мощность двигателя, л.с.",
                },
                "seats_min": {
                    "type": ["integer", "null"],
                    "description": "минимальное явно названное число мест (например, 'минимум 7 мест')",
                },
                "family_friendly": {
                    "type": ["boolean", "null"],
                    "description": "true, если клиент хочет семейный/вместительный автомобиль",
                },
                "economical": {
                    "type": ["boolean", "null"],
                    "description": "true, если клиент хочет экономичный автомобиль / небольшой расход",
                },
                "prefer_cheap": {
                    "type": ["boolean", "null"],
                    "description": (
                        "true, если клиент хочет недорогой/бюджетный автомобиль, но НЕ назвал "
                        "конкретную сумму (например, 'недорогая первая машина', 'подешевле', "
                        "'бюджетный вариант'). Если названо конкретное число - используй "
                        "price_max, а не этот флаг."
                    ),
                },
                "free_text_intent": {
                    "type": ["string", "null"],
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

_FUEL_TYPE_SYNONYMS = {
    "электро": "электро",
    "электрокар": "электро",
    "электромобиль": "электро",
    "электрический": "электро",
    "на электричестве": "электро",
    "гибрид": "гибрид",
    "гибридный": "гибрид",
    "дизель": "дизель",
    "дизельный": "дизель",
    "бензин": "бензин",
    "бензиновый": "бензин",
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


def _fold(value: str) -> str:
    """Case-insensitive comparison fold that also treats ё/е as the same
    letter ("чёрный" vs "черный") - the feed and user input aren't
    consistent about which one they use."""
    return value.strip().lower().replace("ё", "е")


def _clamp_to_known(value: str | None, known_values: list[str]) -> str | None:
    """The Anthropic API does not hard-enforce JSON schema `enum` values -
    it's a strong hint, not a guarantee. Since city/body_type/mark_id/color/
    drive_type/transmission_type must only ever be real DB values (an
    unfiltered SQL query on a bogus value silently returns zero rows), drop
    anything the model returns that doesn't match one of the known values,
    rather than filtering on a value that can't possibly exist."""
    if value is None or not known_values:
        return value
    for known in known_values:
        if _fold(value) == _fold(known):
            return known
    return None


def _sanitize_partial_update(raw: dict) -> dict:
    """Even with a nullable JSON schema, a model can still emit the literal
    string "null" instead of real JSON null when asked to clear a field
    (this happened in practice) - `model_copy`/`model_validate` don't
    coerce that, so a stray "null" string would otherwise flow straight
    into a SQL parameter bound against a numeric column. Normalize it here
    before it goes anywhere near the filter."""
    return {
        key: (None if isinstance(value, str) and value.strip().lower() == "null" else value)
        for key, value in raw.items()
    }


# Human-readable labels for fields the clamp step can silently drop (e.g.
# the model says mark_id="Mercedes" but there's no Mercedes in stock) - used
# to tell the caller "this constraint was dropped before SQL ever ran" so
# a query like "мерседес джип" can't come back reporting a perfect match
# just because the SQL step, having lost the brand, happened to find SUVs.
_CLAMP_FIELD_LABELS = {
    "city": "город",
    "mark_id": "марка",
    "body_type": "тип кузова",
    "color": "цвет",
    "drive_type": "привод",
    "transmission_type": "коробка передач",
    "fuel_type": "тип двигателя",
}


def _apply_clamping(
    filt: CarFilter,
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
    known_colors: list[str],
    known_fuel_types: list[str],
) -> tuple[CarFilter, list[str]]:
    dropped: list[str] = []

    def _clamp_field(field: str, value: str | None, known_values: list[str]) -> str | None:
        clamped = _clamp_to_known(value, known_values)
        if value is not None and clamped is None:
            dropped.append(_CLAMP_FIELD_LABELS[field])
        return clamped

    filt.city = _clamp_field("city", filt.city, known_cities)
    filt.body_type = _clamp_field("body_type", filt.body_type, known_body_types)
    filt.mark_id = _clamp_field("mark_id", filt.mark_id, known_marks)
    filt.color = _clamp_field("color", filt.color, known_colors)
    filt.drive_type = _clamp_field(
        "drive_type", _normalize_synonym(filt.drive_type, _DRIVE_TYPE_SYNONYMS), known_drive_types
    )
    filt.transmission_type = _clamp_field(
        "transmission_type",
        _normalize_synonym(filt.transmission_type, _TRANSMISSION_SYNONYMS),
        known_transmissions,
    )
    filt.fuel_type = _clamp_field(
        "fuel_type", _normalize_synonym(filt.fuel_type, _FUEL_TYPE_SYNONYMS), known_fuel_types
    )
    return filt, dropped


def parse_query(
    query: str,
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
    known_colors: list[str],
    known_fuel_types: list[str],
) -> tuple[CarFilter, list[str]]:
    """Returns (filter, dropped_field_labels). `dropped_field_labels` lists
    any field the model asked for that isn't a real value in the DB (e.g.
    a brand we don't stock) and was therefore cleared before the SQL step -
    the caller must treat that the same as an unsatisfied constraint, not
    silently degrade to "matches everything on this field"."""
    tool = _build_tool_schema(
        known_cities,
        known_body_types,
        known_marks,
        known_drive_types,
        known_transmissions,
        known_colors,
        known_fuel_types,
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
            filt = CarFilter(**_sanitize_partial_update(block.input))
            return _apply_clamping(
                filt,
                known_cities,
                known_body_types,
                known_marks,
                known_drive_types,
                known_transmissions,
                known_colors,
                known_fuel_types,
            )

    raise RuntimeError("LLM did not call extract_car_filter")


def refine_query(
    base_filter: CarFilter,
    refinement_text: str,
    known_cities: list[str],
    known_body_types: list[str],
    known_marks: list[str],
    known_drive_types: list[str],
    known_transmissions: list[str],
    known_colors: list[str],
    known_fuel_types: list[str],
) -> tuple[CarFilter, list[str]]:
    """Update `base_filter` with a follow-up refinement ("а подешевле?",
    "только с автоматом") instead of re-parsing from scratch - the model is
    told to include only the fields the refinement actually changes, and
    those get merged onto the existing filter (untouched fields keep their
    prior value; a field explicitly set to null clears that constraint).
    """
    tool = _build_tool_schema(
        known_cities,
        known_body_types,
        known_marks,
        known_drive_types,
        known_transmissions,
        known_colors,
        known_fuel_types,
    )

    user_content = (
        f"Текущий фильтр (JSON):\n{base_filter.model_dump_json()}\n\n"
        f"Уточнение клиента: {refinement_text}"
    )

    response = get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=REFINE_QUERY_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            # Validated reconstruction rather than model_copy(update=...):
            # model_copy skips validation/coercion entirely, so any type
            # slip from the model (a stray "null" string once caused a SQL
            # error - see _sanitize_partial_update) would otherwise flow
            # straight through to the database query.
            merged_data = {**base_filter.model_dump(), **_sanitize_partial_update(block.input)}
            merged = CarFilter.model_validate(merged_data)
            return _apply_clamping(
                merged,
                known_cities,
                known_body_types,
                known_marks,
                known_drive_types,
                known_transmissions,
                known_colors,
                known_fuel_types,
            )

    raise RuntimeError("LLM did not call extract_car_filter")
