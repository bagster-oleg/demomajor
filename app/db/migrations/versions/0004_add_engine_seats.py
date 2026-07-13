"""add engine_volume_l, power_hp, seats derived columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("engine_volume_l", sa.Numeric(3, 1)))
    op.add_column("cars", sa.Column("power_hp", sa.SmallInteger()))
    op.add_column("cars", sa.Column("seats", sa.SmallInteger()))
    op.create_index("idx_cars_engine_volume", "cars", ["engine_volume_l"])
    op.create_index("idx_cars_seats", "cars", ["seats"])


def downgrade() -> None:
    op.drop_index("idx_cars_seats", table_name="cars")
    op.drop_index("idx_cars_engine_volume", table_name="cars")
    op.drop_column("cars", "seats")
    op.drop_column("cars", "power_hp")
    op.drop_column("cars", "engine_volume_l")
