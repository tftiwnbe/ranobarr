"""add chapter snapshots"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_chapter_snapshots"
down_revision = "0001_initial_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chaptersnapshot",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("chapter_key", sa.String(), nullable=False),
        sa.Column("volume", sa.String(), nullable=False),
        sa.Column("number", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("branch_id", sa.String(), nullable=True),
        sa.Column("branch_name", sa.String(), nullable=True),
        sa.Column("ordinal_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chaptersnapshot_book_id"), "chaptersnapshot", ["book_id"], unique=False)
    op.create_index(op.f("ix_chaptersnapshot_branch_id"), "chaptersnapshot", ["branch_id"], unique=False)
    op.create_index(op.f("ix_chaptersnapshot_chapter_key"), "chaptersnapshot", ["chapter_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chaptersnapshot_chapter_key"), table_name="chaptersnapshot")
    op.drop_index(op.f("ix_chaptersnapshot_branch_id"), table_name="chaptersnapshot")
    op.drop_index(op.f("ix_chaptersnapshot_book_id"), table_name="chaptersnapshot")
    op.drop_table("chaptersnapshot")
