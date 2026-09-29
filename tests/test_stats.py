from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.models import Assignment, User
from bot.services.assignments import find_reminder_due
from bot.services.stats import build_stats, render_digest, render_stats
from bot.utils.time import to_utc

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 9, 29, 14, 30, tzinfo=TZ)


def make_assignment(
    user_id: int = 1,
    title: str = "Лаба",
    days: int = 1,
    hour: int = 18,
    status: str = "active",
    completed_at: datetime | None = None,
) -> Assignment:
    local = (NOW + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return Assignment(
        id=abs(hash(title)) % 10000,
        user_id=user_id,
        title=title,
        kind="lab",
        deadline=to_utc(local),
        status=status,
        reminded_offsets=[],
        created_at=to_utc(NOW),
        completed_at=completed_at,
    )


def test_counts_active_and_overdue() -> None:
    assignments = [
        make_assignment(title="просроченная", days=-2),
        make_assignment(title="сегодня", days=0),
        make_assignment(title="завтра", days=1),
        make_assignment(title="через неделю", days=7),
        make_assignment(title="сделанная", status="done", completed_at=to_utc(NOW)),
    ]
    stats = build_stats(User(tg_id=1), assignments, TZ, NOW)
    assert stats.active == 4
    assert stats.overdue == 1
    assert stats.today == 1
    assert stats.done_total == 1
    assert stats.next is not None and stats.next[0].title == "сегодня"


def test_load_peak_detected() -> None:
    assignments = [make_assignment(title=f"работа {i}", days=2) for i in range(3)]
    stats = build_stats(User(tg_id=1), assignments, TZ, NOW)
    peak = max(stats.day_loads, key=lambda load: load.count)
    assert peak.count == 3
    assert stats.load_label == "плотно"
    assert stats.load_icon == "🟡"


def test_overload_label() -> None:
    assignments = [make_assignment(title=f"работа {i}", days=3) for i in range(5)]
    stats = build_stats(User(tg_id=1), assignments, TZ, NOW)
    assert stats.load_label == "перегруз"
    assert stats.load_icon == "🔴"


def test_render_stats_contains_deadline_and_warning() -> None:
    assignments = [make_assignment(title=f"работа {i}", days=1) for i in range(3)]
    stats = build_stats(User(tg_id=1), assignments, TZ, NOW)
    text = render_stats(stats, NOW)
    assert "Сводка" in text
    assert "работа 0" in text
    assert "разнеси" in text


def test_render_stats_empty() -> None:
    stats = build_stats(User(tg_id=1), [], TZ, NOW)
    assert "Активных работ нет" in render_stats(stats, NOW)


def test_render_digest_lists_today_and_overdue() -> None:
    assignments = [
        make_assignment(title="просроченная", days=-1),
        make_assignment(title="сегодня", days=0),
        make_assignment(title="позже", days=5),
    ]
    text = render_digest(assignments, TZ, NOW)
    assert "Просрочено" in text
    assert "Сдаём сегодня" in text
    assert "позже" not in text


def test_render_digest_without_work() -> None:
    assert "выдохни" in render_digest([], TZ, NOW)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(24, [24]), (6, [24, 6]), (1, [24, 6, 1])],
)
def test_find_reminder_due_reports_elapsed_offsets(offset: int, expected: list[int]) -> None:
    assignment = make_assignment(days=0)
    assignment.deadline = to_utc(NOW + timedelta(hours=offset))
    due = find_reminder_due(assignment, [24, 6, 1], to_utc(NOW))
    assert due == expected


def test_find_reminder_due_skips_already_sent() -> None:
    assignment = make_assignment(days=0)
    assignment.deadline = to_utc(NOW + timedelta(hours=3))
    assignment.reminded_offsets = [24]
    assert find_reminder_due(assignment, [24, 6, 1], to_utc(NOW)) == [6]
