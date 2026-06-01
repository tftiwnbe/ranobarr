"""add koreader device books

Revision ID: 0010_add_koreader_device_books
Revises: 0009_add_opds_visibility_and_download_state
Create Date: 2026-06-01 14:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_koreader_device_books"
down_revision = "0009_add_opds_visibility_and_download_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "koreaderdevicebook",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_path", sa.String(), nullable=False),
        sa.Column("metadata_path", sa.String(), nullable=False),
        sa.Column("document_name", sa.String(), nullable=False),
        sa.Column("file_format", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("linked_book_id", sa.String(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["linked_book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_koreaderdevicebook_document_path"), "koreaderdevicebook", ["document_path"], unique=True)
    op.create_index(op.f("ix_koreaderdevicebook_linked_book_id"), "koreaderdevicebook", ["linked_book_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_koreaderdevicebook_linked_book_id"), table_name="koreaderdevicebook")
    op.drop_index(op.f("ix_koreaderdevicebook_document_path"), table_name="koreaderdevicebook")
    op.drop_table("koreaderdevicebook")
