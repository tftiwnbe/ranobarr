"""add library preferences

Revision ID: 0008_add_library_preferences
Revises: 0007_add_book_metadata_fields
Create Date: 2026-05-29 13:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_library_preferences"
down_revision = "0007_add_book_metadata_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("book", sa.Column("opds_visible_genres_json", sa.String(), nullable=True))
    op.add_column("book", sa.Column("opds_visible_tags_json", sa.String(), nullable=True))
    op.add_column("book", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("book", sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("book", sa.Column("rating", sa.Integer(), nullable=True))
    op.add_column("book", sa.Column("comment", sa.String(), nullable=True))

    op.create_table(
        "usercollection",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usercollection_slug"), "usercollection", ["slug"], unique=True)

    op.create_table(
        "collectionbook",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collection_id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.ForeignKeyConstraint(["collection_id"], ["usercollection.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_collectionbook_collection_id"), "collectionbook", ["collection_id"], unique=False)
    op.create_index(op.f("ix_collectionbook_book_id"), "collectionbook", ["book_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_collectionbook_book_id"), table_name="collectionbook")
    op.drop_index(op.f("ix_collectionbook_collection_id"), table_name="collectionbook")
    op.drop_table("collectionbook")
    op.drop_index(op.f("ix_usercollection_slug"), table_name="usercollection")
    op.drop_table("usercollection")

    op.drop_column("book", "comment")
    op.drop_column("book", "rating")
    op.drop_column("book", "is_current")
    op.drop_column("book", "is_favorite")
    op.drop_column("book", "opds_visible_tags_json")
    op.drop_column("book", "opds_visible_genres_json")
