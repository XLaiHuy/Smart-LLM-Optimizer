from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.storage.models import AnalyticsEpoch, Attempt, User


async def current_epoch(db: AsyncSession) -> AnalyticsEpoch | None:
    return cast(
        AnalyticsEpoch | None,
        await db.scalar(select(AnalyticsEpoch).order_by(AnalyticsEpoch.started_at.desc()).limit(1)),
    )


def product_attempts() -> tuple[ColumnElement[bool], ...]:
    return (
        Attempt.traffic_class == "chat",
        Attempt.research_run_id.is_(None),
        Attempt.owner_user_id.in_(select(User.id).where(User.account_purpose == "standard")),
    )
