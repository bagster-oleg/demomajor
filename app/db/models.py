from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

EMBEDDING_DIM = 384  # sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

metadata = MetaData()

cars = Table(
    "cars",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("city", Text, nullable=False),
    Column("unique_id", Text, nullable=False),
    Column("vin", Text),
    Column("mark_id", Text, nullable=False),
    Column("folder_id", Text, nullable=False),
    Column("modification_id", Text),
    Column("complectation_name", Text),
    Column("body_type", Text),
    Column("wheel", Text),
    Column("color", Text),
    Column("metallic", Text),
    Column("availability", Text),
    Column("custom", Text),
    Column("state", Text),
    # Raw Russian phrase from the feed ("Два владельца") plus a parsed count.
    Column("owners_number", Text),
    Column("owners_count", SmallInteger),
    Column("not_registered_in_russia", Boolean),
    Column("run", BigInteger),
    Column("year", SmallInteger),
    Column("registry_year", SmallInteger),
    Column("price", Numeric(12, 2)),
    Column("currency", Text, server_default="RUR"),
    Column("max_discount", Numeric(12, 2)),
    Column("tradein_discount", Numeric(12, 2)),
    Column("credit_discount", Numeric(12, 2)),
    Column("insurance_discount", Numeric(12, 2)),
    Column("doors_count", SmallInteger),
    # Not a real feed field - best-effort guess derived from modification_id
    # (looks for a "4WD"/"AWD" marker). See app/etl/feed_parser.py::_drive_type.
    Column("drive_type", Text),
    Column("transmission_type", Text),
    Column("description", Text),
    Column("extras", Text),
    Column("images", ARRAY(Text)),
    Column("video", Text),
    Column("poi_id", Text),  # full showroom address string, not an opaque id
    Column("pts", Text),
    Column("sts", Text),
    Column("action", Text),
    Column("exchange", Text),
    Column("contact_name", Text),
    Column("contact_phone", Text),
    Column("contact_hours", Text),
    Column("online_view_available", Boolean),
    Column("with_nds", Boolean),
    Column("url", Text),
    # Phase-5 rerank only: reorders the already SQL-filtered candidate list
    # by similarity to the fuzzy leftover part of a query ("для дачи с
    # прицепом") - never used as the primary filter. Built from
    # description+extras, see app/vector/embed.py.
    Column("embedding", Vector(EMBEDDING_DIM)),
    Column("raw", JSONB, nullable=False),
    Column("feed_source", Text, nullable=False),
    Column("first_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("city", "unique_id", name="uq_cars_city_unique_id"),
)

Index("idx_cars_city_active_price", cars.c.city, cars.c.is_active, cars.c.price)
Index("idx_cars_year", cars.c.year)
Index("idx_cars_body_type", cars.c.body_type)
Index("idx_cars_mark_folder", cars.c.mark_id, cars.c.folder_id)
Index("idx_cars_run", cars.c.run)
Index("idx_cars_is_active", cars.c.is_active)
