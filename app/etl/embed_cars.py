from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.db.models import cars
from app.vector.embed import build_embedding_text, embed_texts

# Process rows in chunks rather than materializing every text/vector for the
# whole city at once - the production box is memory-constrained, and this
# keeps peak footprint flat regardless of how large the feed grows.
_CHUNK_SIZE = 200


def embed_city_cars(conn: Connection, city: str) -> int:
    """(Re)compute embeddings for every active car in `city`. Cheap enough
    at this feed's scale to just redo the whole city each ETL run rather
    than tracking which rows changed."""
    rows = conn.execute(
        select(cars.c.id, cars.c.description, cars.c.extras).where(
            cars.c.city == city, cars.c.is_active.is_(True)
        )
    ).all()
    if not rows:
        return 0

    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        texts = [build_embedding_text(row.description, row.extras) for row in chunk]
        vectors = embed_texts(texts)
        for row, vector in zip(chunk, vectors):
            conn.execute(update(cars).where(cars.c.id == row.id).values(embedding=vector))

    return len(rows)
