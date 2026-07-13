"""add transmission_type derived column

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("transmission_type", sa.Text()))


def downgrade() -> None:
    op.drop_column("cars", "transmission_type")
