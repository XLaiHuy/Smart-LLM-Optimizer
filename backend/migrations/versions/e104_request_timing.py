"""Retain measured request time independently of purged private trace content."""

import sqlalchemy as sa
from alembic import op

revision = "e104"
down_revision = "d103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("request_attempts", sa.Column("e2e_ms", sa.Float(), nullable=True))
    # Only copy an existing measurement; never infer one from creation timestamps.
    op.execute("""UPDATE request_attempts
        SET e2e_ms = json_extract(response_json, '$.timing.e2e_ms')
        WHERE response_json IS NOT NULL AND json_valid(response_json)""")


def downgrade() -> None:
    op.drop_column("request_attempts", "e2e_ms")
