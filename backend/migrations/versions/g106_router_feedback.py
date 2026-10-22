"""Content-free owned router outcomes for bounded drift adaptation."""

import sqlalchemy as sa
from alembic import op

revision = "g106"
down_revision = "f105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "router_outcomes",
        sa.Column(
            "request_id",
            sa.String(64),
            sa.ForeignKey("request_attempts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("config_id", sa.String(100), nullable=False),
        sa.Column("failed", sa.Boolean(), nullable=False),
        sa.Column("tool_error", sa.Boolean(), nullable=False),
        sa.Column("dislike", sa.Boolean(), nullable=False),
        sa.Column("retry", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index(
        "ix_router_outcomes_window", "router_outcomes", ["artifact_hash", "config_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_router_outcomes_window", table_name="router_outcomes")
    op.drop_table("router_outcomes")
