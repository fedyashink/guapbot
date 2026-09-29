from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.db import close_db, describe_backend, init_db, session_factory
from bot.handlers import assignments, settings, start, stats
from bot.middlewares import DbSessionMiddleware, UserMiddleware
from bot.scheduler import start_scheduler

log = logging.getLogger(__name__)


def build_dispatcher(session_factory=session_factory) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    for event_router in (dp.message, dp.callback_query):
        event_router.middleware(DbSessionMiddleware(session_factory))
        event_router.middleware(UserMiddleware())
    dp.include_router(start.router)
    dp.include_router(assignments.router)
    dp.include_router(stats.router)
    dp.include_router(settings.router)
    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируй .env.example в .env и вставь токен от @BotFather"
        )

    await init_db()
    log.info("БД: %s", describe_backend())
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    scheduler = start_scheduler(bot, session_factory)

    try:
        log.info("Бот запущен")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
