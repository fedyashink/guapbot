from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import assignment_markup, detail_markup, main_menu_markup
from bot.models import User
from bot.services.assignments import (
    create_assignment,
    delete_assignment,
    get_assignment,
    list_assignments,
    local_deadline,
    mark_done,
    postpone,
    reopen,
)
from bot.services.users import local_now, user_tz
from bot.texts import ADD_BAD_DATE, ADD_DONE, ADD_PROMPT, CONFIRM_DELETE, EMPTY_LIST, NOT_FOUND
from bot.utils.datetime_parser import ParseError, parse_when, split_title_and_when
from bot.utils.formatting import countdown_text, esc, human_datetime

router = Router(name="assignments")


class AddDeadline(StatesGroup):
    waiting = State()


def detect_kind(text: str) -> str:
    lowered = (text or "").lower()
    if "лаб" in lowered:
        return "lab"
    if "курс" in lowered:
        return "coursework"
    if "экзам" in lowered or "защит" in lowered:
        return "exam"
    return "other"


async def process_new_assignment(
    message: Message,
    text: str,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    tz = user_tz(db_user)
    title, when_text = split_title_and_when(text)
    if not when_text:
        await message.answer(
            "В сообщении нет даты. Например: <i>Курсовая 25.10 в 14:00</i>\n"
            "Или просто напиши /add и опиши работу двумя словами."
        )
        return

    try:
        deadline = parse_when(when_text, tz)
    except ParseError as exc:
        hint = exc.hint or "Например: «завтра в 18:00» или «через 3 дня»."
        await message.answer(ADD_BAD_DATE.format(reason=exc.message, hint=hint))
        return

    assignment = await create_assignment(
        session=session,
        user_id=db_user.id,
        title=title or "Без названия",
        deadline_local=deadline,
        tz=tz,
        kind=detect_kind(title),
    )
    await state.clear()

    await message.answer(
        ADD_DONE.format(
            title=esc(assignment.title),
            when=human_datetime(deadline),
            left=countdown_text(deadline, local_now(db_user)),
        ),
        reply_markup=main_menu_markup(),
    )


@router.message(Command("add"))
@router.message(Command("a"))
async def cmd_add(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await process_new_assignment(message, parts[1], state, session, db_user)
        return
    await state.set_state(AddDeadline.waiting)
    await message.answer(ADD_PROMPT)


@router.message(AddDeadline.waiting)
async def on_add_text(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    await process_new_assignment(message, message.text, state, session, db_user)


@router.message(Command("list"))
@router.message(Command("l"))
async def cmd_list(message: Message, session: AsyncSession, db_user: User) -> None:
    await render_and_send_list(message, session, db_user)


async def render_and_send_list(message: Message, session: AsyncSession, db_user: User) -> None:
    tz = user_tz(db_user)
    now = local_now(db_user)
    active = await list_assignments(session, db_user.id, status="active")

    if not active:
        await message.answer(EMPTY_LIST, reply_markup=main_menu_markup())
        return

    lines = ["<b>Что горит:</b>", ""]
    for assignment in active:
        local = local_deadline(assignment, tz)
        if local < now:
            flag = "🔴"
        elif local - now <= timedelta(hours=24):
            flag = "🟡"
        else:
            flag = "⚪️"
        lines.append(
            f"{flag} <b>{esc(assignment.title)}</b>\n"
            f"    {human_datetime(local)} · {countdown_text(local, now)}"
        )

    done = await list_assignments(session, db_user.id, status="done")
    if done:
        lines.append("")
        lines.append(f"<i>Сделано: {len(done)}</i>")

    await message.answer("\n".join(lines), reply_markup=assignment_markup(active))


@router.message(Command("done"))
async def cmd_done(message: Message, session: AsyncSession, db_user: User) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажи номер или часть названия: <code>/done 2</code> или <code>/done БД</code>"
        )
        return
    await _complete_by_query(message, session, db_user, parts[1])


async def _complete_by_query(
    message: Message, session: AsyncSession, db_user: User, query: str
) -> None:
    items = await list_assignments(session, db_user.id, status="active")
    if not items:
        await message.answer(EMPTY_LIST)
        return

    query = query.strip()
    if query.isdigit():
        index = int(query) - 1
        if not 0 <= index < len(items):
            await message.answer("Нет такой позиции в списке.")
            return
        target = items[index]
    else:
        matches = [a for a in items if query.lower() in a.title.lower()]
        if not matches:
            await message.answer(NOT_FOUND)
            return
        if len(matches) > 1:
            listing = "\n".join(f"{i + 1}. {esc(a.title)}" for i, a in enumerate(matches))
            await message.answer(f"Подходит несколько:\n{listing}\nУточни номер: <code>/done 1</code>")
            return
        target = matches[0]

    await mark_done(session, target)
    await message.answer(f"✅ Закрыто: <b>{esc(target.title)}</b> Так держать!")


@router.message(Command("undo"))
async def cmd_undo(message: Message, session: AsyncSession, db_user: User) -> None:
    done = await list_assignments(session, db_user.id, status="done")
    if not done:
        await message.answer("Нечего отменять — ты пока ничего не отмечал.")
        return
    target = done[-1]
    await reopen(session, target)
    await message.answer(f"Вернул в работу: <b>{esc(target.title)}</b>")


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    assignment = await get_assignment(session, int(callback.data.split(":")[1]), db_user.id)
    if assignment is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    await mark_done(session, assignment)
    await callback.answer("Закрыто ✅")
    await callback.message.edit_text(
        f"✅ <b>{esc(assignment.title)}</b> — сделано. Молодец!",
        reply_markup=main_menu_markup(),
    )


@router.callback_query(F.data.startswith("show:"))
async def cb_show(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    assignment = await get_assignment(session, int(callback.data.split(":")[1]), db_user.id)
    if assignment is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    tz = user_tz(db_user)
    now = local_now(db_user)
    local = local_deadline(assignment, tz)
    await callback.answer()
    await callback.message.answer(
        f"<b>{esc(assignment.title)}</b>\n"
        f"Дедлайн: {human_datetime(local)}\n"
        f"{countdown_text(local, now)}",
        reply_markup=detail_markup(assignment),
    )


@router.callback_query(F.data.startswith("postpone:"))
async def cb_postpone(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, assignment_id, days = callback.data.split(":")
    assignment = await get_assignment(session, int(assignment_id), db_user.id)
    if assignment is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    tz = user_tz(db_user)
    new_local = local_deadline(assignment, tz) + timedelta(days=int(days))
    await postpone(session, assignment, new_local, tz)
    await callback.answer("Перенёс")
    await callback.message.edit_text(
        f"Сдвинул на {days} дн.\n<b>{esc(assignment.title)}</b> → {human_datetime(new_local)}",
        reply_markup=main_menu_markup(),
    )


@router.callback_query(F.data.startswith("askdel:"))
async def cb_ask_delete(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    assignment_id = int(callback.data.split(":")[1])
    assignment = await get_assignment(session, assignment_id, db_user.id)
    if assignment is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        CONFIRM_DELETE.format(title=esc(assignment.title)),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"del:{assignment_id}"),
                    InlineKeyboardButton(text="Отмена", callback_data="menu:list"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    assignment = await get_assignment(session, int(callback.data.split(":")[1]), db_user.id)
    if assignment is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    title = assignment.title
    await delete_assignment(session, assignment)
    await callback.answer("Удалено")
    await callback.message.edit_text(
        f"🗑 Удалено: <b>{esc(title)}</b>", reply_markup=main_menu_markup()
    )


@router.callback_query(F.data == "bulk:clear")
async def cb_bulk_clear(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    done = await list_assignments(session, db_user.id, status="done")
    for assignment in done:
        await delete_assignment(session, assignment)
    await callback.answer("Очищено")
    await render_and_send_list(callback.message, session, db_user)


@router.callback_query(F.data == "bulk:done")
async def cb_bulk_done(callback: CallbackQuery) -> None:
    await callback.answer("Отмечай кнопками ✅ у каждой работы")
