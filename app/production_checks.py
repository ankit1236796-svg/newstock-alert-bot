import logging
from pathlib import Path

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.core.config import Settings
from app.database.connection import get_session

logger = logging.getLogger(__name__)


async def verify_database() -> None:
    """Verify the configured database accepts a simple query."""
    async with get_session() as session:
        await session.execute(text("SELECT 1"))
    logger.info("startup_check_database_ok")


def verify_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Verify the stock-check scheduler has the expected job registered."""
    job = scheduler.get_job("check_all_active_products")
    if job is None:
        raise RuntimeError("stock-check scheduler job is not registered")
    logger.info("startup_check_scheduler_ok", extra={"job_id": job.id})


def verify_browser_pool(settings: Settings) -> None:
    """Verify browser pool settings and installed Chromium browser path."""
    if settings.browser_pool_size < 1:
        raise RuntimeError("browser pool size must be at least 1")
    browser_root = Path("/ms-playwright")
    if settings.app_env == "production" and not browser_root.exists():
        raise RuntimeError("Playwright browser directory is missing")
    logger.info("startup_check_browser_pool_ok", extra={"pool_size": settings.browser_pool_size})


async def verify_telegram_bot(bot: Bot) -> None:
    """Verify the Telegram token by loading the bot identity."""
    me = await bot.get_me()
    logger.info("startup_check_telegram_bot_ok", extra={"bot_username": me.username})
