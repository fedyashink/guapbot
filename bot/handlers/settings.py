from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import DEFAULT_REMINDER_OFFSETS, resolve_timezone
from bot.keyboards import settings_markup
from bot.models import User
from bot.services.users import sanitize_reminder_offsets
from bot.utils.formatting import esc, hours_word

router = Router(name="settings")

SUGGESTED_OFFSETS = (720, 168, 72, 24, 6, 1)

COMMON_TIMEZONES = (
    "Europe/Kaliningrad",
    "Europe/Moscow",
    "Europe/Samara",
    "Asia/Yekaterinburg",
    "Asia/Omsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
    "Asia/Magadan",
    "Asia/Kamchatka",
    "Europe/London",
    "Asia/Almaty",
    "Asia/Tashkent",
)


class SettingsFlow(StatesGroup):
    waiting_offsets = State()
    waiting_timezone = State()
    waiting_digest_hour = State()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db_user: User) -> None:
    await show_settings(message, db_user)


async def show_settings(message: Message, db_user: User) -> None:
    offsets = db_user.reminder_offsets or list(DEFAULT_REMINDER_OFFSETS)
    intervals = ", ".join(str(value) for value in offsets)
    digest = "включён" if db_user.digest_enabled else "выключен"
    await message.answer(
        "<b>⚙️ Настройки</b>\n\n"
        f"Часовой пояс: <b>{esc(db_user.timezone)}</b>\n"
        f"Напоминать за (часов): <b>{intervals}</b>\n"
        f"Утренний дайджест: <b>{digest}</b>"
        + (f" в {db_user.digest_hour:02d}:00" if db_user.digest_enabled else "")
        + "\n\n"
        "Команда <code>/remind 24,6,1</code> меняет интервалы,\n"
        "<code>/tz Europe/Moscow</code> — часовой пояс,\n"
        "<code>/digest 8</code> — час утренней сводки.",
        reply_markup=settings_markup(db_user.digest_enabled),
    )


@router.message(Command("remind"))
async def cmd_remind(message: Message, db_user: User) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажи интервалы в часах через запятую: <code>/remind 48,24,6,1</code>\n"
            "0 означает «напомнить ровно в момент дедлайна»."
        )
        return
    await _apply_offsets(message, db_user, parts[1])


@router.message(Command("tz"))
async def cmd_tz(message: Message, db_user: User) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажи часовой пояс: <code>/tz Europe/Kazan</code>\n"
            "Примеры: " + ", ".join(f"<code>{tz}</code>" for tz in COMMON_TIMEZONES[:5]) + " и другие."
        )
        return
    await _apply_timezone(message, db_user, parts[1])


@router.message(Command("digest"))
async def cmd_digest(message: Message, db_user: User) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"Дайджест сейчас {'включён' if db_user.digest_enabled else 'выключен'} "
            f"в {db_user.digest_hour:02d}:00.\n"
            "Включить/выключить: <code>/digest on</code> · <code>/digest off</code>\n"
            "Сменить час: <code>/digest 10</code>"
        )
        return
    value = parts[1].strip().lower()
    if value in {"on", "вкл", "да", "1", "true"}:
        db_user.digest_enabled = True
        await message.answer("Дайджест включён ✅")
        return
    if value in {"off", "выкл", "нет", "0", "false"}:
        db_user.digest_enabled = False
        await message.answer("Дайджест выключен")
        return
    await _apply_digest_hour(message, db_user, value)


async def _apply_offsets(message: Message, db_user: User, raw: str) -> None:
    chunks = [chunk for chunk in raw.replace(" ", "").split(",") if chunk]
    values: list[int] = []
    for chunk in chunks:
        try:
            values.append(int(chunk))
        except ValueError:
            await message.answer(f"Не понимаю «{chunk}». Нужны числа в часах: <code>/remind 24,6,1</code>")
            return
    cleaned = sanitize_reminder_offsets(values)
    if not cleaned:
        await message.answer("Список пуст. Например: <code>/remind 24,6,1</code>")
        return
    db_user.reminder_offsets = cleaned
    await message.answer(
        "Буду напоминать за " + ", ".join(hours_word(v) if v else "ровно в дедлайн" for v in cleaned)
    )


