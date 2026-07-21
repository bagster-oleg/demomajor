"""Deterministic SQL filtering over the cars table.

This is the layer that turns a CarFilter into a plain indexed SQL query -
no embeddings, no similarity search. Price/year/mileage/availability are
facts, not vibes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection

from app.api.schemas import CarFilter
from app.db.models import cars

DEFAULT_CANDIDATE_LIMIT = 30
# Used instead of DEFAULT_CANDIDATE_LIMIT when free_text_intent is set: the
# SQL ORDER BY here is a crude price/discount/year heuristic, not a
# relevance score - if it truncated to 30 before the embedding-based rerank
# ever ran, a genuinely better semantic match sitting at position 31+ could
# never be surfaced. Fetch a much bigger pool first, let the rerank sort by
# actual similarity, then the caller truncates to what's shown/explained.
FUZZY_RERANK_POOL_LIMIT = 300

# Thresholds behind the semantic preferences, kept in code (not guessed by
# the LLM) so "экономичный"/"семейный"/"новая"/"почти не ездили" mean the
# same thing every time.
ECONOMICAL_MAX_ENGINE_L = 1.6  # "экономичный" -> small engine, a real number
FAMILY_MIN_SEATS = 5  # "семейный" -> room for a family
RECENT_MAX_AGE_YEARS = 2  # "новая"/"свежая машина" -> within the last N model years
LOW_MILEAGE_MAX_RUN = 30_000  # "почти не ездили"/"маленький пробег" -> real km number

# Curated feature vocabulary for "с подогревом сидений"/"панорамная крыша"
# style requests. extras is one long free-text option list per car (not a
# clean enum), so instead of an LLM enum over the full real vocabulary
# (hundreds of distinct option strings), we hand-pick the common, well-
# understood asks and map each to a substring pattern verified against real
# feed data - still a real, deterministic match against the actual extras
# text, just via a fixed label set rather than a DB-derived one.
FEATURE_KEYWORDS = {
    "панорамная крыша": "панорам",
    "люк": "люк",
    "подогрев сидений": "подогрев%сидени",
    "вентиляция сидений": "вентиляция%сидени",
    "кожаный салон": "кожа (материал салона)",
    "камера": "камера",
    "круиз-контроль": "круиз-контроль",
    "навигация": "навигационная система",
    "подогрев руля": "обогрев рулевого колеса",
    "беспроводная зарядка": "беспроводная зарядка",
}
FEATURE_LABELS = list(FEATURE_KEYWORDS)


def build_candidate_query(filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT):
    conditions = [cars.c.is_active.is_(True)]

    if filt.city:
        conditions.append(cars.c.city == filt.city)
    if filt.mark_ids:
        # OR across brands ("Kia или Hyundai") - any one of them matches.
        conditions.append(func.lower(cars.c.mark_id).in_([m.lower() for m in filt.mark_ids]))
    if filt.exclude_mark_ids:
        conditions.append(
            func.lower(cars.c.mark_id).not_in([m.lower() for m in filt.exclude_mark_ids])
        )
    if filt.body_type:
        conditions.append(cars.c.body_type.ilike(f"%{filt.body_type}%"))
    if filt.exclude_body_types:
        for excluded in filt.exclude_body_types:
            conditions.append(~cars.c.body_type.ilike(f"%{excluded}%"))
    if filt.color:
        conditions.append(func.lower(cars.c.color) == filt.color.lower())
    if filt.exclude_colors:
        conditions.append(
            func.lower(cars.c.color).not_in([c.lower() for c in filt.exclude_colors])
        )
    if filt.required_features:
        # AND across features - the client asked for all of them together.
        for label in filt.required_features:
            pattern = FEATURE_KEYWORDS.get(label)
            if pattern:
                conditions.append(cars.c.extras.ilike(f"%{pattern}%"))
    if filt.complectation_keyword:
        # Not clamped to a known list like color/body_type - complectation
        # names are per-model trim labels (hundreds of distinct real
        # values), too many to enumerate as an LLM enum. A real ILIKE
        # against the actual column either matches genuine trims or matches
        # nothing (handled honestly by the relaxation ladder), never a
        # false positive on an invented value.
        conditions.append(cars.c.complectation_name.ilike(f"%{filt.complectation_keyword}%"))
    if filt.not_registered_in_russia is not None:
        conditions.append(cars.c.not_registered_in_russia.is_(filt.not_registered_in_russia))
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
    if filt.recent_only:
        current_year = datetime.now(timezone.utc).year
        conditions.append(cars.c.year >= current_year - RECENT_MAX_AGE_YEARS)
    if filt.low_mileage:
        conditions.append(cars.c.run <= LOW_MILEAGE_MAX_RUN)
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
    if filt.prefer_premium and filt.price_min is None:
        # Symmetric opposite of prefer_cheap: "топовая комплектация"/
        # "подороже" with no stated number - cap at the real median price
        # of currently matching stock instead of inventing a floor, same
        # self-adjusting logic as prefer_cheap just on the other side.
        median_price = (
            select(func.percentile_cont(0.5).within_group(cars.c.price.asc()))
            .where(and_(*conditions))
            .scalar_subquery()
        )
        conditions.append(cars.c.price >= median_price)

    # Heuristic ordering: within budget, a higher price usually means a
    # better-equipped trim, so surface those first; break ties by discount
    # size and recency of model year. "недорогая" without a stated budget
    # means the opposite - cheapest genuinely first.
    order = []
    if filt.prefer_cheap:
        order.append(cars.c.price.asc())
    elif filt.prefer_premium or filt.price_max is not None:
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
    "complectation_keyword",
    "required_features",
    "not_registered_in_russia",
    "exclude_mark_ids",
    "doors_count",
    "owners_count_max",
    "color",
    "exclude_colors",
    "fuel_type",
    "power_hp_min",
    "power_hp_max",
    "engine_volume_min",
    "engine_volume_max",
    "economical",
    "low_mileage",
    "drive_type",
    "transmission_type",
    "run_max",
    "seats_min",
    "family_friendly",
    "recent_only",
    "prefer_cheap",
    "prefer_premium",
    "body_type",
    "exclude_body_types",
    "year_min",
    "year_max",
]

_RELAX_FIELD_LABELS = {
    "complectation_keyword": "комплектация",
    "required_features": "дополнительные опции",
    "not_registered_in_russia": "статус регистрации в РФ",
    "exclude_mark_ids": "исключение по марке",
    "doors_count": "количество дверей",
    "owners_count_max": "число владельцев",
    "color": "цвет",
    "exclude_colors": "исключение по цвету",
    "fuel_type": "тип двигателя",
    "power_hp_min": "мощность двигателя",
    "power_hp_max": "мощность двигателя",
    "engine_volume_min": "объём двигателя",
    "engine_volume_max": "объём двигателя",
    "economical": "экономичность",
    "low_mileage": "малый пробег",
    "drive_type": "привод",
    "transmission_type": "коробка передач",
    "run_max": "пробег",
    "seats_min": "количество мест",
    "family_friendly": "вместимость (семейный)",
    "recent_only": "год выпуска (новая машина)",
    "prefer_cheap": "бюджетное ограничение",
    "prefer_premium": "предпочтение по цене (дороже)",
    "body_type": "тип кузова",
    "exclude_body_types": "исключение по кузову",
    "year_min": "год выпуска",
    "year_max": "год выпуска",
    "price_max": "бюджет",
    "mark_ids": "марка",
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

    if relaxed.mark_ids is not None:
        relaxed = relaxed.model_copy(update={"mark_ids": None})
        relaxed_labels = relaxed_labels + [_RELAX_FIELD_LABELS["mark_ids"]]
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
