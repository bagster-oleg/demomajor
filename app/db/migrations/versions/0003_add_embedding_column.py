"""add embedding column for phase-5 vector rerank

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.add_column("cars", sa.Column("embedding", Vector(EMBEDDING_DIM)))


def downgrade() -> None:
    op.drop_column("cars", "embedding")
