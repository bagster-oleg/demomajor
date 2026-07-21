"""Deterministic SQL filtering over the cars table.

This is the layer that turns a CarFilter into a plain indexed SQL query -
no embeddings, no similarity search. Price/year/mileage/availability are
facts, not vibes.
"""
from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection

from app.api.schemas import CarFilter
from app.db.models import cars

DEFAULT_CANDIDATE_LIMIT = 30

# Thresholds behind the two semantic preferences, kept in code (not guessed
# by the LLM) so "экономичный"/"семейный" mean the same thing every time.
ECONOMICAL_MAX_ENGINE_L = 1.6  # "экономичный" -> small engine, a real number
FAMILY_MIN_SEATS = 5  # "семейный" -> room for a family


def build_candidate_query(filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT):
    conditions = [cars.c.is_active.is_(True)]

    if filt.city:
        conditions.append(cars.c.city == filt.city)
    if filt.mark_id:
        conditions.append(func.lower(cars.c.mark_id) == filt.mark_id.lower())
    if filt.body_type:
        conditions.append(cars.c.body_type.ilike(f"%{filt.body_type}%"))
    if filt.color:
        conditions.append(func.lower(cars.c.color) == filt.color.lower())
    if filt.drive_type:
        conditions.append(cars.c.drive_type == filt.drive_type)
    if filt.transmission_type:
        conditions.append(cars.c.transmission_type == filt.transmission_type)
    if filt.fuel_type:
        conditions.append(func.lower(cars.c.fuel_type) == filt.fuel_type.lower())
    if filt.year_min is not None:
        conditions.append(cars.c.year >= filt.year_min)
    if filt.year_max is not None:
        conditions.append(cars.c.year <= filt.year_max)
    if filt.run_max is not None:
        conditions.append(cars.c.run <= filt.run_max)
    if filt.price_min is not None:
        conditions.append(cars.c.price >= filt.price_min)
    if filt.price_max is not None:
        conditions.append(cars.c.price <= filt.price_max)
    if filt.doors_count is not None:
        conditions.append(cars.c.doors_count == filt.doors_count)
    if filt.owners_count_max is not None:
        conditions.append(cars.c.owners_count <= filt.owners_count_max)
    if filt.engine_volume_min is not None:
        conditions.append(cars.c.engine_volume_l >= filt.engine_volume_min)
    if filt.engine_volume_max is not None:
        conditions.append(cars.c.engine_volume_l <= filt.engine_volume_max)
    if filt.power_hp_min is not None:
        conditions.append(cars.c.power_hp >= filt.power_hp_min)
    if filt.power_hp_max is not None:
        conditions.append(cars.c.power_hp <= filt.power_hp_max)
    if filt.seats_min is not None:
        conditions.append(cars.c.seats >= filt.seats_min)
    if filt.economical:
        # A real number (engine displacement) is the honest best proxy the
        # feed supports - it has no fuel-consumption figures at all.
        conditions.append(cars.c.engine_volume_l <= ECONOMICAL_MAX_ENGINE_L)
    if filt.family_friendly:
        conditions.append(cars.c.seats >= FAMILY_MIN_SEATS)
    if filt.prefer_cheap and filt.price_max is None:
        # "недорогая"/"бюджетная" with no stated number - rather than invent
        # a cutoff, cap it at the real median price of currently matching
        # stock (computed from the conditions gathered so far), so it's
        # always grounded in what's actually in inventory right now instead
        # of a fixed number that goes stale as prices/stock change.
        median_price = (
            select(func.percentile_cont(0.5).within_group(cars.c.price.asc()))
            .where(and_(*conditions))
            .scalar_subquery()
        )
        conditions.append(cars.c.price <= median_price)

    # Heuristic ordering: within budget, a higher price usually means a
    # better-equipped trim, so surface those first; break ties by discount
    # size and recency of model year. "недорогая" without a stated budget
    # means the opposite - cheapest genuinely first.
    order = []
    if filt.prefer_cheap:
        order.append(cars.c.price.asc())
    elif filt.price_max is not None:
        order.append(cars.c.price.desc())
    order.append(cars.c.max_discount.desc().nullslast())
    order.append(cars.c.year.desc())

    return select(cars).where(and_(*conditions)).order_by(*order).limit(limit)


def fetch_candidates(conn: Connection, filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT) -> list[dict]:
    stmt = build_candidate_query(filt, limit=limit)
    rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


# Order to drop constraints in when the exact filter matches nothing, from
# least to most likely to be the thing the user actually cares about.
# `city` and `free_text_intent` are never touched here: city is an explicit
# UI choice, and free_text_intent was never a SQL condition to begin with.
_RELAX_FIELD_ORDER = [
    "doors_count",
    "owners_count_max",
    "color",
    "fuel_type",
    "power_hp_min",
    "power_hp_max",
    "engine_volume_min",
    "engine_volume_max",
    "economical",
    "drive_type",
    "transmission_type",
    "run_max",
    "seats_min",
    "family_friendly",
    "prefer_cheap",
    "body_type",
    "year_min",
    "year_max",
]

