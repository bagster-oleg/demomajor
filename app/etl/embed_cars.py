from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.db.models import cars
from app.vector.embed import build_embedding_text, embed_texts


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

    texts = [build_embedding_text(row.description, row.extras) for row in rows]
    vectors = embed_texts(texts)

    for row, vector in zip(rows, vectors):
        conn.execute(update(cars).where(cars.c.id == row.id).values(embedding=vector))

    return len(rows)
