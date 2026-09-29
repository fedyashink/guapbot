from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import DEFAULT_TZ, resolve_timezone
from bot.models import User


async def get_or_create_user(
    session: AsyncSession, tg_id: int, username: str | None = None
) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, username=username, timezone=DEFAULT_TZ)
        session.add(user)
        await session.flush()
    elif username and user.username != username:
        user.username = username
        await session.flush()
    return user


def user_tz(user: User) -> ZoneInfo:
    return resolve_timezone(user.timezone)


def local_now(user: User) -> datetime:
    return datetime.now(user_tz(user))


def sanitize_reminder_offsets(values: object, fallback: list[int] | None = None) -> list[int]:
    if not isinstance(values, list) or not values:
        return list(fallback or [])
    cleaned: list[int] = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 24 * 31 and number not in cleaned:
            cleaned.append(number)
    return sorted(cleaned, reverse=True) or list(fallback or [])
