import logging

logger = logging.getLogger(__name__)


async def check_all_active_products() -> None:
    """Run the stock-check schedule without marketplace implementations yet."""
    logger.info("stock_check_job_skipped", extra={"reason": "marketplace_clients_not_implemented"})
