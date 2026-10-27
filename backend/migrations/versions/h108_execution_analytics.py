"""Execution evidence and a reporting epoch; financial history is preserved."""

import sqlalchemy as sa
from alembic import op

revision = "h108"
down_revision = "h107"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("account_purpose", sa.String(24), nullable=False, server_default="standard"),
    )
    op.add_column(
        "request_attempts",
        sa.Column("traffic_class", sa.String(24), nullable=False, server_default="chat"),
    )
    op.create_table(
        "analytics_epochs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_table(
        "execution_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            sa.String(64),
            sa.ForeignKey("request_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("at", sa.String(40), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_execution_events_request_id", "execution_events", ["request_id"])


def downgrade():
    op.drop_table("execution_events")
    op.drop_table("analytics_epochs")
    op.drop_column("request_attempts", "traffic_class")
    op.drop_column("users", "account_purpose")
