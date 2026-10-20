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
