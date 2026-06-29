from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.lifecycle import on_shutdown, on_startup
from app.bot.middlewares import DatabaseSessionMiddleware, UpdateLoggingMiddleware
from app.bot.routers import build_router
from app.core.config import Settings


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    dispatcher = Dispatcher(settings=settings)
    dispatcher.update.outer_middleware(UpdateLoggingMiddleware())
    dispatcher.update.middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(build_router())
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    return dispatcher
