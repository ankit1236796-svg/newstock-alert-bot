import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.domain.entities import Marketplace, Product, StockStatus, User
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
)
from app.integrations.marketplaces.amazon.adapter import AmazonProductSnapshot

logger = logging.getLogger(__name__)


class AmazonProductChecker(Protocol):
    async def check_product(
        self, product_url: str, pincodes: list[str]
    ) -> AmazonProductSnapshot: ...


class ProductCheckError(Exception):
    """Raised when a user-requested product check cannot be completed."""


@dataclass(frozen=True, slots=True)
class ProductCheckResult:
    product: Product
    pincodes: list[str]
    snapshot: AmazonProductSnapshot


class CheckProductService:
    def __init__(
        self,
        product_repository: ProductRepository,
        pincode_repository: ProductPincodeRepository,
        tracking_repository: UserProductTrackingRepository,
    ) -> None:
        self._products = product_repository
        self._pincodes = pincode_repository
        self._trackings = tracking_repository

    async def check_amazon_product(
        self, user: User, product_id: int, adapter: AmazonProductChecker
    ) -> ProductCheckResult:
        if user.id is None:
            raise ProductCheckError("User must be registered before checking products")

        product = await self._products.get(product_id)
        if product is None:
            raise ProductCheckError("Product was not found")
        if product.id is None:
            raise ProductCheckError("Product is missing its database id")
        if product.marketplace is not Marketplace.AMAZON:
            raise ProductCheckError("Live /check is currently available for Amazon products only")

        tracking = await self._trackings.get(user.id, product.id)
        if tracking is None:
            raise ProductCheckError("Product is not tracked by this user")

        pincode_entities = await self._pincodes.list_for_product(product.id)
        pincodes = [pin.pincode for pin in pincode_entities]
        if not pincodes:
            raise ProductCheckError("No PIN codes are configured for this product")

        logger.info(
            "manual_product_check_started",
            extra={"user_id": user.id, "product_id": product.id, "pincodes": pincodes},
        )
        snapshot = await adapter.check_product(product.product_url, pincodes)
        logger.info(
            "manual_product_check_completed",
            extra={
                "user_id": user.id,
                "product_id": product.id,
                "status": snapshot.current_stock_status.value,
                "checked_pincodes": len(snapshot.delivery_availability),
            },
        )
        return ProductCheckResult(product, pincodes, snapshot)


def display_marketplace(marketplace: Marketplace) -> str:
    return marketplace.value.title()


def display_status(status: StockStatus) -> str:
    return status.value.replace("_", " ").title()


def format_price(price_paise: int | None) -> str:
    if price_paise is None:
        return "Not available"
    rupees = price_paise / 100
    if price_paise % 100 == 0:
        return f"₹{int(rupees):,}"
    return f"₹{rupees:,.2f}"


def format_checked_timestamp(checked_at: datetime) -> str:
    if checked_at.tzinfo is not None:
        checked_at = checked_at.astimezone(UTC).replace(tzinfo=None)
    return checked_at.strftime("%Y-%m-%d %H:%M")
