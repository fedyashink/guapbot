from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import main_menu_markup
from bot.texts import HELP, WELCOME

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = message.from_user.first_name or "друг"
    await message.answer(WELCOME.format(name=name), reply_markup=main_menu_markup())


@router.message(Command("help"))
@router.message(Command("h"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu_markup())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, отменил. Начнём заново — просто напиши /add")


@router.callback_query(F.data.startswith("menu:"))
async def menu_navigation(callback: CallbackQuery, state: FSMContext, db_user, session) -> None:
    from bot.handlers.assignments import AddDeadline, render_and_send_list
    from bot.handlers.settings import show_settings
    from bot.handlers.stats import show_stats

    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "add":
        await state.set_state(AddDeadline.waiting)
        await callback.message.answer(
            "Опиши работу: <i>название + дедлайн</i>\n"
            "Например: <i>Лаба 3 по ОС в четверг в 18:00</i>"
        )
    elif action == "list":
        await render_and_send_list(callback.message, session, db_user)
    elif action == "stats":
        await show_stats(callback.message, session, db_user)
    elif action == "settings":
        await show_settings(callback.message, db_user)
    else:
        await callback.message.answer("Не понимаю, куда идти. Напиши /help")
