"""add last chapter added timestamp

Revision ID: 0012_add_last_chapter_added_at
Revises: 0011_replace_koreader_device_books_with_sync_tables
Create Date: 2026-06-02 09:02:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_add_last_chapter_added_at"
down_revision = "0011_replace_koreader_device_books_with_sync_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookstate", sa.Column("last_chapter_added_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookstate", "last_chapter_added_at")
