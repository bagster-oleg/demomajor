from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from app.db.models import cars
from app.etl.embed_cars import embed_city_cars
from app.etl.feed_parser import parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"


def _seed(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")


def _fake_embed_texts(texts):
    # Deterministic per-text stand-in vector, matching the real 384-dim
    # column - only the call count/args matter for these tests, not the
    # actual values.
    return [[float(len(t))] * 384 for t in texts]


def test_first_run_embeds_every_active_car(conn):
    _seed(conn)
    with patch("app.etl.embed_cars.embed_texts", side_effect=_fake_embed_texts) as mock_embed:
        embedded = embed_city_cars(conn, "Москва")
    assert embedded == 9
    mock_embed.assert_called_once()
    assert len(mock_embed.call_args[0][0]) == 9


def test_second_run_with_no_changes_embeds_nothing(conn):
    # Regression: on a static feed, re-running the ETL every 30 minutes used
    # to recompute embeddings for every car unconditionally - real,
    # unnecessary load on a memory-constrained box. Once every car's
    # embedding_text_hash matches its current text, a second run must skip
    # the (expensive) embedding model call entirely.
    _seed(conn)
    with patch("app.etl.embed_cars.embed_texts", side_effect=_fake_embed_texts):
        embed_city_cars(conn, "Москва")

    with patch("app.etl.embed_cars.embed_texts", side_effect=_fake_embed_texts) as mock_embed:
        embedded = embed_city_cars(conn, "Москва")

    assert embedded == 0
    mock_embed.assert_not_called()


def test_changed_description_triggers_reembedding_of_only_that_car(conn):
    _seed(conn)
    with patch("app.etl.embed_cars.embed_texts", side_effect=_fake_embed_texts):
        embed_city_cars(conn, "Москва")

    audi_id = conn.execute(
        select(cars.c.id).where(cars.c.unique_id == "1937189")
    ).scalar_one()
    conn.execute(
        update(cars).where(cars.c.id == audi_id).values(description="Совершенно новое описание")
    )

    with patch("app.etl.embed_cars.embed_texts", side_effect=_fake_embed_texts) as mock_embed:
        embedded = embed_city_cars(conn, "Москва")

    assert embedded == 1
    assert len(mock_embed.call_args[0][0]) == 1
