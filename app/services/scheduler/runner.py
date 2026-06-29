import logging
from types import TracebackType

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database.connection import get_session
from app.database.repositories import (
    SqlAlchemyProductPincodeRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyStockHistoryRepository,
    SqlAlchemyUserProductTrackingRepository,
    SqlAlchemyUserRepository,
)
from app.integrations.marketplaces.amazon.adapter import (
    AmazonMarketplaceAdapter,
    PlaywrightBrowserPool,
)
from app.services.notifications.telegram import TelegramNotifier
from app.services.scheduler.jobs import BackgroundStockChecker

logger = logging.getLogger(__name__)
_CHECKERS: dict[int, BackgroundStockChecker] = {}


class SqlAlchemyStockCheckUnitOfWork:
    def __init__(self) -> None:
        self.products: SqlAlchemyProductRepository
        self.pincodes: SqlAlchemyProductPincodeRepository
        self.stock_history: SqlAlchemyStockHistoryRepository
        self.users: SqlAlchemyUserRepository
        self.trackings: SqlAlchemyUserProductTrackingRepository
        self._session_context = get_session()
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyStockCheckUnitOfWork":
        self._session = await self._session_context.__aenter__()
        self.products = SqlAlchemyProductRepository(self._session)
        self.pincodes = SqlAlchemyProductPincodeRepository(self._session)
        self.stock_history = SqlAlchemyStockHistoryRepository(self._session)
        self.users = SqlAlchemyUserRepository(self._session)
        self.trackings = SqlAlchemyUserProductTrackingRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._session_context.__aexit__(exc_type, exc, tb)


def create_stock_checker(settings: Settings, bot: Bot | None = None) -> BackgroundStockChecker:
    browser_pool = PlaywrightBrowserPool(
        headless=settings.browser_headless,
        max_browsers=settings.stock_check_worker_limit,
        launch_timeout_ms=settings.browser_timeout_seconds * 1000,
    )
    amazon_adapter = AmazonMarketplaceAdapter(
        browser_pool=browser_pool,
        headless=settings.browser_headless,
        timeout_ms=settings.browser_timeout_seconds * 1000,
        retries=settings.stock_check_retry_attempts,
    )
    return BackgroundStockChecker(
        uow_factory=lambda: SqlAlchemyStockCheckUnitOfWork(),
        amazon_adapter=amazon_adapter,
        worker_limit=settings.stock_check_worker_limit,
        notifier=TelegramNotifier(bot) if bot is not None else None,
    )


def create_scheduler(settings: Settings, bot: Bot | None = None) -> AsyncIOScheduler:
    checker = create_stock_checker(settings, bot)
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        checker.check_all_active_products,
        IntervalTrigger(seconds=settings.stock_check_interval_seconds),
        id="check_all_active_products",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_listener(_log_scheduler_error)
    _CHECKERS[id(scheduler)] = checker
    return scheduler


def _log_scheduler_error(event: object) -> None:
    exception = getattr(event, "exception", None)
    if exception is not None:
        logger.error("stock_scheduler_job_error", extra={"exception": repr(exception)})


async def start_scheduler(scheduler: AsyncIOScheduler) -> None:
    scheduler.start()
    logger.info("stock_scheduler_started")


async def stop_scheduler(scheduler: AsyncIOScheduler) -> None:
    scheduler.shutdown(wait=True)
    checker = _CHECKERS.pop(id(scheduler), None)
    adapter = getattr(checker, "_amazon_adapter", None)
    close = getattr(adapter, "close", None)
    if close is not None:
        await close()
    logger.info("stock_scheduler_stopped")
