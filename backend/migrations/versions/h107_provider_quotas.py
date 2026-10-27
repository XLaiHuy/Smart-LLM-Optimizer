"""Persistent provider admission shared by chat, workers and training."""

import sqlalchemy as sa
from alembic import op

revision = "h107"
down_revision = "g106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_quota_buckets",
        sa.Column("scope_key", sa.String(256), primary_key=True),
        sa.Column("state_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_quota_buckets")
