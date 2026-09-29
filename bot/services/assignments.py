from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import MAX_TITLE_LENGTH
from bot.models import Assignment
from bot.utils.formatting import truncate
from bot.utils.time import to_local, to_utc, utcnow


async def create_assignment(
    session: AsyncSession,
    user_id: int,
    title: str,
    deadline_local: datetime,
    tz: ZoneInfo,
    kind: str = "other",
    notes: str | None = None,
) -> Assignment:
    assignment = Assignment(
        user_id=user_id,
        title=truncate(title, MAX_TITLE_LENGTH) or "Без названия",
        notes=notes,
        kind=kind,
        deadline=to_utc(deadline_local),
        status="active",
        reminded_offsets=[],
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def get_assignment(session: AsyncSession, assignment_id: int, user_id: int) -> Assignment | None:
    return await session.scalar(
        select(Assignment).where(Assignment.id == assignment_id, Assignment.user_id == user_id)
    )


async def list_assignments(
    session: AsyncSession, user_id: int, status: str | None = "active"
) -> list[Assignment]:
    query = select(Assignment).where(Assignment.user_id == user_id)
    if status:
        query = query.where(Assignment.status == status)
    items = list(await session.scalars(query))
    items.sort(key=lambda item: item.deadline)
    return items


async def mark_done(session: AsyncSession, assignment: Assignment) -> None:
    assignment.status = "done"
    assignment.completed_at = utcnow()
    await session.flush()


async def reopen(session: AsyncSession, assignment: Assignment) -> None:
    assignment.status = "active"
    assignment.completed_at = None
    await session.flush()


async def delete_assignment(session: AsyncSession, assignment: Assignment) -> None:
    await session.delete(assignment)
    await session.flush()


async def postpone(
    session: AsyncSession, assignment: Assignment, until_local: datetime, tz: ZoneInfo
) -> None:
    assignment.deadline = to_utc(until_local)
    assignment.reminded_offsets = []
    assignment.status = "active"
    assignment.completed_at = None
    await session.flush()


def local_deadline(assignment: Assignment, tz: ZoneInfo) -> datetime:
    return to_local(assignment.deadline, tz)


async def mark_sent(session: AsyncSession, assignment: Assignment, offset: int) -> None:
    sent = list(assignment.reminded_offsets or [])
    if offset not in sent:
        sent.append(offset)
        assignment.reminded_offsets = sent
        await session.flush()


def find_reminder_due(
    assignment: Assignment, user_offsets: list[int], now: datetime
) -> list[int]:
    due: list[int] = []
    already = set(assignment.reminded_offsets or [])
    for offset in user_offsets:
        if offset in already:
            continue
        remind_at = assignment.deadline - timedelta(hours=offset)
        if remind_at <= now:
            due.append(offset)
    return sorted(due, reverse=True)
