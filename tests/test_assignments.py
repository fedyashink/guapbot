from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.services.assignments import (
    create_assignment,
    delete_assignment,
    get_assignment,
    list_assignments,
    local_deadline,
    mark_done,
    mark_sent,
    postpone,
    reopen,
)
from bot.services.users import get_or_create_user, sanitize_reminder_offsets
from bot.utils.time import to_utc, utcnow

TZ = ZoneInfo("Europe/Moscow")


@pytest.fixture
async def user(session):
    created = await get_or_create_user(session, 42, "student")
    await session.commit()
    return created


async def test_get_or_create_user_is_idempotent(session) -> None:
    first = await get_or_create_user(session, 7, "a")
    second = await get_or_create_user(session, 7, "a")
    assert first.id == second.id
    assert second.username == "a"


async def test_create_assignment_converts_to_utc(session, user) -> None:
    local = datetime(2026, 10, 1, 18, 0, tzinfo=TZ)
    assignment = await create_assignment(
        session=session, user_id=user.id, title="Лаба 1", deadline_local=local, tz=TZ, kind="lab"
    )
    assert assignment.deadline == to_utc(local)
    assert assignment.status == "active"
    assert assignment.reminded_offsets == []
    assert local_deadline(assignment, TZ) == local


async def test_list_assignments_sorted_by_deadline(session, user) -> None:
    base = datetime(2026, 10, 1, 10, 0, tzinfo=TZ)
    for offset, title in [(3, "третья"), (1, "вторая"), (2, "первая")]:
        await create_assignment(
            session=session,
            user_id=user.id,
            title=title,
            deadline_local=base + timedelta(days=offset),
            tz=TZ,
        )
    items = await list_assignments(session, user.id)
    assert [item.title for item in items] == ["вторая", "первая", "третья"]


async def test_mark_done_and_reopen(session, user) -> None:
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title="Курсовая",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    await mark_done(session, assignment)
    assert assignment.completed_at is not None
    assert await list_assignments(session, user.id, status="done") != []
    assert await list_assignments(session, user.id, status="active") == []

    await reopen(session, assignment)
    assert assignment.status == "active"
    assert assignment.completed_at is None
    assert len(await list_assignments(session, user.id, status="active")) == 1


async def test_get_assignment_checks_owner(session, user) -> None:
    other = await get_or_create_user(session, 999, "other")
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title="Лаба",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    assert await get_assignment(session, assignment.id, user.id) is not None
    assert await get_assignment(session, assignment.id, other.id) is None


async def test_delete_assignment(session, user) -> None:
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title="Лаба",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    await delete_assignment(session, assignment)
    await session.commit()
    assert await list_assignments(session, user.id, status=None) == []


async def test_postpone_resets_reminders(session, user) -> None:
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title="Лаба",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    await mark_sent(session, assignment, 24)
    await mark_sent(session, assignment, 6)
    new_local = local_deadline(assignment, TZ) + timedelta(days=1)
    await postpone(session, assignment, new_local, TZ)
    assert assignment.deadline == to_utc(new_local)
    assert assignment.reminded_offsets == []
    assert assignment.status == "active"


async def test_mark_sent_does_not_duplicate(session, user) -> None:
    assignment = await create_assignment(
        session=session,
        user_id=user.id,
        title="Лаба",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    await mark_sent(session, assignment, 24)
    await mark_sent(session, assignment, 24)
    assert assignment.reminded_offsets == [24]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([1, 24, 6, 6], [24, 6, 1]),
        (["bad", 3], [3]),
        ([], [7, 1]),
        ([-5], [7, 1]),
    ],
)
def test_sanitize_reminder_offsets(values, expected) -> None:
    assert sanitize_reminder_offsets(values, [7, 1]) == expected


async def test_cascade_delete_user_assignments(session, user) -> None:
    await create_assignment(
        session=session,
        user_id=user.id,
        title="Лаба",
        deadline_local=datetime(2026, 10, 1, 18, 0, tzinfo=TZ),
        tz=TZ,
    )
    await session.delete(user)
    await session.commit()
    assert await list_assignments(session, user.id, status=None) == []


def test_utcnow_is_naive() -> None:
    assert utcnow().tzinfo is None
