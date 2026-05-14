"""initial backend schema"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_backend"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "book",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("available_chapters", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_book_slug"), "book", ["slug"], unique=False)

    op.create_table(
        "bookstate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("last_remote_chapter_key", sa.String(), nullable=True),
        sa.Column("last_built_chapter_key", sa.String(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id"),
    )
    op.create_index(op.f("ix_bookstate_book_id"), "bookstate", ["book_id"], unique=False)

    op.create_table(
        "trackrule",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("branch_mode", sa.String(), nullable=False),
        sa.Column("selected_branch_id", sa.String(), nullable=True),
        sa.Column("selected_branch_label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id"),
    )
    op.create_index(op.f("ix_trackrule_book_id"), "trackrule", ["book_id"], unique=False)

    op.create_table(
        "jobrecord",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.String(), nullable=True),
        sa.Column("result_json", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobrecord_book_id"), "jobrecord", ["book_id"], unique=False)
    op.create_index(op.f("ix_jobrecord_status"), "jobrecord", ["status"], unique=False)
    op.create_index(op.f("ix_jobrecord_type"), "jobrecord", ["type"], unique=False)

    op.create_table(
        "artifact",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("chapter_count", sa.Integer(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifact_book_id"), "artifact", ["book_id"], unique=False)
    op.create_index(op.f("ix_artifact_format"), "artifact", ["format"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_artifact_format"), table_name="artifact")
    op.drop_index(op.f("ix_artifact_book_id"), table_name="artifact")
    op.drop_table("artifact")

    op.drop_index(op.f("ix_jobrecord_type"), table_name="jobrecord")
    op.drop_index(op.f("ix_jobrecord_status"), table_name="jobrecord")
    op.drop_index(op.f("ix_jobrecord_book_id"), table_name="jobrecord")
    op.drop_table("jobrecord")

    op.drop_index(op.f("ix_trackrule_book_id"), table_name="trackrule")
    op.drop_table("trackrule")

    op.drop_index(op.f("ix_bookstate_book_id"), table_name="bookstate")
    op.drop_table("bookstate")

    op.drop_index(op.f("ix_book_slug"), table_name="book")
    op.drop_table("book")
