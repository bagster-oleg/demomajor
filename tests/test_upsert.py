from pathlib import Path

from sqlalchemy import func, select

from app.db.models import cars
from app.etl.feed_parser import parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"


def test_sync_inserts_all_cars(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    summary = sync_city_feed(conn, records, city="Москва")

    assert summary["upserted"] == 9
    count = conn.execute(select(func.count()).select_from(cars)).scalar_one()
    assert count == 9


def test_sync_is_idempotent_no_duplicates(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")
    sync_city_feed(conn, records, city="Москва")

    count = conn.execute(select(func.count()).select_from(cars)).scalar_one()
    assert count == 9


def test_sync_updates_changed_fields(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")

    updated = list(records)
    updated[0] = updated[0].model_copy(update={"price": 4_999_999.0})
    sync_city_feed(conn, updated, city="Москва")

    row = conn.execute(
        select(cars.c.price).where(cars.c.unique_id == updated[0].unique_id)
    ).scalar_one()
    assert float(row) == 4_999_999.0


def test_sync_deactivates_cars_missing_from_new_feed(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")

    dropped_id = records[-1].unique_id
    remaining = [r for r in records if r.unique_id != dropped_id]
    sync_city_feed(conn, remaining, city="Москва")

    active = conn.execute(
        select(cars.c.is_active).where(cars.c.unique_id == dropped_id)
    ).scalar_one()
    assert active is False

    still_active = conn.execute(
        select(cars.c.is_active).where(cars.c.unique_id == records[0].unique_id)
    ).scalar_one()
    assert still_active is True


def test_sync_reactivates_car_that_reappears(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    dropped_id = records[-1].unique_id
    remaining = [r for r in records if r.unique_id != dropped_id]
    sync_city_feed(conn, remaining, city="Москва")

    sync_city_feed(conn, records, city="Москва")

    active = conn.execute(
        select(cars.c.is_active).where(cars.c.unique_id == dropped_id)
    ).scalar_one()
    assert active is True


def test_sync_scopes_deactivation_to_city(conn):
    moscow_records = parse_feed_file(FIXTURE, city="Москва")
    spb_records = [
        r.model_copy(update={"city": "Санкт-Петербург", "unique_id": "spb-0001"})
        for r in moscow_records[:1]
    ]

    sync_city_feed(conn, moscow_records, city="Москва")
    sync_city_feed(conn, spb_records, city="Санкт-Петербург")

    # Re-sync Moscow with a subset; SPB car must remain untouched.
    sync_city_feed(conn, moscow_records[:1], city="Москва")

    spb_active = conn.execute(
        select(cars.c.is_active).where(cars.c.unique_id == "spb-0001")
    ).scalar_one()
    assert spb_active is True


def test_owners_count_and_drive_type_persisted(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")

    row = conn.execute(
        select(cars.c.owners_number, cars.c.owners_count, cars.c.drive_type)
        .where(cars.c.unique_id == "1937189")
    ).one()
    assert row.owners_number == "Два владельца"
    assert row.owners_count == 2
    assert row.drive_type == "4WD"
