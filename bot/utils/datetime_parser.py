from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MONTHS: dict[str, int] = {
    "январь": 1, "января": 1, "янв": 1,
    "февраль": 2, "февраля": 2, "фев": 2,
    "март": 3, "марта": 3, "мар": 3,
    "апрель": 4, "апреля": 4, "апр": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6, "июн": 6,
    "июль": 7, "июля": 7, "июл": 7,
    "август": 8, "августа": 8, "авг": 8,
    "сентябрь": 9, "сентября": 9, "сен": 9,
    "октябрь": 10, "октября": 10, "окт": 10,
    "ноябрь": 11, "ноября": 11, "ноя": 11,
    "декабрь": 12, "декабря": 12, "дек": 12,
}

WEEKDAYS: dict[str, int] = {
    "понедельник": 0, "понедельника": 0, "пн": 0, "понедельничок": 0,
    "вторник": 1, "вторника": 1, "вт": 1,
    "среда": 2, "среду": 2, "среды": 2, "ср": 2,
    "четверг": 3, "четверга": 3, "чт": 3,
    "пятница": 4, "пятницу": 4, "пятницы": 4, "пт": 4,
    "суббота": 5, "субботу": 5, "субботы": 5, "сб": 5,
    "воскресенье": 6, "воскресенья": 6, "вс": 6,
}

UNIT_SECONDS: dict[str, int] = {
    "минута": 60, "минуту": 60, "минуты": 60, "минут": 60, "мин": 60,
    "час": 3600, "часа": 3600, "часов": 3600,
    "день": 86400, "дня": 86400, "дней": 86400, "дню": 86400,
    "неделя": 604800, "неделю": 604800, "недели": 604800, "недель": 604800,
    "нед": 604800,
}

WORD_NUMBERS: dict[str, int] = {
    "один": 1, "одну": 1, "одна": 1, "раз": 1,
    "два": 2, "две": 2, "двоих": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "полтора": 1,
}

MONTH_ALT = "|".join(
    sorted((re.escape(k) for k in MONTHS), key=len, reverse=True)
)
WEEKDAY_ALT = "|".join(
    sorted((re.escape(k) for k in WEEKDAYS), key=len, reverse=True)
)

NUMBER_WORD_ALT = "|".join(sorted((re.escape(k) for k in WORD_NUMBERS), key=len, reverse=True))

RELATIVE_RE = re.compile(
    rf"\bчерез\s+(?P<num>\d+|{NUMBER_WORD_ALT})?\s*"
    r"(?P<unit>минут\w*|мин\w*|час\w*|день\w*|дн\w*|недел\w*|нед\w*)?",
    re.IGNORECASE,
)
HALF_RE = re.compile(r"\bпол(?:часа|дня)\b", re.IGNORECASE)
TODAY_RE = re.compile(r"\b(послезавтра|завтра|сегодня)\b")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)")
WORD_DATE_RE = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:{MONTH_ALT})\.?(?!\d)")
WEEKDAY_DATE_RE = re.compile(rf"\b(?:в|во|на|к|с)\s+(?:следующ\w+\s+)?({WEEKDAY_ALT})\b", re.IGNORECASE)
TIME_PREFIXED_RE = re.compile(r"\b(?:в|во|к|до|после)\s+(\d{1,2})[:.](\d{2})(?!\d)")
TIME_BARE_RE = re.compile(r"(?<![\w\d])(\d{1,2})[:.](\d{2})(?![\d:])")
HOUR_ONLY_RE = re.compile(r"\b(\d{1,2})\s*(?:час\w*)\b")