async def _apply_timezone(message: Message, db_user: User, raw: str) -> None:
    candidate = raw.strip().replace(" ", "_")
    tz = resolve_timezone(candidate)
    if tz.key != candidate:
        await message.answer(
            f"Не знаю зону «{candidate}». Попробуй /tz Europe/Moscow или /tz Asia/Almaty"
        )
        return
    db_user.timezone = tz.key
    await message.answer(f"Часовой пояс: <b>{esc(tz.key)}</b> — дедлайны теперь считаю в нём.")


async def _apply_digest_hour(message: Message, db_user: User, raw: str) -> None:
    if not raw.isdigit() or not 0 <= int(raw) <= 23:
        await message.answer("Час должен быть числом от 0 до 23: <code>/digest 9</code>")
        return
    db_user.digest_hour = int(raw)
    db_user.digest_enabled = True
    await message.answer(f"Буду слать сводку в {int(raw):02d}:00")


@router.callback_query(F.data == "toggle:digest")
async def cb_toggle_digest(callback: CallbackQuery, db_user: User) -> None:
    db_user.digest_enabled = not db_user.digest_enabled
    await callback.answer("Включён" if db_user.digest_enabled else "Выключен")
    await show_settings(callback.message, db_user)


@router.callback_query(F.data == "digest:hour")
async def cb_ask_digest_hour(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SettingsFlow.waiting_digest_hour)
    await callback.message.answer("Напиши час для сводки (0–23), например <code>9</code>")


@router.callback_query(F.data == "remind:menu")
async def cb_remind_menu(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await callback.answer()
    await state.set_state(SettingsFlow.waiting_offsets)
    rows = [
        [
            InlineKeyboardButton(text=hours_word(value) if value else "в дедлайн", callback_data=f"preset:{value}")
        ]
        for value in SUGGESTED_OFFSETS
    ]
    rows.append([InlineKeyboardButton(text=f"Мои: {', '.join(str(v) for v in (db_user.reminder_offsets or []))}", callback_data="noop")])
    await callback.message.answer(
        "Выбери частый пресет или напиши свои интервалы: <code>24, 6, 1</code>\n"
        "Часы означают «за сколько часов до дедлайна напомнить».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("preset:"))
async def cb_apply_preset(callback: CallbackQuery, db_user: User) -> None:
    value = int(callback.data.split(":")[1])
    cleaned = sanitize_reminder_offsets([value])
    if not cleaned:
        await callback.answer("Не выбрано", show_alert=True)
        return
    db_user.reminder_offsets = cleaned
    await callback.answer("Готово")
    await show_settings(callback.message, db_user)


@router.callback_query(F.data == "tz:menu")
async def cb_tz_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SettingsFlow.waiting_timezone)
    rows = [
        [InlineKeyboardButton(text=tz, callback_data=f"settz:{tz}")]
        for tz in COMMON_TIMEZONES
    ]
    await callback.message.answer(
        "Выбери свой пояс или напиши его текстом (например <code>Europe/Kazan</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("settz:"))
async def cb_apply_tz(callback: CallbackQuery, db_user: User) -> None:
    key = callback.data.split(":", 1)[1]
    db_user.timezone = key
    await callback.answer("Готово")
    await show_settings(callback.message, db_user)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(SettingsFlow.waiting_offsets)
async def on_offsets_text(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _apply_offsets(message, db_user, message.text)


@router.message(SettingsFlow.waiting_timezone)
async def on_timezone_text(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _apply_timezone(message, db_user, message.text)


@router.message(SettingsFlow.waiting_digest_hour)
async def on_digest_hour_text(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _apply_digest_hour(message, db_user, message.text)
