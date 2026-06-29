from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.services.scheduler.jobs import check_all_active_products


def create_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        check_all_active_products,
        IntervalTrigger(seconds=settings.stock_check_interval_seconds),
        id="check_all_active_products",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
