"""Upsert parsed CarRecords into Postgres and soft-delete cars that dropped
out of the latest feed for their city.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from app.db.models import cars
from app.etl.feed_parser import CarRecord

# Columns that get refreshed on every upsert (everything except identity/audit
# columns that should only be set on first insert).
_UPDATE_COLUMNS = [
    "vin",
    "mark_id",
    "folder_id",
    "modification_id",
    "complectation_name",
    "body_type",
    "wheel",
    "color",
    "metallic",
    "availability",
    "custom",
    "state",
    "owners_number",
    "owners_count",
    "not_registered_in_russia",
    "run",
    "year",
    "registry_year",
    "price",
    "currency",
    "max_discount",
    "tradein_discount",
    "credit_discount",
    "insurance_discount",
    "doors_count",
    "drive_type",
    "transmission_type",
    "engine_volume_l",
    "power_hp",
    "seats",
    "description",
    "extras",
    "images",
    "video",
    "poi_id",
    "pts",
    "sts",
    "action",
    "exchange",
    "contact_name",
    "contact_phone",
    "contact_hours",
    "online_view_available",
    "with_nds",
    "url",
    "raw",
    "feed_source",
]


def upsert_cars(conn: Connection, records: list[CarRecord], run_started_at: datetime) -> int:
    """Upsert a batch of CarRecords (all belonging to the same city feed).

    Returns the number of rows affected. Does not commit; caller controls
    the transaction.
    """
    if not records:
        return 0

    rows = [
        {
            **record.model_dump(),
            "last_seen_at": run_started_at,
        }
        for record in records
    ]

    stmt = insert(cars).values(rows)
    update_set = {col: getattr(stmt.excluded, col) for col in _UPDATE_COLUMNS}
    update_set["last_seen_at"] = stmt.excluded.last_seen_at
    update_set["is_active"] = True
    update_set["updated_at"] = func.now()

    stmt = stmt.on_conflict_do_update(
        index_elements=["city", "unique_id"],
        set_=update_set,
    )
    conn.execute(stmt)
    # psycopg does not reliably report rowcount for multi-row INSERT ... ON
    # CONFLICT statements, so report the batch size we attempted to upsert.
    return len(records)


def deactivate_stale_cars(conn: Connection, city: str, run_started_at: datetime) -> int:
    """Mark cars in `city` not seen in the current run as inactive."""
    stmt = (
        update(cars)
        .where(
            and_(
                cars.c.city == city,
                cars.c.is_active.is_(True),
                cars.c.last_seen_at < run_started_at,
            )
        )
        .values(is_active=False, updated_at=func.now())
    )
    result = conn.execute(stmt)
    return result.rowcount


def sync_city_feed(conn: Connection, records: list[CarRecord], city: str) -> dict:
    """Full sync for one city: upsert current records, deactivate the rest."""
    run_started_at = datetime.now(timezone.utc)
    upserted = upsert_cars(conn, records, run_started_at)
    deactivated = deactivate_stale_cars(conn, city, run_started_at)
    return {"city": city, "upserted": upserted, "deactivated": deactivated}
