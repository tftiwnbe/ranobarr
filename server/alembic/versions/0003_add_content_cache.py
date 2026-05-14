"""add chapter content cache"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_content_cache"
down_revision = "0002_add_chapter_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chaptercontentcache",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("chapter_key", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chaptercontentcache_book_id"), "chaptercontentcache", ["book_id"], unique=False)
    op.create_index(op.f("ix_chaptercontentcache_branch_id"), "chaptercontentcache", ["branch_id"], unique=False)
    op.create_index(op.f("ix_chaptercontentcache_chapter_key"), "chaptercontentcache", ["chapter_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chaptercontentcache_chapter_key"), table_name="chaptercontentcache")
    op.drop_index(op.f("ix_chaptercontentcache_branch_id"), table_name="chaptercontentcache")
    op.drop_index(op.f("ix_chaptercontentcache_book_id"), table_name="chaptercontentcache")
    op.drop_table("chaptercontentcache")
