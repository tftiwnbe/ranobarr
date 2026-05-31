"""add opds visibility and download state

Revision ID: 0009_add_opds_visibility_and_download_state
Revises: 0008_add_library_preferences
Create Date: 2026-05-29 19:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_opds_visibility_and_download_state"
down_revision = "0008_add_library_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookstate", sa.Column("last_downloaded_at", sa.DateTime(), nullable=True))
    op.create_table(
        "appsetting",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_appsetting_key"), "appsetting", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_appsetting_key"), table_name="appsetting")
    op.drop_table("appsetting")
    op.drop_column("bookstate", "last_downloaded_at")
