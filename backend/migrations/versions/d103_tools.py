"""Owned tool activity and next-turn recovery; no history reset."""

import sqlalchemy as sa
from alembic import op

revision = "d103"
down_revision = "c102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "tool_recovery_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "operation_id",
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
        sa.Column("call_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("operation_id", "call_id"),
    )
    op.create_index("ix_tool_invocations_operation_id", "tool_invocations", ["operation_id"])
    op.create_index("ix_tool_invocations_session_id", "tool_invocations", ["session_id"])


def downgrade() -> None:
    op.drop_table("tool_invocations")
    op.drop_column("sessions", "tool_recovery_required")
