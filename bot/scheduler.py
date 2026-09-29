from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import DEFAULT_REMINDER_OFFSETS
from bot.keyboards import InlineKeyboardButton, InlineKeyboardMarkup
from bot.models import Assignment, User
from bot.services.assignments import find_reminder_due, mark_sent
from bot.services.stats import render_digest
from bot.services.users import sanitize_reminder_offsets
from bot.utils.formatting import (
    countdown_text,
    esc,
    hours_word,
    human_datetime,
    kind_label,
)
from bot.utils.time import to_local, utcnow

log = logging.getLogger(__name__)

TICK_SECONDS = 30
STALE_REMINDER_AFTER = timedelta(hours=12)
DEADLINE_GRACE = timedelta(hours=2)


def reminder_keyboard(assignment: Assignment) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал", callback_data=f"done:{assignment.id}"),
                InlineKeyboardButton(
                    text="➕ День", callback_data=f"postpone:{assignment.id}:1"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➕ Три дня", callback_data=f"postpone:{assignment.id}:3"
                ),
                InlineKeyboardButton(
                    text="➕ Неделя", callback_data=f"postpone:{assignment.id}:7"
                ),
            ],
        ]
    )


async def tick(bot: Bot, session_factory: async_sessionmaker) -> None:
    now = utcnow()
    async with session_factory() as session:
        users = list(await session.scalars(select(User)))
        for user in users:
            await _process_user(bot, session, user, now)
        await session.commit()


async def _process_user(bot: Bot, session, user: User, now: datetime) -> None:
    offsets = sanitize_reminder_offsets(user.reminder_offsets, list(DEFAULT_REMINDER_OFFSETS))
    assignments = [a for a in user.assignments if a.status == "active"]

    for assignment in assignments:
        for offset in find_reminder_due(assignment, offsets, now):
            if not _should_send(assignment, offset, now):
                await mark_sent(session, assignment, offset)
                continue
            await _send_reminder(bot, session, user, assignment, offset)
            await mark_sent(session, assignment, offset)

    if user.digest_enabled:
        await _maybe_send_digest(bot, session, user, assignments, now)


def _should_send(assignment: Assignment, offset: int, now: datetime) -> bool:
    if offset == 0:
        return assignment.deadline <= now <= assignment.deadline + DEADLINE_GRACE
    if assignment.deadline <= now:
        return False
    remind_at = assignment.deadline - timedelta(hours=offset)
    return remind_at >= now - STALE_REMINDER_AFTER


async def _send_reminder(
    bot: Bot, session, user: User, assignment: Assignment, offset: int
) -> None:
    from bot.services.users import user_tz

    tz = user_tz(user)
    local_now = datetime.now(tz)
    local_deadline = to_local(assignment.deadline, tz)
    if offset:
        header = f"⏰ Через {hours_word(offset)} сдача <b>{esc(assignment.title)}</b>"
    else:
        header = f"🚨 Сейчас сдача <b>{esc(assignment.title)}</b>"
    text = (
        f"{header}\n"
        f"Дедлайн: {human_datetime(local_deadline)}\n"
        f"{countdown_text(local_deadline, local_now)} · {kind_label(assignment.kind)}"
    )
    try:
        await bot.send_message(user.tg_id, text, reply_markup=reminder_keyboard(assignment))
    except TelegramForbiddenError:
        log.info("user %s blocked the bot", user.tg_id)
    except Exception:
        log.exception("failed to send reminder to %s", user.tg_id)


async def _maybe_send_digest(
    bot: Bot, session, user: User, assignments: list[Assignment], now: datetime
) -> None:
    from bot.services.users import user_tz

    tz = user_tz(user)
    local_now = to_local(now, tz)
    if local_now.hour != user.digest_hour:
        return
    if user.last_digest_date is not None and user.last_digest_date >= local_now.date():
        return

    text = render_digest(assignments, tz, local_now)
    try:
        await bot.send_message(user.tg_id, text)
    except TelegramForbiddenError:
        return
    except Exception:
        log.exception("failed to send digest to %s", user.tg_id)
        return
    user.last_digest_date = local_now.date()


def start_scheduler(bot: Bot, session_factory: async_sessionmaker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        tick,
        IntervalTrigger(seconds=TICK_SECONDS),
        args=[bot, session_factory],
        id="reminders",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
