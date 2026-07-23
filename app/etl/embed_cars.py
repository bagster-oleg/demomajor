import hashlib

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.db.models import cars
from app.vector.embed import build_embedding_text, embed_texts

# Process rows in chunks rather than materializing every text/vector for the
# whole city at once - the production box is memory-constrained, and this
# keeps peak footprint flat regardless of how large the feed grows.
_CHUNK_SIZE = 200


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def embed_city_cars(conn: Connection, city: str) -> int:
    """Compute embeddings only for active cars in `city` whose embedding
    text actually changed since the last run (or that have none yet).

    upsert_cars rewrites every column unconditionally on every ETL run, so
    comparing description/extras to their previous value doesn't tell you
    anything - they're always "just written". Comparing a stored hash of
    the exact embedding text does: on a static feed (no real content
    changes between runs), this skips the ONNX model load and the expensive
    embedding pass entirely, which is exactly the load a memory-constrained
    box shouldn't be paying every 30 minutes for the same 1939 cars.
    """
    rows = conn.execute(
        select(
            cars.c.id, cars.c.description, cars.c.extras, cars.c.embedding_text_hash
        ).where(cars.c.city == city, cars.c.is_active.is_(True))
    ).all()
    if not rows:
        return 0

    to_embed = []
    for row in rows:
        text = build_embedding_text(row.description, row.extras)
        new_hash = _text_hash(text)
        if new_hash != row.embedding_text_hash:
            to_embed.append((row.id, text, new_hash))

    for i in range(0, len(to_embed), _CHUNK_SIZE):
        chunk = to_embed[i : i + _CHUNK_SIZE]
        vectors = embed_texts([text for _id, text, _hash in chunk])
        for (row_id, _text, new_hash), vector in zip(chunk, vectors):
            conn.execute(
                update(cars)
                .where(cars.c.id == row_id)
                .values(embedding=vector, embedding_text_hash=new_hash)
            )

    return len(to_embed)
