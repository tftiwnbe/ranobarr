"""add persisted book metadata fields"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_book_metadata_fields"
down_revision = "0006_add_job_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("book", sa.Column("genres_json", sa.String(), nullable=True))
    op.add_column("book", sa.Column("tags_json", sa.String(), nullable=True))
    op.add_column("book", sa.Column("branches_json", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("book", "branches_json")
    op.drop_column("book", "tags_json")
    op.drop_column("book", "genres_json")
