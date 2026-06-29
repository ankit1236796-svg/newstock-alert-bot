import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    """Log high-level update handling details without message contents."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        if isinstance(event, Message):
            logger.info(
                "telegram_message_received",
                extra={
                    "telegram_user_id": event.from_user.id if event.from_user else None,
                    "chat_id": event.chat.id,
                },
            )
        return await handler(event, data)
