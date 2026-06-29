import logging

from aiogram import Bot

from app.services.notifications.notifier import Notifier

logger = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    """aiogram-backed notifier for outbound stock alerts."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_stock_alert(self, telegram_user_id: int, message: str) -> None:
        await self._bot.send_message(chat_id=telegram_user_id, text=message)
        logger.info("telegram_alert_sent", extra={"telegram_user_id": telegram_user_id})
