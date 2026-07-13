"""Entrypoint for the periodic feed-ingestion job (invoked by cron).

Iterates configured city -> feed path/URL mappings, parses each XML feed,
and upserts into Postgres. Run with:

    python -m app.etl.run_etl
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.request import urlopen

from app.config import settings
from app.db.session import engine
from app.etl.embed_cars import embed_city_cars
from app.etl.feed_parser import parse_feed_bytes
from app.etl.upsert import sync_city_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_etl")


def _load_feed_bytes(source: str) -> bytes:
    if source.startswith("http://") or source.startswith("https://"):
        with urlopen(source) as resp:  # noqa: S310 - feed source is operator-configured
            return resp.read()
    return Path(source).read_bytes()


def run() -> int:
    total_upserted = 0
    total_deactivated = 0
    had_errors = False

    for city, source in settings.feed_sources.items():
        feed_source_name = Path(source).name
        try:
            xml_bytes = _load_feed_bytes(source)
            records = parse_feed_bytes(xml_bytes, city=city, feed_source=feed_source_name)
        except Exception:
            logger.exception("failed to parse feed for city=%s source=%s", city, source)
            had_errors = True
            continue

        with engine.begin() as conn:
            summary = sync_city_feed(conn, records, city)
            embedded = embed_city_cars(conn, city)

        logger.info(
            "city=%s upserted=%s deactivated=%s parsed=%s embedded=%s",
            summary["city"], summary["upserted"], summary["deactivated"], len(records), embedded,
        )
        total_upserted += summary["upserted"]
        total_deactivated += summary["deactivated"]

    logger.info("done: total_upserted=%s total_deactivated=%s", total_upserted, total_deactivated)
    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(run())
