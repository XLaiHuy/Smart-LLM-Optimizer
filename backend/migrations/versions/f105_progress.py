"""Persist content-free processing stages; preserve existing accounts/history."""

import sqlalchemy as sa
from alembic import op

revision = "f105"
down_revision = "e104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            sa.String(64),
            sa.ForeignKey("request_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("finished_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_processing_events_request_id", "processing_events", ["request_id"])


def downgrade() -> None:
    op.drop_table("processing_events")
