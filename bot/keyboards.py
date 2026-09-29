from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models import Assignment


def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить работу", callback_data="menu:add"),
                InlineKeyboardButton(text="📋 Список", callback_data="menu:list"),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
            ],
        ]
    )


def assignment_markup(assignments: list[Assignment]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for assignment in assignments:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{assignment.title[:28]}", callback_data=f"show:{assignment.id}"
                ),
                InlineKeyboardButton(text="✅", callback_data=f"done:{assignment.id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"askdel:{assignment.id}"),
            ]
        )
    if rows:
        rows.append(
            [InlineKeyboardButton(text="🧹 Очистить сделанные", callback_data="bulk:clear")]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data="menu:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def detail_markup(assignment: Assignment) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал", callback_data=f"done:{assignment.id}"),
                InlineKeyboardButton(text="↩️ Назад", callback_data="menu:list"),
            ]
        ]
    )


def settings_markup(digest_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Дайджест: {'включён' if digest_enabled else 'выключен'}",
                    callback_data="toggle:digest",
                )
            ],
            [InlineKeyboardButton(text="🕐 Час дайджеста", callback_data="digest:hour")],
            [InlineKeyboardButton(text="🔔 Интервалы напоминаний", callback_data="remind:menu")],
            [InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="tz:menu")],
        ]
    )
