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


def build_candidate_query(filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT):
    conditions = [cars.c.is_active.is_(True)]

    if filt.city:
        conditions.append(cars.c.city == filt.city)
    if filt.mark_id:
        conditions.append(func.lower(cars.c.mark_id) == filt.mark_id.lower())
    if filt.body_type:
        conditions.append(cars.c.body_type.ilike(f"%{filt.body_type}%"))
    if filt.drive_type:
        conditions.append(cars.c.drive_type == filt.drive_type)
    if filt.transmission_type:
        conditions.append(cars.c.transmission_type == filt.transmission_type)
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

    # Heuristic ordering: within budget, a higher price usually means a
    # better-equipped trim, so surface those first; break ties by discount
    # size and recency of model year.
    order = []
    if filt.price_max is not None:
        order.append(cars.c.price.desc())
    order.append(cars.c.max_discount.desc().nullslast())
    order.append(cars.c.year.desc())

    return select(cars).where(and_(*conditions)).order_by(*order).limit(limit)


def fetch_candidates(conn: Connection, filt: CarFilter, limit: int = DEFAULT_CANDIDATE_LIMIT) -> list[dict]:
    stmt = build_candidate_query(filt, limit=limit)
    rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


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


def fetch_distinct_transmissions(conn: Connection) -> list[str]:
    stmt = (
        select(cars.c.transmission_type)
        .where(and_(cars.c.is_active.is_(True), cars.c.transmission_type.is_not(None)))
        .distinct()
        .order_by(cars.c.transmission_type)
    )
    return [row[0] for row in conn.execute(stmt).all()]
