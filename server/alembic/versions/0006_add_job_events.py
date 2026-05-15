"""add job events"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_job_events"
down_revision = "0005_add_source_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobevent",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("payload_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobrecord.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobevent_job_id"), "jobevent", ["job_id"], unique=False)
    op.create_index(op.f("ix_jobevent_level"), "jobevent", ["level"], unique=False)
    op.create_index(op.f("ix_jobevent_event_type"), "jobevent", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobevent_event_type"), table_name="jobevent")
    op.drop_index(op.f("ix_jobevent_level"), table_name="jobevent")
    op.drop_index(op.f("ix_jobevent_job_id"), table_name="jobevent")
    op.drop_table("jobevent")
