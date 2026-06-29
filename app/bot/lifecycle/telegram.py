import logging

from aiogram import Bot
from aiogram.types import BotCommand

from app.core.config import Settings
from app.database.connection import close_database, init_database

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, settings: Settings) -> None:
    logger.info("telegram_bot_startup", extra={"environment": settings.app_env})
    await init_database(settings.database_url)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Register and start the bot"),
            BotCommand(command="help", description="Show available commands"),
            BotCommand(command="add", description="Add products to track"),
            BotCommand(command="pins", description="Save default PIN codes"),
            BotCommand(command="ping", description="Check bot responsiveness"),
        ]
    )


async def on_shutdown(bot: Bot) -> None:
    logger.info("telegram_bot_shutdown")
    await close_database()
    await bot.session.close()
