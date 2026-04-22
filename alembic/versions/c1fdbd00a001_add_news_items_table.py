"""add news_items table

Revision ID: c1fdbd00a001
Revises: e6f885d3ac30
Create Date: 2026-04-06 00:06:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1fdbd00a001"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_code", sa.String(length=40), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_tier", sa.String(length=8), nullable=False),
        sa.Column("region", sa.String(length=16), nullable=False),
        sa.Column("official", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="ko"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("sentiment_label", sa.String(length=16), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("symbols_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("dedupe_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_hash"),
    )
    op.create_index(op.f("ix_news_items_source_code"), "news_items", ["source_code"], unique=False)
    op.create_index(op.f("ix_news_items_source_tier"), "news_items", ["source_tier"], unique=False)
    op.create_index(op.f("ix_news_items_region"), "news_items", ["region"], unique=False)
    op.create_index(op.f("ix_news_items_external_id"), "news_items", ["external_id"], unique=False)
    op.create_index(op.f("ix_news_items_published_at"), "news_items", ["published_at"], unique=False)
    op.create_index(op.f("ix_news_items_dedupe_hash"), "news_items", ["dedupe_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_news_items_dedupe_hash"), table_name="news_items")
    op.drop_index(op.f("ix_news_items_published_at"), table_name="news_items")
    op.drop_index(op.f("ix_news_items_external_id"), table_name="news_items")
    op.drop_index(op.f("ix_news_items_region"), table_name="news_items")
    op.drop_index(op.f("ix_news_items_source_tier"), table_name="news_items")
    op.drop_index(op.f("ix_news_items_source_code"), table_name="news_items")
    op.drop_table("news_items")
