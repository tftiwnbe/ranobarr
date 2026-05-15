"""add binary asset cache"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_binary_asset_cache"
down_revision = "0003_add_content_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "binaryassetcache",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url"),
    )
    op.create_index(op.f("ix_binaryassetcache_source_url"), "binaryassetcache", ["source_url"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_binaryassetcache_source_url"), table_name="binaryassetcache")
    op.drop_table("binaryassetcache")
