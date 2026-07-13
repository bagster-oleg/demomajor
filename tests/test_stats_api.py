from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.main import app
from app.etl.feed_parser import parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"

client = TestClient(app)


@pytest.fixture(autouse=True)
def use_test_engine(engine, monkeypatch):
    monkeypatch.setattr("app.api.main.engine", engine)


@pytest.fixture()
def seeded_cars(engine):
    records = parse_feed_file(FIXTURE, city="Москва")
    with engine.begin() as conn:
        sync_city_feed(conn, records, city="Москва")
    yield records
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE cars"))


def test_stats_counts_real_cars_and_distinct_models(seeded_cars):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cars"] == 9
    # two Nissan Qashqai entries share mark_id+folder_id -> 8 distinct models
    assert data["total_models"] == 8


def test_stats_filtered_by_city_with_no_match_returns_zero(seeded_cars):
    resp = client.get("/api/stats", params={"city": "Казань"})
    assert resp.status_code == 200
    assert resp.json() == {"total_cars": 0, "total_models": 0}


def test_stats_with_no_data_returns_zero():
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    assert resp.json() == {"total_cars": 0, "total_models": 0}
