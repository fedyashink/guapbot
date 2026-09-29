from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from bot.utils.datetime_parser import (
    ParseError,
    parse_when,
    split_title_and_when,
)

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 9, 29, 14, 30, tzinfo=TZ)

DEFAULT = time(23, 59)


def parse(text: str, now: datetime = NOW) -> datetime:
    return parse_when(text, TZ, now=now, default_time=DEFAULT)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("завтра в 18:00", datetime(2026, 9, 30, 18, 0, tzinfo=TZ)),
        ("сегодня в 23:00", datetime(2026, 9, 29, 23, 0, tzinfo=TZ)),
        ("послезавтра", datetime(2026, 10, 1, 23, 59, tzinfo=TZ)),
        ("завтра", datetime(2026, 9, 30, 23, 59, tzinfo=TZ)),
        ("через 3 дня в 14:30", datetime(2026, 10, 2, 14, 30, tzinfo=TZ)),
        ("через 2 часа", datetime(2026, 9, 29, 16, 30, tzinfo=TZ)),
        ("через 40 минут", datetime(2026, 9, 29, 15, 10, tzinfo=TZ)),
        ("через неделю", datetime(2026, 10, 6, 14, 30, tzinfo=TZ)),
        ("через две недели", datetime(2026, 10, 13, 14, 30, tzinfo=TZ)),
        ("через полчаса", datetime(2026, 9, 29, 15, 0, tzinfo=TZ)),
        ("25.10 в 14:00", datetime(2026, 10, 25, 14, 0, tzinfo=TZ)),
        ("25.10.2026 в 14:00", datetime(2026, 10, 25, 14, 0, tzinfo=TZ)),
        ("2026-10-25 09:00", datetime(2026, 10, 25, 9, 0, tzinfo=TZ)),
        ("25 октября в 14:00", datetime(2026, 10, 25, 14, 0, tzinfo=TZ)),
        ("25 окт 14:00", datetime(2026, 10, 25, 14, 0, tzinfo=TZ)),
        ("в пятницу к 15:00", datetime(2026, 10, 2, 15, 0, tzinfo=TZ)),
        ("в понедельник в 9:00", datetime(2026, 10, 5, 9, 0, tzinfo=TZ)),
        ("18:30", datetime(2026, 9, 29, 18, 30, tzinfo=TZ)),
        ("в 18:00", datetime(2026, 9, 29, 18, 0, tzinfo=TZ)),
        ("к 23:00", datetime(2026, 9, 29, 23, 0, tzinfo=TZ)),
        ("в 3 часа", datetime(2026, 9, 30, 3, 0, tzinfo=TZ)),
    ],
)
def test_parse_when(text: str, expected: datetime) -> None:
    assert parse(text) == expected


def test_time_in_past_rolls_to_tomorrow() -> None:
    assert parse("09:00") == datetime(2026, 9, 30, 9, 0, tzinfo=TZ)


def test_weekday_in_past_rolls_to_next_week() -> None:
    assert parse("в вторник в 09:00") == datetime(2026, 10, 6, 9, 0, tzinfo=TZ)


def test_past_explicit_date_rolls_to_next_year() -> None:
    late = datetime(2026, 12, 1, 9, 0, tzinfo=TZ)
    assert parse("10.10 в 09:00", now=late) == datetime(2027, 10, 10, 9, 0, tzinfo=TZ)


def test_future_explicit_date_uses_current_year() -> None:
    assert parse("10.10 в 09:00") == datetime(2026, 10, 10, 9, 0, tzinfo=TZ)


def test_explicit_year_in_past_is_kept() -> None:
    assert parse("10.10.2026 в 09:00") == datetime(2026, 10, 10, 9, 0, tzinfo=TZ)


def test_yo_is_normalized() -> None:
    assert parse("завтра в 18:00".replace("а", "а")) == parse("ЗАВТРА В 18:00")


def test_invalid_date_raises() -> None:
    with pytest.raises(ParseError):
        parse("31.02 в 09:00")


def test_invalid_time_raises() -> None:
    with pytest.raises(ParseError):
        parse("завтра в 99:00")


def test_missing_date_raises() -> None:
    with pytest.raises(ParseError):
        parse("когда-нибудь потом")


def test_empty_text_raises() -> None:
    with pytest.raises(ParseError):
        parse("   ")


def test_different_timezone_shifts_instant() -> None:
    almaty = ZoneInfo("Asia/Almaty")
    moment = parse_when("завтра в 18:00", TZ, now=NOW, default_time=DEFAULT)
    same = parse_when("завтра в 18:00", almaty, now=NOW, default_time=DEFAULT)
    assert moment != same


@pytest.mark.parametrize(
    ("text", "title", "when"),
    [
        ("Лаба 5 по БД, дедлайн завтра в 18:00", "Лаба 5 по БД, дедлайн", "завтра в 18:00"),
        ("Курсовая 25.10 в 14:00", "Курсовая", "25.10 в 14:00"),
        ("Экзамен по матану завтра", "Экзамен по матану", "завтра"),
        ("Отчёт к понедельнику", "Отчёт к понедельнику", ""),
        ("завтра", "", "завтра"),
    ],
)
def test_split_title_and_when(text: str, title: str, when: str) -> None:
    assert split_title_and_when(text) == (title, when)
