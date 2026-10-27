import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, cast

from pwdlib import PasswordHash
from sqlalchemy import delete, select

from app.config import Settings
from app.contracts.dtos import Principal
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import AuthSession, User
from app.storage.repositories import uid

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash("not-a-user-password")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def principal_of(user: User) -> Principal:
    return Principal(
        id=user.id,
        username=user.username,
        role=cast(Literal["user", "admin"], user.role),
        quota_usd=Decimal(user.quota_usd),
    )


class AuthService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    async def create_user(
        self,
        username: str,
        password: str,
        role: Literal["user", "admin"] = "user",
        quota: Decimal | None = None,
        *,
        account_purpose: Literal["standard", "internal_audit"] = "standard",
    ) -> Principal:
        if not username.strip() or len(username) > 64 or len(password) < 8 or len(password) > 256:
            raise AppError("VALIDATION_ERROR", 422, "Username and password (8–256 chars) required")
        actual_quota = quota if quota is not None else self.settings.default_user_budget_usd
        if not actual_quota.is_finite() or actual_quota <= 0:
            raise AppError("VALIDATION_ERROR", 422, "Quota must be positive")
        hashed = await asyncio.to_thread(password_hasher.hash, password)
        async with self.db.write() as db:
            if await db.scalar(select(User).where(User.username == username)):
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Username already exists")
            user = User(
                id=uid(),
                username=username,
                password_hash=hashed,
                role=role,
                quota_usd=str(actual_quota),
                account_purpose=account_purpose,
            )
            db.add(user)
            return principal_of(user)

    async def login(self, username: str, password: str) -> tuple[Principal, str]:
        async with self.db.sessions() as db:
            user = await db.scalar(select(User).where(User.username == username))
        valid = await asyncio.to_thread(
            password_hasher.verify, password, user.password_hash if user else DUMMY_HASH
        )
        if user is None or not valid:
            raise AppError("AUTH_REQUIRED", 401, "Invalid username or password")
        token = secrets.token_urlsafe(32)
        async with self.db.write() as db:
            db.add(
                AuthSession(
                    token_hash=token_hash(token),
                    user_id=user.id,
                    expires_at=(
                        datetime.now(UTC) + timedelta(hours=self.settings.auth_session_hours)
                    ).isoformat(),
                )
            )
        return principal_of(user), token

    async def resolve(self, token: str | None) -> Principal:
        if not token:
            raise AppError("AUTH_REQUIRED", 401, "Authentication required")
        async with self.db.sessions() as db:
            session = await db.get(AuthSession, token_hash(token))
            if session is None or datetime.fromisoformat(session.expires_at) <= datetime.now(UTC):
                raise AppError("AUTH_REQUIRED", 401, "Session expired or revoked")
            user = await db.get(User, session.user_id)
            if user is None:
                raise AppError("AUTH_REQUIRED", 401, "Account unavailable")
            return principal_of(user)

    async def logout(self, token: str | None) -> None:
        if token:
            async with self.db.write() as db:
                await db.execute(
                    delete(AuthSession).where(AuthSession.token_hash == token_hash(token))
                )
