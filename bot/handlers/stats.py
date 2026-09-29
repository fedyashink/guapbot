from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import main_menu_markup
from bot.models import User
from bot.services.assignments import list_assignments
from bot.services.stats import build_stats, render_stats
from bot.services.users import local_now, user_tz
from bot.texts import STAT_EMPTY
from bot.utils.formatting import countdown_text, esc, human_datetime

router = Router(name="stats")


async def show_stats(message: Message, session: AsyncSession, db_user: User) -> None:
    assignments = await list_assignments(session, db_user.id, status=None)
    if not assignments:
        await message.answer(STAT_EMPTY, reply_markup=main_menu_markup())
        return

    tz = user_tz(db_user)
    now = local_now(db_user)
    stats = build_stats(db_user, assignments, tz, now)
    await message.answer(render_stats(stats, now), reply_markup=main_menu_markup())


@router.message(Command("stats"))
@router.message(Command("stat"))
async def cmd_stats(message: Message, session: AsyncSession, db_user: User) -> None:
    await show_stats(message, session, db_user)


@router.message(Command("next"))
async def cmd_next(message: Message, session: AsyncSession, db_user: User) -> None:
    tz = user_tz(db_user)
    now = local_now(db_user)
    active = [a for a in await list_assignments(session, db_user.id, status="active")]
    if not active:
        await message.answer("Активных работ нет 🎉")
        return
    from bot.utils.time import to_local

    upcoming = sorted(active, key=lambda a: a.deadline)[:3]
    lines = ["<b>Ближайшие дедлайны:</b>", ""]
    for assignment in upcoming:
        local = to_local(assignment.deadline, tz)
        lines.append(
            f"• <b>{esc(assignment.title)}</b>\n"
            f"  {human_datetime(local)} · {countdown_text(local, now)}"
        )
    await message.answer("\n".join(lines), reply_markup=main_menu_markup())
