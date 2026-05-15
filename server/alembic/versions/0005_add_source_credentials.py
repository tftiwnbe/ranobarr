"""add source credentials"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_source_credentials"
down_revision = "0004_add_binary_asset_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sourcecredential",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=True),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider"),
    )
    op.create_index(op.f("ix_sourcecredential_provider"), "sourcecredential", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sourcecredential_provider"), table_name="sourcecredential")
    op.drop_table("sourcecredential")
