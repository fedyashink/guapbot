from __future__ import annotations

import html
from datetime import datetime, timedelta

WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTH_SHORT = [
    "янв", "фев", "мар", "апр", "мая", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

KIND_LABELS = {
    "lab": "лабораторная",
    "coursework": "курсовая",
    "exam": "экзамен",
    "defense": "защита",
    "other": "задача",
}

LOAD_LEVELS = (
    (0, "свободно", "⚪"),
    (1, "нормально", "🟢"),
    (3, "плотно", "🟡"),
    (5, "перегруз", "🔴"),
)


def esc(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def plural(number: int, one: str, few: str, many: str) -> str:
    remainder = abs(number) % 100
    if 11 <= remainder <= 19:
        return many
    remainder %= 10
    if remainder == 1:
        return one
    if 2 <= remainder <= 4:
        return few
    return many


def hours_word(number: int) -> str:
    return f"{number} {plural(number, 'час', 'часа', 'часов')}"


def minutes_word(number: int) -> str:
    return f"{number} {plural(number, 'минута', 'минуты', 'минут')}"


def days_word(number: int) -> str:
    return f"{number} {plural(number, 'день', 'дня', 'дней')}"


def human_delta(delta: timedelta) -> str:
    total = int(abs(delta).total_seconds())
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days >= 1:
        return days_word(days)
    if hours >= 1:
        return f"{hours} {plural(hours, 'ч', 'ч', 'ч')} {minutes} мин" if minutes else hours_word(hours)
    return minutes_word(max(minutes, 0))


def countdown_text(target: datetime, now: datetime) -> str:
    delta = target - now
    if delta.total_seconds() <= 0:
        overdue = human_delta(-delta)
        return f"просрочено на {overdue}"
    return f"осталось {human_delta(delta)}"


def human_datetime(value: datetime) -> str:
    return (
        f"{WEEKDAY_SHORT[value.weekday()]} {value.day:02d}.{value.month:02d}.{value.year} "
        f"в {value.hour:02d}:{value.minute:02d}"
    )


def short_date(value: datetime) -> str:
    return f"{value.day:02d}.{MONTH_SHORT[value.month - 1]}"


def load_level(count: int) -> tuple[str, str]:
    label, icon = LOAD_LEVELS[0][1], LOAD_LEVELS[0][2]
    for threshold, name, mark in LOAD_LEVELS:
        if count >= threshold:
            label, icon = name, mark
    return label, icon


def bar(count: int, width: int = 10) -> str:
    filled = min(width, count * 2)
    return "▰" * filled + "▱" * (width - filled)


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, KIND_LABELS["other"])


def truncate(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
