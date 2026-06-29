import asyncio
import logging

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.observability.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the Telegram bot polling lifecycle."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_newstock_alert_bot", extra={"environment": settings.app_env})

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings)
    await dispatcher.start_polling(bot, settings=settings)


def run() -> None:
    asyncio.run(main())
