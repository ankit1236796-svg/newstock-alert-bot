import asyncio
import logging

from app.core.config import get_settings
from app.database.connection import close_database, init_database
from app.observability.logging import configure_logging
from app.services.scheduler.runner import create_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Application entrypoint without Telegram command or marketplace implementations."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_newstock_alert_bot", extra={"environment": settings.app_env})

    await init_database(settings.database_url)
    scheduler = create_scheduler(settings)
    scheduler.start()

    try:
        # Placeholder lifecycle loop. Telegram polling/webhook startup will be added later.
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await close_database()


def run() -> None:
    asyncio.run(main())
