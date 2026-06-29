import logging

from aiogram import Bot
from aiogram.types import BotCommand

from app.core.config import Settings
from app.database.connection import close_database, init_database
from app.services.scheduler.runner import create_scheduler, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)
_stock_scheduler: object | None = None


async def on_startup(bot: Bot, settings: Settings) -> None:
    logger.info("telegram_bot_startup", extra={"environment": settings.app_env})
    await init_database(settings.database_url)
    global _stock_scheduler
    scheduler = create_scheduler(settings, bot)
    _stock_scheduler = scheduler
    await start_scheduler(scheduler)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Register and start the bot"),
            BotCommand(command="help", description="Show available commands"),
            BotCommand(command="add", description="Add products to track"),
            BotCommand(command="pins", description="Save default PIN codes"),
            BotCommand(command="check", description="Run a live product stock check"),
            BotCommand(command="ping", description="Check bot responsiveness"),
        ]
    )


async def on_shutdown(bot: Bot) -> None:
    logger.info("telegram_bot_shutdown")
    global _stock_scheduler
    if _stock_scheduler is not None:
        await stop_scheduler(_stock_scheduler)
        _stock_scheduler = None
    await close_database()
    await bot.session.close()
