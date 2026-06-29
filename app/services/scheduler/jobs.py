import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol

from app.domain.entities import Marketplace, Product, StockHistory
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    StockHistoryRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.integrations.marketplaces.amazon.adapter import AmazonProductSnapshot
from app.services.notifications.alerts import TelegramAlertService
from app.services.notifications.notifier import Notifier

logger = logging.getLogger(__name__)


class AmazonProductChecker(Protocol):
    async def check_product(
        self, product_url: str, pincodes: list[str]
    ) -> AmazonProductSnapshot: ...


class StockCheckUnitOfWork(Protocol):
    products: ProductRepository
    pincodes: ProductPincodeRepository
    stock_history: StockHistoryRepository
    users: UserRepository
    trackings: UserProductTrackingRepository

    async def __aenter__(self) -> "StockCheckUnitOfWork": ...
    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object
    ) -> None: ...


class BackgroundStockChecker:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], Any],
        amazon_adapter: AmazonProductChecker,
        worker_limit: int,
        notifier: Notifier | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._amazon_adapter = amazon_adapter
        self._worker_limit = worker_limit
        self._notifier = notifier

    async def check_all_active_products(self) -> None:
        started = perf_counter()
        async with self._uow_factory() as uow:
            products = await uow.products.list_active_tracked()
        logger.info("stock_scheduler_job_started", extra={"product_count": len(products)})
        semaphore = asyncio.Semaphore(self._worker_limit)
        durations = await asyncio.gather(
            *(self._check_with_limit(product, semaphore) for product in products),
            return_exceptions=True,
        )
        successful_durations = [duration for duration in durations if isinstance(duration, float)]
        duration = perf_counter() - started
        average_duration = (
            sum(successful_durations) / len(successful_durations) if successful_durations else 0.0
        )
        logger.info(
            "stock_scheduler_job_completed",
            extra={
                "product_count": len(products),
                "duration_seconds": round(duration, 3),
                "average_check_duration_seconds": round(average_duration, 3),
            },
        )

    async def _check_with_limit(
        self, product: Product, semaphore: asyncio.Semaphore
    ) -> float | None:
        async with semaphore:
            return await self._check_product(product)

    async def _check_product(self, product: Product) -> float | None:
        if product.id is None:
            logger.error("stock_scheduler_product_missing_id")
            return None
        started = perf_counter()
        try:
            async with self._uow_factory() as uow:
                pincode_entities = await uow.pincodes.list_for_product(product.id)
            pincodes = [pin.pincode for pin in pincode_entities]
            if not pincodes:
                logger.info(
                    "stock_scheduler_product_skipped",
                    extra={"product_id": product.id, "reason": "no_pincodes"},
                )
                return None
            if product.marketplace is not Marketplace.AMAZON:
                logger.info(
                    "stock_scheduler_product_skipped",
                    extra={
                        "product_id": product.id,
                        "marketplace": product.marketplace.value,
                        "reason": "unsupported_marketplace",
                    },
                )
                return None
            snapshot = await self._amazon_adapter.check_product(product.product_url, pincodes)
            checked_product = replace(
                product,
                product_name=snapshot.product_name or product.product_name,
                current_status=snapshot.current_stock_status,
                last_checked=snapshot.last_checked,
                current_price_paise=snapshot.current_price_paise,
                delivery_availability_by_pincode={
                    delivery.pincode: delivery.is_available
                    for delivery in snapshot.delivery_availability
                },
            )
            async with self._uow_factory() as uow:
                if self._notifier is not None:
                    alert_service = TelegramAlertService(
                        notifier=self._notifier,
                        user_repository=uow.users,
                        tracking_repository=uow.trackings,
                    )
                    await alert_service.notify_product_changes(
                        previous=product, current=checked_product, snapshot=snapshot
                    )
                await uow.products.update(checked_product)
                await uow.stock_history.record(
                    StockHistory(None, product.id, snapshot.current_stock_status, datetime.now(UTC))
                )
            duration = perf_counter() - started
            logger.info(
                "stock_scheduler_product_checked",
                extra={
                    "product_id": product.id,
                    "status": snapshot.current_stock_status.value,
                    "pincode_count": len(pincodes),
                    "duration_seconds": round(duration, 3),
                },
            )
            return duration
        except Exception as exc:
            logger.exception(
                "stock_scheduler_product_error",
                extra={
                    "product_id": product.id,
                    "error": repr(exc),
                    "duration_seconds": round(perf_counter() - started, 3),
                },
            )
            return None
