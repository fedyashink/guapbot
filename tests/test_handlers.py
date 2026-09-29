from __future__ import annotations


import pytest
from aiogram import Dispatcher
from sqlalchemy import select

from bot.main import build_dispatcher
from bot.models import Assignment, User
from tests.fakes import USER_ID, make_bot, make_update, sent_texts


@pytest.fixture(scope="module")
def dispatcher(session_factory) -> Dispatcher:
    return build_dispatcher(session_factory)


@pytest.fixture(autouse=True)
async def clean_state(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    yield


async def feed(dispatcher: Dispatcher, *texts: str) -> list[str]:
    bot, fake = make_bot()
    for index, text in enumerate(texts):
        await dispatcher.feed_update(bot, make_update(text, index + 1))
    await bot.session.close()
    return sent_texts(fake)


async def test_start_registers_user_and_greets(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/start")
    assert any("Я напомню о дедлайнах" in text for text in texts)

    async with session_factory() as session:
        user = await session.scalar(select(User))
        assert user is not None
        assert user.tg_id == USER_ID
        assert user.username == "ivan"


async def test_add_creates_assignment(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Лаба 5 по БД, дедлайн завтра в 18:00")
    assert any("Запомнил" in text for text in texts)

    async with session_factory() as session:
        item = await session.scalar(select(Assignment))
        assert item is not None
        assert item.title == "Лаба 5 по БД, дедлайн"
        assert item.kind == "lab"
        assert item.status == "active"
        assert item.reminded_offsets == []


async def test_list_shows_added_assignment(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Курсовая по статистике 25.10 в 14:00", "/list")
    listing = [text for text in texts if "Курсовая" in text]
    assert listing, texts
    assert "25.10.2026" in listing[-1]


async def test_done_marks_assignment(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Лаба 1 завтра в 18:00", "/done 1")
    assert any("Закрыто" in text for text in texts)

    async with session_factory() as session:
        item = await session.scalar(select(Assignment))
        assert item is not None
        assert item.status == "done"
        assert item.completed_at is not None


async def test_undo_returns_assignment(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Лаба 1 завтра в 18:00", "/done 1", "/undo")
    assert any("Вернул в работу" in text for text in texts)

    async with session_factory() as session:
        item = await session.scalar(select(Assignment))
        assert item is not None
        assert item.status == "active"


async def test_stats_reports_load(dispatcher, session_factory) -> None:
    texts = await feed(
        dispatcher,
        "/add Лаба 1 завтра в 18:00",
        "/add Лаба 2 завтра в 20:00",
        "/add Курсовая завтра в 21:00",
        "/stats",
    )
    summary = [text for text in texts if "Сводка" in text]
    assert summary, texts
    assert "плотно" in summary[-1]
    assert "Активных работ: <b>3</b>" in summary[-1]


async def test_next_lists_closest(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Лаба 1 завтра в 18:00", "/next")
    assert any("Ближайшие дедлайны" in text for text in texts)


async def test_settings_changes_offsets(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/remind 48,12,2", "/settings")
    assert any("Буду напоминать" in text for text in texts)
    settings_text = [text for text in texts if "Настройки" in text]
    assert settings_text
    assert "48, 12, 2" in settings_text[-1]

    async with session_factory() as session:
        user = await session.scalar(select(User))
        assert user is not None
        assert user.reminder_offsets == [48, 12, 2]


async def test_add_without_date_asks_again(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Просто работа без даты")
    assert any("нет даты" in text for text in texts)

    async with session_factory() as session:
        assert list(await session.scalars(select(Assignment))) == []


async def test_add_with_invalid_date_shows_hint(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/add Отчёт 31.02 в 10:00")
    assert any("31.02" in text for text in texts)


async def test_timezone_command_rejects_unknown(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/tz Mars/Olympus")
    assert any("Не знаю зону" in text for text in texts)


async def test_timezone_command_applies(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/tz Asia/Almaty")
    assert any("Asia/Almaty" in text for text in texts)

    async with session_factory() as session:
        user = await session.scalar(select(User))
        assert user is not None
        assert user.timezone == "Asia/Almaty"


async def test_digest_toggle(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/digest off")
    assert any("выключен" in text.lower() for text in texts)

    async with session_factory() as session:
        user = await session.scalar(select(User))
        assert user is not None
        assert user.digest_enabled is False


async def test_help_lists_commands(dispatcher, session_factory) -> None:
    texts = await feed(dispatcher, "/help")
    assert any("/add" in text for text in texts)
