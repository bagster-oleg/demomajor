from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.main import app
from app.api.schemas import CarFilter
from app.etl.feed_parser import parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"

client = TestClient(app)


@pytest.fixture(autouse=True)
def use_test_engine(engine, monkeypatch):
    """The FastAPI app talks to app.db.session.engine (the dev/demo DB) by
    default; point it at the isolated test DB from conftest instead, so
    these tests can never touch (or truncate) real demo data."""
    monkeypatch.setattr("app.api.main.engine", engine)


@pytest.fixture()
def seeded_cars(engine):
    """Seed the real feed into the DB, committed (not the rollback-based
    `conn` fixture) - the API under test opens its own connection, which
    would never see uncommitted rows from another transaction."""
    records = parse_feed_file(FIXTURE, city="Москва")
    with engine.begin() as conn:
        sync_city_feed(conn, records, city="Москва")
    yield records
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE cars"))


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cities_lists_seeded_city(seeded_cars):
    resp = client.get("/api/cities")
    assert resp.status_code == 200
    assert resp.json() == ["Москва"]


def test_search_returns_llm_selected_results_in_order(seeded_cars):
    with patch("app.api.search.parse_query") as mock_parse, patch(
        "app.api.search.rank_and_explain"
    ) as mock_rank:
        mock_parse.return_value = (CarFilter(city="Москва", body_type="Внедорожник 5 дв."), [])
        mock_rank.return_value = [
            {"unique_id": "1865441", "explanation": "Кроссовер, один владелец, недорогой."},
            {"unique_id": "1862622", "explanation": "Кроссовер с полным приводом."},
        ]

        resp = client.post("/api/search", json={"query": "внедорожник в Москве"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["city_used"] == "Москва"
    assert [r["unique_id"] for r in data["results"]] == ["1865441", "1862622"]
    assert data["results"][0]["explanation"] == "Кроссовер, один владелец, недорогой."
    # price_after_max_discount is derived, not just echoed from the DB
    geely = data["results"][0]
    assert geely["price_after_max_discount"] == geely["price"] - geely["discounts"]["max_discount"]


def test_explicit_city_param_overrides_llm_parsed_city(seeded_cars):
    with patch("app.api.search.parse_query") as mock_parse, patch(
        "app.api.search.rank_and_explain"
    ) as mock_rank:
        mock_parse.return_value = (CarFilter(city="Санкт-Петербург"), [])
        mock_rank.return_value = [{"unique_id": "1937189", "explanation": "ok"}]

        resp = client.post(
            "/api/search", json={"query": "любая машина", "city": "Москва"}
        )

    assert resp.status_code == 200
    assert resp.json()["city_used"] == "Москва"
    assert resp.json()["parsed_filter"]["city"] == "Москва"


def test_search_with_no_sql_candidates_skips_llm_ranking(seeded_cars):
    # price_max alone can't force zero results any more - the relaxation
    # ladder (tests/test_filter_sql.py) will eventually drop the budget
    # entirely and find something. City is the one dimension that's never
    # relaxed, so an impossible city is the only reliable way to get a
    # true "nothing in stock at all" response.
    with patch("app.api.search.parse_query") as mock_parse, patch(
        "app.api.search.rank_and_explain"
    ) as mock_rank:
        mock_parse.return_value = (CarFilter(city="Владивосток"), [])

        resp = client.post("/api/search", json={"query": "любая машина во Владивостоке"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["total_candidates_after_sql_filter"] == 0
    assert data["exact_match"] is False
    mock_rank.assert_not_called()


def test_search_with_relaxed_filter_reports_exact_match_false(seeded_cars):
    with patch("app.api.search.parse_query") as mock_parse, patch(
        "app.api.search.rank_and_explain"
    ) as mock_rank:
        mock_parse.return_value = (CarFilter(city="Москва", mark_ids=["Kia"], doors_count=3), [])
        mock_rank.return_value = [{"unique_id": "1864081", "explanation": "ok"}]

        resp = client.post("/api/search", json={"query": "kia с 3 дверями"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["exact_match"] is False
    assert "количество дверей" in data["relaxed_fields"]
    # rank_and_explain must be told what was relaxed so it can be honest
    # about the mismatch instead of pretending it's a perfect match.
    mock_rank.assert_called_once()
    assert mock_rank.call_args[0][2] == ["количество дверей"]


def test_search_reports_not_exact_when_brand_silently_dropped(seeded_cars):
    # Regression: "мерседес джип" - no Mercedes in stock. parse_query
    # clamps mark_id to None and reports it as dropped; body_type alone
    # then matches SUVs in stock via SQL on the first try (sql_exact_match
    # would be True in isolation). The response must still say
    # exact_match=False - the brand was never actually honored.
    with patch("app.api.search.parse_query") as mock_parse, patch(
        "app.api.search.rank_and_explain"
    ) as mock_rank:
        mock_parse.return_value = (
            CarFilter(body_type="Внедорожник 5 дв."),
            ["марка"],
        )
        mock_rank.return_value = [{"unique_id": "1862622", "explanation": "ok"}]

        resp = client.post("/api/search", json={"query": "мерседес джип"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["exact_match"] is False
    assert "марка" in data["relaxed_fields"]
    assert len(data["results"]) > 0
