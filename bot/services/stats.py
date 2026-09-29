from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bot.models import Assignment, User
from bot.utils.formatting import (
    bar,
    days_word,
    esc,
    kind_label,
    load_level,
)
from bot.utils.time import to_local


@dataclass
class DayLoad:
    day: date
    items: list[tuple[Assignment, datetime]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def level(self) -> tuple[str, str]:
        return load_level(self.count)


@dataclass
class Stats:
    active: int
    done_total: int
    done_week: int
    overdue: int
    today: int
    next_7: int
    next: tuple[Assignment, datetime] | None
    day_loads: list[DayLoad]
    load_label: str
    load_icon: str


def build_stats(
    user: User,
    assignments: list[Assignment],
    tz: ZoneInfo,
    now_local: datetime,
) -> Stats:
    active = [a for a in assignments if a.status == "active"]
    done = [a for a in assignments if a.status == "done"]

    local_items: list[tuple[Assignment, datetime]] = [
        (a, to_local(a.deadline, tz)) for a in active
    ]
    local_items.sort(key=lambda pair: pair[1])

    week_ago = now_local - timedelta(days=7)
    done_week = sum(
        1
        for a in done
        if a.completed_at is not None
        and to_local(a.completed_at, tz) >= week_ago
    )

    today_date = now_local.date()
    horizon = today_date + timedelta(days=7)
    today_count = 0
    week_count = 0
    overdue = 0
    day_loads: list[DayLoad] = [DayLoad(today_date + timedelta(days=i)) for i in range(7)]
    day_index = {load.day: load for load in day_loads}

    for assignment, local in local_items:
        if local < now_local:
            overdue += 1
            continue
        if local.date() == today_date:
            today_count += 1
        if local.date() < horizon:
            week_count += 1
            day_index[local.date()].items.append((assignment, local))

    peak = max((load.count for load in day_loads), default=0)
    label, icon = load_level(peak)
    upcoming = [pair for pair in local_items if pair[1] >= now_local]
    next_item = upcoming[0] if upcoming else (local_items[0] if local_items else None)

    return Stats(
        active=len(active),
        done_total=len(done),
        done_week=done_week,
        overdue=overdue,
        today=today_count,
        next_7=week_count,
        next=next_item,
        day_loads=day_loads,
        load_label=label,
        load_icon=icon,
    )


def render_stats(stats: Stats, now_local: datetime) -> str:
    lines: list[str] = ["<b>📊 Сводка по дедлайнам</b>", ""]

    if stats.active == 0:
        lines.append("Активных работ нет — можно выдохнуть 🎉")
        return "\n".join(lines)

    lines.append(f"Активных работ: <b>{stats.active}</b>")
    if stats.overdue:
        lines.append(f"🔴 Просрочено: <b>{stats.overdue}</b> — стоит закрыть прямо сейчас")
    if stats.today:
        lines.append(f"📌 Сегодня сдаётся: <b>{stats.today}</b>")
    lines.append(f"На ближайшие 7 дней: <b>{stats.next_7}</b>")
    lines.append(f"Выполнено всего: {stats.done_total} (за неделю: {stats.done_week})")

    if stats.next is not None:
        assignment, local = stats.next
        lines.append("")
        lines.append(
            f"Ближайший дедлайн: <b>{local.day:02d}.{local.month:02d} "
            f"в {local.hour:02d}:{local.minute:02d}</b> — {kind_label(assignment.kind)}"
        )
        lines.append(f"  {assignment.title}")

    lines.append("")
    lines.append(f"<b>Загрузка по дням</b> (пик: {stats.load_icon} {stats.load_label})")
    risk = risk_comment(stats.day_loads)
    for load in stats.day_loads:
        marker = "◉" if load.day == now_local.date() else " "
        _, icon = load.level
        lines.append(f"{marker} {load.day.day:02d}.{load.day.month:02d} {bar(load.count)} {load.count} {icon}")
    if risk:
        lines.append("")
        lines.append(risk)

    if stats.overdue == 0 and stats.active > 0:
        lines.append("")
        lines.append("Просрочек нет — так держать 💪")
    return "\n".join(lines)


def weekly_forecast(
    assignments: list[Assignment], tz: ZoneInfo, now_local: datetime, days: int = 7
) -> list[DayLoad]:
    loads = [DayLoad(now_local.date() + timedelta(days=i)) for i in range(days)]
    index = {load.day: load for load in loads}
    for assignment in assignments:
        if assignment.status != "active":
            continue
        local = to_local(assignment.deadline, tz)
        if local.day in index and local >= now_local:
            index[local.day].items.append((assignment, local))
    return loads


def render_digest(assignments: list[Assignment], tz: ZoneInfo, now_local: datetime) -> str:
    active = sorted(
        (a for a in assignments if a.status == "active"),
        key=lambda a: a.deadline,
    )
    overdue = [
        (a, to_local(a.deadline, tz))
        for a in active
        if to_local(a.deadline, tz) < now_local
    ]
    today = [
        (a, to_local(a.deadline, tz))
        for a in active
        if to_local(a.deadline, tz).date() == now_local.date()
    ]
    soon = [
        (a, to_local(a.deadline, tz))
        for a in active
        if now_local < to_local(a.deadline, tz) <= now_local + timedelta(days=3)
    ]

    lines = ["<b>Доброе утро!</b> ☀️", ""]

    if overdue:
        lines.append("🔴 <b>Просрочено</b>")
        lines += [f"  • {esc(a.title)}" for a, _ in overdue]
        lines.append("")

    if today:
        lines.append("📌 <b>Сдаём сегодня</b>")
        for assignment, local in today:
            lines.append(f"  • {esc(assignment.title)} — в {local.hour:02d}:{local.minute:02d}")
        lines.append("")

    if soon:
        lines.append("🔜 <b>В ближайшие 3 дня</b>")
        for assignment, local in soon:
            lines.append(f"  • {esc(assignment.title)} — {local.day:02d}.{local.month:02d} в {local.hour:02d}:{local.minute:02d}")
        lines.append("")

    if not active:
        lines.append("Дедлайнов нет — выдохни 🎉")
    elif not overdue and not today:
        lines.append(f"Сегодня сдавать нечего. Всего в работе: {len(active)}.")

    return "\n".join(lines).strip() + "\n\nКоманда /stats — загрузка по дням."


def risk_comment(loads: list[DayLoad], deadline_days: int = 2) -> str | None:
    if not loads:
        return None
    peak = max(loads, key=lambda load: load.count)
    if peak.count >= 3:
        return (
            f"⚠️ {peak.day.day:02d}.{peak.day.month:02d} сразу {peak.count} работ — "
            f"разнеси на {days_word(deadline_days)} раньше, если можешь."
        )
    return None
