"""initial cars table

Revision ID: 0001
Revises:
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "cars",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("unique_id", sa.Text(), nullable=False),
        sa.Column("vin", sa.Text()),
        sa.Column("mark_id", sa.Text(), nullable=False),
        sa.Column("folder_id", sa.Text(), nullable=False),
        sa.Column("modification_id", sa.Text()),
        sa.Column("complectation_name", sa.Text()),
        sa.Column("body_type", sa.Text()),
        sa.Column("wheel", sa.Text()),
        sa.Column("color", sa.Text()),
        sa.Column("metallic", sa.Text()),
        sa.Column("availability", sa.Text()),
        sa.Column("custom", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("owners_number", sa.Text()),
        sa.Column("owners_count", sa.SmallInteger()),
        sa.Column("not_registered_in_russia", sa.Boolean()),
        sa.Column("run", sa.BigInteger()),
        sa.Column("year", sa.SmallInteger()),
        sa.Column("registry_year", sa.SmallInteger()),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("currency", sa.Text(), server_default="RUR"),
        sa.Column("max_discount", sa.Numeric(12, 2)),
        sa.Column("tradein_discount", sa.Numeric(12, 2)),
        sa.Column("credit_discount", sa.Numeric(12, 2)),
        sa.Column("insurance_discount", sa.Numeric(12, 2)),
        sa.Column("doors_count", sa.SmallInteger()),
        sa.Column("drive_type", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("extras", sa.Text()),
        sa.Column("images", postgresql.ARRAY(sa.Text())),
        sa.Column("video", sa.Text()),
        sa.Column("poi_id", sa.Text()),
        sa.Column("pts", sa.Text()),
        sa.Column("sts", sa.Text()),
        sa.Column("action", sa.Text()),
        sa.Column("exchange", sa.Text()),
        sa.Column("contact_name", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("contact_hours", sa.Text()),
        sa.Column("online_view_available", sa.Boolean()),
        sa.Column("with_nds", sa.Boolean()),
        sa.Column("url", sa.Text()),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("feed_source", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("city", "unique_id", name="uq_cars_city_unique_id"),
    )

    op.create_index("idx_cars_city_active_price", "cars", ["city", "is_active", "price"])
    op.create_index("idx_cars_year", "cars", ["year"])
    op.create_index("idx_cars_body_type", "cars", ["body_type"])
    op.create_index("idx_cars_mark_folder", "cars", ["mark_id", "folder_id"])
    op.create_index("idx_cars_run", "cars", ["run"])
    op.create_index("idx_cars_is_active", "cars", ["is_active"])


def downgrade() -> None:
    op.drop_table("cars")
