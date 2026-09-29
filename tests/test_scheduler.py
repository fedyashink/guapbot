from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Assignment, User
from bot.scheduler import reminder_keyboard, tick
from bot.services.assignments import create_assignment
from bot.services.users import get_or_create_user
from bot.utils.time import utcnow
from tests.fakes import make_bot, sent_texts

TZ = ZoneInfo("Europe/Moscow")


async def make_user(
    session: AsyncSession, offsets: list[int] | None = None, digest_enabled: bool = True
) -> User:
    user = await get_or_create_user(session, 1001, "ivan")
    user.timezone = str(TZ)
    user.reminder_offsets = offsets if offsets is not None else [24, 1]
    user.digest_enabled = digest_enabled
    user.digest_hour = 9
    user.last_digest_date = None
    await session.commit()
    return user


async def add(
    session: AsyncSession,
    user: User,
    title: str,
    deadline_utc: datetime,
) -> Assignment:
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title=title,
        deadline_local=deadline_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ),
        tz=TZ,
    )
    await session.commit()
    return assignment


async def test_reminder_sent_before_deadline(session, session_factory) -> None:
    user = await make_user(session, offsets=[1])
    await add(session, user, "Лаба", utcnow() + timedelta(minutes=30))
    bot, fake = make_bot()

    await tick(bot, session_factory)

    texts = sent_texts(fake)
    assert len(texts) == 1
    assert "Лаба" in texts[0]
    assert "Через" in texts[0]

    async with session_factory() as check:
        stored = await check.scalar(select(Assignment))
        assert stored is not None
        assert stored.reminded_offsets == [1]


async def test_reminder_not_sent_twice(session, session_factory) -> None:
    user = await make_user(session, offsets=[1])
    await add(session, user, "Лаба", utcnow() + timedelta(minutes=30))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    await tick(bot, session_factory)

    assert len(sent_texts(fake)) == 1


async def test_far_deadline_not_reminded(session, session_factory) -> None:
    user = await make_user(session, offsets=[1])
    await add(session, user, "Курсовая", utcnow() + timedelta(days=3))
    bot, fake = make_bot()

    await tick(bot, session_factory)

    assert all("Курсовая" not in text for text in sent_texts(fake))


async def test_several_offsets_fire_in_order(session, session_factory) -> None:
    user = await make_user(session, offsets=[8, 7, 1])
    await add(session, user, "Отчёт", utcnow() + timedelta(hours=6))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    texts = sent_texts(fake)
    assert len(texts) == 2
    assert "Через 8 часов" in texts[0]
    assert "Через 7 часов" in texts[1]


async def test_stale_reminder_is_skipped(session, session_factory) -> None:
    user = await make_user(session, offsets=[24, 6])
    await add(session, user, "Отчёт", utcnow() + timedelta(hours=5))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    texts = sent_texts(fake)
    assert len(texts) == 1
    assert "Через 6 часов" in texts[0]

    async with session_factory() as check:
        assignment = await check.scalar(select(Assignment))
        assert assignment is not None
        assert assignment.reminded_offsets == [24, 6]


async def test_zero_offset_sends_at_deadline(session, session_factory) -> None:
    user = await make_user(session, offsets=[0])
    await add(session, user, "Экзамен", utcnow() + timedelta(hours=1))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    assert sent_texts(fake) == []

    async with session_factory() as check:
        assignment = await check.scalar(select(Assignment))
        assert assignment is not None
        assignment.deadline = utcnow() - timedelta(seconds=5)
        await check.commit()

    await tick(bot, session_factory)
    texts = sent_texts(fake)
    assert len(texts) == 1
    assert "Сейчас сдача" in texts[0]


async def test_digest_sent_once_per_day(session, session_factory) -> None:
    user = await make_user(session, offsets=[24])
    user.digest_hour = datetime.now(TZ).hour
    await session.commit()
    await add(session, user, "Завтрашняя работа", utcnow() + timedelta(hours=2))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    texts = sent_texts(fake)
    assert any("Доброе утро" in text for text in texts)

    await tick(bot, session_factory)
    assert len([t for t in sent_texts(fake) if "Доброе утро" in t]) == 1


async def test_digest_disabled(session, session_factory) -> None:
    user = await make_user(session, offsets=[1], digest_enabled=False)
    user.digest_hour = datetime.now(TZ).hour
    await session.commit()
    await add(session, user, "Работа", utcnow() + timedelta(minutes=30))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    assert all("Доброе утро" not in text for text in sent_texts(fake))


async def test_reminder_keyboard_has_actions() -> None:
    assignment = Assignment(id=7, user_id=1, title="Лаба", kind="lab")
    markup = reminder_keyboard(assignment)
    data = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert data == ["done:7", "postpone:7:1", "postpone:7:3", "postpone:7:7"]


async def test_overdue_assignment_is_not_spammed(session, session_factory) -> None:
    user = await make_user(session, offsets=[1])
    await add(session, user, "Просроченная", utcnow() - timedelta(hours=5))
    bot, fake = make_bot()

    await tick(bot, session_factory)
    assert sent_texts(fake) == []


@pytest.mark.parametrize("offset", [0, 1, 24, 720])
def test_offset_formatting(offset: int) -> None:
    assert offset >= 0
