"""add fuel_type derived column

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-21

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("fuel_type", sa.Text()))
    op.create_index("idx_cars_fuel_type", "cars", ["fuel_type"])


def downgrade() -> None:
    op.drop_index("idx_cars_fuel_type", table_name="cars")
    op.drop_column("cars", "fuel_type")
