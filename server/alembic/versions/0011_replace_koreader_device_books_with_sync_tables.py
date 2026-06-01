"""replace koreader device books with sync tables

Revision ID: 0011_replace_koreader_device_books_with_sync_tables
Revises: 0010_add_koreader_device_books
Create Date: 2026-06-01 15:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_replace_koreader_device_books_with_sync_tables"
down_revision = "0010_add_koreader_device_books"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "koreadersyncuser",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("auth_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_koreadersyncuser_username"), "koreadersyncuser", ["username"], unique=True)

    op.create_table(
        "koreadersyncdocument",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("document_hash", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("linked_book_id", sa.String(), nullable=True),
        sa.Column("progress", sa.String(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("progress_timestamp", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["linked_book_id"], ["book.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["koreadersyncuser.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_koreadersyncdocument_document_hash"), "koreadersyncdocument", ["document_hash"], unique=False)
    op.create_index(op.f("ix_koreadersyncdocument_linked_book_id"), "koreadersyncdocument", ["linked_book_id"], unique=False)
    op.create_index(op.f("ix_koreadersyncdocument_user_id"), "koreadersyncdocument", ["user_id"], unique=False)

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "koreaderdevicebook" in inspector.get_table_names():
        legacy_rows = list(
            bind.execute(
                sa.text(
                    """
                    SELECT id, title, author, linked_book_id, progress_percent, created_at, updated_at
                    FROM koreaderdevicebook
                    """
                )
            ).mappings()
        )
        if legacy_rows:
            legacy_user_id = "koreader-legacy-user"
            bind.execute(
                sa.text(
                    """
                    INSERT INTO koreadersyncuser (id, username, auth_key, created_at, updated_at)
                    VALUES (:id, :username, :auth_key, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {"id": legacy_user_id, "username": "legacy-import", "auth_key": "legacy-import-disabled"},
            )

        for row in legacy_rows:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO koreadersyncdocument (
                        id, user_id, document_hash, title, author, linked_book_id,
                        progress, progress_percent, device, device_id, progress_timestamp,
                        created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :document_hash, :title, :author, :linked_book_id,
                        NULL, :progress_percent, 'legacy-import', NULL, NULL,
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": row["id"],
                    "user_id": legacy_user_id,
                    "document_hash": row["id"],
                    "title": row["title"],
                    "author": row["author"],
                    "linked_book_id": row["linked_book_id"],
                    "progress_percent": row["progress_percent"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                },
            )

        op.drop_index(op.f("ix_koreaderdevicebook_linked_book_id"), table_name="koreaderdevicebook")
        op.drop_index(op.f("ix_koreaderdevicebook_document_path"), table_name="koreaderdevicebook")
        op.drop_table("koreaderdevicebook")


def downgrade() -> None:
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

    op.drop_index(op.f("ix_koreadersyncdocument_user_id"), table_name="koreadersyncdocument")
    op.drop_index(op.f("ix_koreadersyncdocument_linked_book_id"), table_name="koreadersyncdocument")
    op.drop_index(op.f("ix_koreadersyncdocument_document_hash"), table_name="koreadersyncdocument")
    op.drop_table("koreadersyncdocument")
    op.drop_index(op.f("ix_koreadersyncuser_username"), table_name="koreadersyncuser")
    op.drop_table("koreadersyncuser")
