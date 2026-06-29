from aiogram import Bot, Dispatcher

from app.core.config import Settings


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.telegram_bot_token)


def create_dispatcher() -> Dispatcher:
    # Command routers will be included here in a later iteration.
    return Dispatcher()