class ParseError(ValueError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def normalize(text: str) -> str:
    lowered = (text or "").strip().lower().replace("\u00a0", " ")
    lowered = lowered.replace("\u0451", "\u0435")
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip(" \t\n\r,;-")


def _cut(source: str, match: re.Match[str]) -> str:
    return source[: match.start()] + " " + source[match.end() :]


def _parse_time(hour: int, minute: int) -> time:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ParseError(
            f"Некорректное время: {hour:02d}:{minute:02d}",
            hint="Время должно быть в формате ЧЧ:ММ, например 18:30.",
        )
    return time(hour=hour, minute=minute)


def _relative_delta(match: re.Match[str]) -> timedelta | None:
    raw_num = (match.group("num") or "").lower()
    unit = (match.group("unit") or "").lower()
    if not raw_num and not unit:
        return None
    if not raw_num:
        seconds = UNIT_SECONDS.get(unit)
        return timedelta(seconds=seconds) if seconds else None
    if raw_num.isdigit():
        count = int(raw_num)
    else:
        count = WORD_NUMBERS.get(raw_num, 0)
    if count <= 0:
        return None
    seconds = UNIT_SECONDS.get(unit) or UNIT_SECONDS.get(raw_num) or 86400
    return timedelta(seconds=seconds * count)


def _extract_relative(source: str) -> tuple[timedelta | None, str]:
    match = HALF_RE.search(source)
    if match:
        seconds = 1800 if match.group(0).startswith("полчаса") else 43200
        return timedelta(seconds=seconds), _cut(source, match)
    match = RELATIVE_RE.search(source)
    if match:
        delta = _relative_delta(match)
        if delta is not None:
            return delta, _cut(source, match)
    return None, source


def _extract_time(source: str) -> tuple[time | None, str]:
    for regex in (TIME_PREFIXED_RE, TIME_BARE_RE):
        match = regex.search(source)
        if match:
            return _parse_time(int(match.group(1)), int(match.group(2))), _cut(source, match)
    match = HOUR_ONLY_RE.search(source)
    if match:
        return _parse_time(int(match.group(1)), 0), _cut(source, match)
    return None, source


def _extract_date(source: str, today: date) -> tuple[date | None, int, bool]:
    match = TODAY_RE.search(source)
    if match:
        offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[match.group(1)]
        return today + timedelta(days=offset), 1, False

    match = ISO_DATE_RE.search(source)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3))), 365, True

    match = NUM_DATE_RE.search(source)
    if match:
        year_raw = match.group(3)
        if year_raw:
            year = 2000 + int(year_raw) if len(year_raw) == 2 else int(year_raw)
        else:
            year = today.year
        return _safe_date(year, int(match.group(2)), int(match.group(1))), 365, bool(year_raw)

    match = WORD_DATE_RE.search(source)
    if match:
        word = re.sub(r"[^a-zа-я]", "", match.group(0)[len(match.group(1)) :])
        month = MONTHS.get(word)
        if month:
            return _safe_date(today.year, month, int(match.group(1))), 365, False

    match = WEEKDAY_DATE_RE.search(source)
    if match:
        target = WEEKDAYS.get(match.group(1).lower())
        if target is not None:
            ahead = (target - today.weekday()) % 7
            return today + timedelta(days=ahead), 7, False

    return None, 1, False


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ParseError(
            f"Такой даты не существует: {day:02d}.{month:02d}",
            hint="Проверь число и месяц, например 25.10 или 25 октября.",
        ) from exc


def _combine(day: date, moment: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, moment).replace(tzinfo=tz)


def parse_when(
    text: str,
    tz: ZoneInfo,
    now: datetime | None = None,
    default_time: time = time(23, 59),
) -> datetime:
    source = normalize(text)
    if not source:
        raise ParseError(
            "Не понял, когда дедлайн.",
            hint="Например: «завтра в 18:00», «через 3 дня», «25.10 в 14:00».",
        )

    local_now = now.astimezone(tz) if now is not None else datetime.now(tz)
    today = local_now.date()

    delta, source = _extract_relative(source)
    moment, source = _extract_time(source)
    day, step, has_year = _extract_date(source, today)

    if delta is not None:
        target = local_now + delta
        if moment is not None:
            target = _combine(target.date(), moment, tz)
        else:
            target = target.replace(second=0, microsecond=0)
        if target <= local_now:
            target += timedelta(days=1)
        return target

    if day is not None:
        target = _combine(day, moment or default_time, tz)
        if not has_year:
            while target <= local_now:
                target = _combine(target.date() + timedelta(days=step), moment or default_time, tz)
        return target

    if moment is not None:
        target = _combine(today, moment, tz)
        if target <= local_now:
            target += timedelta(days=1)
        return target

    raise ParseError(
        "Не нашёл в тексте дату или время.",
        hint="Например: «в 18:00», «завтра», «через 2 недели», «в пятницу», «03.11 в 09:00».",
    )


DATE_START_PATTERNS: tuple[re.Pattern[str], ...] = (
    TODAY_RE,
    RELATIVE_RE,
    HALF_RE,
    ISO_DATE_RE,
    NUM_DATE_RE,
    WORD_DATE_RE,
    WEEKDAY_DATE_RE,
    TIME_PREFIXED_RE,
    TIME_BARE_RE,
    HOUR_ONLY_RE,
)


def split_title_and_when(text: str) -> tuple[str, str]:
    source = (text or "").strip()
    lowered = normalize(source)
    positions = [m.start() for regex in DATE_START_PATTERNS for m in regex.finditer(lowered)]
    if not positions:
        return source, ""
    cut = min(positions)
    title = source[:cut].strip(" ,;:-–—")
    when = source[cut:].strip(" ,;:-–—")
    if not when:
        return source, ""
    return title, when
