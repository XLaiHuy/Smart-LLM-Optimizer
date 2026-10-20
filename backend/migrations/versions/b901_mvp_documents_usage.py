"""Documents, durable jobs and retained usage. Frozen SQLite schema snapshot."""

import sqlalchemy as sa
from alembic import op

revision = "b901"
down_revision = "70542f1078a5"
branch_labels = None
depends_on = None

STATEMENTS = (
    "CREATE TABLE documents (\n\tid VARCHAR(64) NOT NULL, \n\towner_user_id VARCHAR(64) NOT NULL, \n\tsession_id VARCHAR(64) NOT NULL, \n\tfilename VARCHAR(255) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\ttext TEXT NOT NULL, \n\tsections_json TEXT NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\terror_code VARCHAR(64), \n\tPRIMARY KEY (id), \n\tUNIQUE (session_id, content_hash), \n\tFOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tFOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE\n)",
    "CREATE INDEX ix_documents_owner_user_id ON documents (owner_user_id)",
    "CREATE INDEX ix_documents_session_id ON documents (session_id)",
    "CREATE TABLE document_chunks (\n\tid VARCHAR(64) NOT NULL, \n\tdocument_id VARCHAR(64) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tcontent TEXT NOT NULL, \n\tlocation VARCHAR(200) NOT NULL, \n\tvector_json TEXT, \n\tversion VARCHAR(100) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)",
    "CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id)",
    "CREATE TABLE document_jobs (\n\tid VARCHAR(64) NOT NULL, \n\tpayload_json TEXT NOT NULL, \n\tprogress INTEGER NOT NULL, \n\ttotal INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(id) REFERENCES request_attempts (id)\n)",
    "CREATE TABLE usage_records (\n\tid VARCHAR(64) NOT NULL, \n\towner_user_id VARCHAR(64) NOT NULL, \n\toperation_id VARCHAR(64) NOT NULL, \n\tsession_id VARCHAR(64) NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tcategory VARCHAR(40) NOT NULL, \n\texecution_source VARCHAR(16) NOT NULL, \n\tmodel_id VARCHAR(100) NOT NULL, \n\trecord_json TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(owner_user_id) REFERENCES users (id)\n)",
    "CREATE INDEX ix_usage_records_created_at ON usage_records (created_at)",
    "CREATE INDEX ix_usage_records_operation_id ON usage_records (operation_id)",
    "CREATE INDEX ix_usage_records_owner_user_id ON usage_records (owner_user_id)",
    "CREATE INDEX ix_usage_records_session_id ON usage_records (session_id)",
    "CREATE TABLE price_snapshots (\n\tid VARCHAR(100) NOT NULL, \n\tcatalog_json TEXT NOT NULL, \n\tPRIMARY KEY (id)\n)",
    "CREATE TABLE quota_audit (\n\tid VARCHAR(64) NOT NULL, \n\tactor_id VARCHAR(64) NOT NULL, \n\tuser_id VARCHAR(64) NOT NULL, \n\tbefore_usd VARCHAR(64) NOT NULL, \n\tafter_usd VARCHAR(64) NOT NULL, \n\treason VARCHAR(300) NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)",
    "CREATE VIRTUAL TABLE document_fts USING fts5(chunk_id UNINDEXED, content, tokenize='unicode61 remove_diacritics 0')",
)


def upgrade() -> None:
    op.add_column(
        "request_attempts",
        sa.Column("execution_source", sa.String(16), nullable=False, server_default="mock"),
    )
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    with op.batch_alter_table("request_attempts") as batch:
        batch.drop_column("execution_source")
    op.execute("DROP TABLE document_fts")
    for name in (
        "quota_audit",
        "price_snapshots",
        "usage_records",
        "document_jobs",
        "document_chunks",
        "documents",
    ):
        op.execute(f"DROP TABLE {name}")
