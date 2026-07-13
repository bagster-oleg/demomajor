import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.config import settings
from app.db.models import metadata


def _test_database_url() -> str:
    """Tests must never point at the same database as the demo/dev
    instance - a previous version of this suite truncated the shared
    `cars` table via a test fixture and silently wiped out demo data. Derive
    a sibling `<db>_test` database from DATABASE_URL instead."""
    base_url = settings.database_url
    db_name = base_url.rsplit("/", 1)[-1]
    return base_url.rsplit("/", 1)[0] + f"/{db_name}_test"


def _ensure_test_database_exists(test_url: str) -> None:
    admin_url = test_url.rsplit("/", 1)[0] + "/postgres"
    db_name = test_url.rsplit("/", 1)[-1]
    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except ProgrammingError:
        pass  # already exists
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def engine():
    test_url = _test_database_url()
    _ensure_test_database_exists(test_url)

    eng = create_engine(test_url, future=True)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    metadata.drop_all(eng)
    metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def conn(engine):
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()
