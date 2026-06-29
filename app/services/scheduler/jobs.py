import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol

from app.domain.entities import Marketplace, Product, StockHistory
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    StockHistoryRepository,
)
from app.integrations.marketplaces.amazon.adapter import AmazonProductSnapshot

logger = logging.getLogger(__name__)


class AmazonProductChecker(Protocol):
    async def check_product(
        self, product_url: str, pincodes: list[str]
    ) -> AmazonProductSnapshot: ...


class StockCheckUnitOfWork(Protocol):
    products: ProductRepository
    pincodes: ProductPincodeRepository
    stock_history: StockHistoryRepository

    async def __aenter__(self) -> "StockCheckUnitOfWork": ...
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class BackgroundStockChecker:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], StockCheckUnitOfWork],
        amazon_adapter: AmazonProductChecker,
        worker_limit: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._amazon_adapter = amazon_adapter
        self._worker_limit = worker_limit

    async def check_all_active_products(self) -> None:
        started = perf_counter()
        async with self._uow_factory() as uow:
            products = await uow.products.list_active_tracked()
        logger.info("stock_scheduler_job_started", extra={"product_count": len(products)})
        semaphore = asyncio.Semaphore(self._worker_limit)
        await asyncio.gather(*(self._check_with_limit(product, semaphore) for product in products))
        duration = perf_counter() - started
        logger.info(
            "stock_scheduler_job_completed",
            extra={"product_count": len(products), "duration_seconds": round(duration, 3)},
        )

    async def _check_with_limit(self, product: Product, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            await self._check_product(product)

    async def _check_product(self, product: Product) -> None:
        if product.id is None:
            logger.error("stock_scheduler_product_missing_id")
            return
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
                return
            if product.marketplace is not Marketplace.AMAZON:
                logger.info(
                    "stock_scheduler_product_skipped",
                    extra={
                        "product_id": product.id,
                        "marketplace": product.marketplace.value,
                        "reason": "unsupported_marketplace",
                    },
                )
                return
            snapshot = await self._amazon_adapter.check_product(product.product_url, pincodes)
            checked_product = replace(
                product,
                product_name=snapshot.product_name or product.product_name,
                current_status=snapshot.current_stock_status,
                last_checked=snapshot.last_checked,
            )
            async with self._uow_factory() as uow:
                await uow.products.update(checked_product)
                await uow.stock_history.record(
                    StockHistory(None, product.id, snapshot.current_stock_status, datetime.now(UTC))
                )
            logger.info(
                "stock_scheduler_product_checked",
                extra={
                    "product_id": product.id,
                    "status": snapshot.current_stock_status.value,
                    "pincode_count": len(pincodes),
                    "duration_seconds": round(perf_counter() - started, 3),
                },
            )
        except Exception as exc:
            logger.exception(
                "stock_scheduler_product_error",
                extra={
                    "product_id": product.id,
                    "error": repr(exc),
                    "duration_seconds": round(perf_counter() - started, 3),
                },
            )
