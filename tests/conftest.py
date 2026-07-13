import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.db.models import metadata


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, future=True)
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
