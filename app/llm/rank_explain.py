import json
from decimal import Decimal

from app.config import settings
from app.llm.client import get_client
from app.llm.prompts import RANK_EXPLAIN_SYSTEM

TOOL_NAME = "select_and_explain"

_CANDIDATE_FIELDS = [
    "unique_id",
    "mark_id",
    "folder_id",
    "modification_id",
    "complectation_name",
    "body_type",
    "drive_type",
    "transmission_type",
    "year",
    "run",
    "owners_number",
    "state",
    "price",
    "currency",
    "max_discount",
    "tradein_discount",
    "credit_discount",
    "insurance_discount",
    "city",
    "poi_id",
]


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _compact_candidate(row: dict) -> dict:
    return {field: _json_safe(row.get(field)) for field in _CANDIDATE_FIELDS}


def _tool_schema() -> dict:
    return {
        "name": TOOL_NAME,
        "description": "Выбрать и объяснить подходящие автомобили из списка кандидатов.",
        "input_schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "unique_id": {"type": "string"},
                            "explanation": {"type": "string"},
                        },
                        "required": ["unique_id", "explanation"],
                    },
                }
            },
            "required": ["results"],
        },
    }


def rank_and_explain(
    query: str, candidates: list[dict], relaxed_fields: list[str] | None = None
) -> list[dict]:
    """Ask the LLM to order and explain every candidate - selection already
    happened deterministically in SQL (see fetch_candidates_with_relaxation),
    so this never drops a car the filter approved, whether there's 1 of
    them or 10.

    Returns a list of {"unique_id", "explanation"} dicts in the order the
    LLM ranked them, one entry per candidate. Caller is responsible for
    joining back to full DB rows.

    `relaxed_fields`, when non-empty, means the SQL step found nothing for
    the exact filter and had to loosen these constraints to find anything -
    the explanation must say so honestly rather than pretend it's a perfect
    match.
    """
    if not candidates:
        return []

    compact = [_compact_candidate(row) for row in candidates]
    known_ids = {c["unique_id"] for c in compact}

    mismatch_note = ""
    if relaxed_fields:
        fields_str = ", ".join(relaxed_fields)
        mismatch_note = (
            f"\n\nВАЖНО: точного совпадения по всем условиям запроса в наличии нет. "
            f"Чтобы показать хоть что-то, пришлось не учитывать: {fields_str}. "
            f"В объяснении по каждому автомобилю честно укажи, чем именно он отличается "
            f"от запроса клиента (например, другой тип кузова или бюджет выше указанного), "
            f"а не только то, что в нём совпадает."
        )

    response = get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=RANK_EXPLAIN_SYSTEM,
        tools=[_tool_schema()],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Запрос клиента: {query}\n\n"
                    f"Кандидаты (JSON), все {len(compact)} шт.:\n"
                    f"{json.dumps(compact, ensure_ascii=False)}"
                    f"{mismatch_note}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            results = [r for r in block.input.get("results", []) if r.get("unique_id") in known_ids]
            # The SQL step already decided every one of these candidates
            # qualifies - if the model dropped one (or all) by mistake,
            # append it at the end with a neutral explanation rather than
            # silently losing a car the filter approved.
            seen_ids = {r["unique_id"] for r in results}
            for candidate_id in known_ids - seen_ids:
                results.append({
                    "unique_id": candidate_id,
                    "explanation": "Подходит по заданным критериям поиска.",
                })
            return results

    raise RuntimeError("LLM did not call select_and_explain")