_RELAX_FIELD_LABELS = {
    "doors_count": "количество дверей",
    "owners_count_max": "число владельцев",
    "color": "цвет",
    "fuel_type": "тип двигателя",
    "power_hp_min": "мощность двигателя",
    "power_hp_max": "мощность двигателя",
    "engine_volume_min": "объём двигателя",
    "engine_volume_max": "объём двигателя",
    "economical": "экономичность",
    "drive_type": "привод",
    "transmission_type": "коробка передач",
    "run_max": "пробег",
    "seats_min": "количество мест",
    "family_friendly": "вместимость (семейный)",
    "prefer_cheap": "бюджетное ограничение",
    "body_type": "тип кузова",
    "year_min": "год выпуска",
    "year_max": "год выпуска",
    "price_max": "бюджет",
    "mark_id": "марка",
}

_PRICE_WIDEN_FACTOR = 1.2


def fetch_candidates_with_relaxation(
    conn: Connection, filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> tuple[list[dict], bool, list[str]]:
    """Try the filter exactly as given. If nothing matches, relax it one
    constraint at a time (deterministic, cheapest-first order) until
    something in stock matches - so "no results" only happens when nothing
    in the current inventory is even remotely close, and the user always
    gets real cars, never invented ones, plus an honest account of what
    was loosened to find them.

    Returns (candidates, exact_match, relaxed_field_labels).
    """
    candidates = fetch_candidates(conn, filt, limit)
    if candidates:
        return candidates, True, []

    relaxed = filt.model_copy()
    relaxed_labels: list[str] = []

    def _dedupe(labels: list[str]) -> list[str]:
        return list(dict.fromkeys(labels))

    for field in _RELAX_FIELD_ORDER:
        if getattr(relaxed, field) is not None:
            relaxed = relaxed.model_copy(update={field: None})
            relaxed_labels.append(_RELAX_FIELD_LABELS[field])
            candidates = fetch_candidates(conn, relaxed, limit)
            if candidates:
                return candidates, False, _dedupe(relaxed_labels)

    if relaxed.price_max is not None:
        widened = relaxed.model_copy(update={"price_max": relaxed.price_max * _PRICE_WIDEN_FACTOR})
        candidates = fetch_candidates(conn, widened, limit)
        relaxed_labels = relaxed_labels + [_RELAX_FIELD_LABELS["price_max"]]
        if candidates:
            return candidates, False, _dedupe(relaxed_labels)
        relaxed = widened

    if relaxed.mark_id is not None:
        relaxed = relaxed.model_copy(update={"mark_id": None})
        relaxed_labels = relaxed_labels + [_RELAX_FIELD_LABELS["mark_id"]]
        candidates = fetch_candidates(conn, relaxed, limit)
        if candidates:
            return candidates, False, _dedupe(relaxed_labels)

    # Absolute last resort: a 20% widen still isn't enough for a budget
    # that's just unrealistic for anything in stock (e.g. a typo or a
    # placeholder value) - drop the price bound entirely rather than
    # returning nothing, as long as city (never touched) still matches
    # something.
    if relaxed.price_max is not None or relaxed.price_min is not None:
        relaxed = relaxed.model_copy(update={"price_max": None, "price_min": None})
        relaxed_labels = relaxed_labels + [_RELAX_FIELD_LABELS["price_max"]]
        candidates = fetch_candidates(conn, relaxed, limit)
        if candidates:
            return candidates, False, _dedupe(relaxed_labels)

    return [], False, _dedupe(relaxed_labels)


def fetch_distinct_cities(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.city)
        .where(cars.c.is_active.is_(True))
        .distinct()
        .order_by(cars.c.city)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_body_types(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.body_type)
        .where(and_(cars.c.is_active.is_(True), cars.c.body_type.is_not(None)))
        .distinct()
        .order_by(cars.c.body_type)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_colors(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.color)
        .where(and_(cars.c.is_active.is_(True), cars.c.color.is_not(None)))
        .distinct()
        .order_by(cars.c.color)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_marks(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.mark_id)
        .where(cars.c.is_active.is_(True))
        .distinct()
        .order_by(cars.c.mark_id)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_drive_types(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.drive_type)
        .where(and_(cars.c.is_active.is_(True), cars.c.drive_type.is_not(None)))
        .distinct()
        .order_by(cars.c.drive_type)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_fuel_types(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.fuel_type)
        .where(and_(cars.c.is_active.is_(True), cars.c.fuel_type.is_not(None)))
        .distinct()
        .order_by(cars.c.fuel_type)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_distinct_transmissions(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.transmission_type)
        .where(and_(cars.c.is_active.is_(True), cars.c.transmission_type.is_not(None)))
        .distinct()
        .order_by(cars.c.transmission_type)
    )
    return [row[0] for row in conn.execute(stmt).all()]


def fetch_stats(conn: Connection, city: str | None = None) -> dict:
    """Real counts for the homepage subtitle ("живой каталог: N моделей в
    наличии") - never a hardcoded number."""
    conditions = [cars.c.is_active.is_(True)]
    if city:
        conditions.append(cars.c.city == city)

    total_cars = conn.execute(
        select(func.count()).select_from(cars).where(and_(*conditions))
    ).scalar_one()

    total_models = conn.execute(
        select(func.count(func.distinct(func.concat(cars.c.mark_id, "|", cars.c.folder_id))))
        .where(and_(*conditions))
    ).scalar_one()

    return {"total_cars": total_cars, "total_models": total_models}
