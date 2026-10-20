from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user")
    quota_usd: Mapped[str] = mapped_column(String(64))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[str] = mapped_column(String(40))


class Conversation(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    active_attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class StoredMessage(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("session_id", "position"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(64))


class Attempt(Base):
    __tablename__ = "request_attempts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "client_request_id"),
        Index("ix_attempt_owner_created", "owner_user_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    client_request_id: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    dispatched: Mapped[bool] = mapped_column(default=False)
    execution_source: Mapped[str] = mapped_column(String(16), default="mock")
    created_at: Mapped[str] = mapped_column(String(40))
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class InferenceCall(Base):
    __tablename__ = "inference_calls"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("request_attempts.id"), index=True)
    metadata_json: Mapped[str] = mapped_column(Text)


class OptimizationEvent(Base):
    __tablename__ = "optimization_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("request_attempts.id"), index=True)
    metadata_json: Mapped[str] = mapped_column(Text)


class MemoryRevision(Base):
    __tablename__ = "memory_revisions"
    __table_args__ = (UniqueConstraint("session_id", "revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)


class Reservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (UniqueConstraint("request_id", "call_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("request_attempts.id"), index=True)
    call_id: Mapped[str] = mapped_column(String(64))
    # Decimal strings: arithmetic only in Python under BEGIN IMMEDIATE, never SQL SUM(float).
    reserved_usd: Mapped[str] = mapped_column(String(64))
    settled_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("session_id", "content_hash"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="extracted")
    text: Mapped[str] = mapped_column(Text)
    sections_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    vector_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(100))


class StoredJob(Base):
    __tablename__ = "document_jobs"
    id: Mapped[str] = mapped_column(ForeignKey("request_attempts.id"), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)


class UsageRecord(Base):
    # Deliberately independent of content-bearing rows; remains after explicit content purge.
    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operation_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(40))
    execution_source: Mapped[str] = mapped_column(String(16))
    model_id: Mapped[str] = mapped_column(String(100))
    record_json: Mapped[str] = mapped_column(Text)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    catalog_json: Mapped[str] = mapped_column(Text)


class QuotaAudit(Base):
    __tablename__ = "quota_audit"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    before_usd: Mapped[str] = mapped_column(String(64))
    after_usd: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(40))
