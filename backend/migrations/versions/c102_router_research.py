"""Research runs and audited reconciliation; preserves existing accounts/history."""

import sqlalchemy as sa
from alembic import op

revision = "c102"
down_revision = "b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("budget_usd", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint("owner_user_id", "client_request_id"),
    )
    op.create_index("ix_research_runs_owner_user_id", "research_runs", ["owner_user_id"])
    op.create_index("ix_research_runs_status", "research_runs", ["status"])
    op.execute(
        "CREATE UNIQUE INDEX ix_one_active_research ON research_runs ((1)) WHERE status IN ('pending', 'running')"
    )
    op.create_table(
        "research_trials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("research_runs.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("run_id", "position"),
    )
    op.create_index("ix_research_trials_run_id", "research_trials", ["run_id"])
    op.execute(
        "ALTER TABLE request_attempts ADD COLUMN research_run_id VARCHAR(64) REFERENCES research_runs(id)"
    )
    op.create_index("ix_request_attempts_research_run_id", "request_attempts", ["research_run_id"])
    with op.batch_alter_table("usage_records") as batch:
        batch.alter_column("session_id", existing_type=sa.String(64), nullable=True)
    op.create_table(
        "billing_reconciliations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "reservation_id",
            sa.String(64),
            sa.ForeignKey("budget_reservations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_usd", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("evidence_reference", sa.String(300), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("billing_reconciliations")
    op.drop_index("ix_request_attempts_research_run_id", table_name="request_attempts")
    op.drop_column("request_attempts", "research_run_id")
    op.drop_table("research_trials")
    op.drop_table("research_runs")
    # Keep nullable accounting session IDs: reverting must not invent chat ownership.
