from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User as TgUser

CHAT_ID = 555
USER_ID = 1001


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[TelegramMethod] = []

    async def __call__(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):
        self.calls.append(method)
        return self._build(method)

    async def close(self) -> None:
        return None

    def _build(self, method: TelegramMethod) -> Any:
        return_value = getattr(method, "return_value", None)
        if return_value is Message:
            return Message(
                message_id=len(self.calls),
                date=datetime.now(),
                chat=Chat(id=CHAT_ID, type="private"),
                text=getattr(method, "text", None),
            )
        if return_value is bool or return_value is None:
            return True
        return return_value()


def make_bot() -> tuple[Bot, FakeSession]:
    fake = FakeSession()
    return Bot(token=f"{USER_ID}:TESTTOKEN", session=fake), fake


def make_update(text: str, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(),
            chat=Chat(id=CHAT_ID, type="private"),
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Иван", username="ivan"),
            text=text,
        ),
    )


def sent_texts(fake: FakeSession) -> list[str]:
    return [call.text for call in fake.calls if getattr(call, "text", None)]
