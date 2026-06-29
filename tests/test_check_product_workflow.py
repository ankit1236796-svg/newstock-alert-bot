import asyncio
from datetime import UTC, datetime

import pytest

from app.bot.routers.check_product import format_check_result
from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockStatus,
    User,
    UserProductTracking,
)
from app.integrations.marketplaces.amazon.adapter import (
    AmazonDeliveryAvailability,
    AmazonProductSnapshot,
)
from app.services.products.check_product import (
    CheckProductService,
    ProductCheckError,
    ProductCheckResult,
    format_price,
)
from tests.test_list_products_workflow import (
    InMemoryPincodeRepository,
    InMemoryProductRepository,
    InMemoryTrackingRepository,
)


class FakeAmazonAdapter:
    def __init__(self, snapshot: AmazonProductSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, list[str]]] = []

    async def check_product(self, product_url: str, pincodes: list[str]) -> AmazonProductSnapshot:
        self.calls.append((product_url, pincodes))
        return self.snapshot


def test_check_product_service_checks_every_configured_pin() -> None:
    asyncio.run(_run_check_product_service_checks_every_configured_pin())


async def _run_check_product_service_checks_every_configured_pin() -> None:
    products = InMemoryProductRepository()
    pincodes = InMemoryPincodeRepository()
    trackings = InMemoryTrackingRepository()
    service = CheckProductService(products, pincodes, trackings)
    user = User(1, 123, "alice", "Alice")
    product = await products.create(
        Product(
            None,
            "ASIN",
            Marketplace.AMAZON,
            "https://amazon.in/dp/ASIN123456",
            "PS5",
            StockStatus.UNKNOWN,
        )
    )
    assert product.id is not None
    await pincodes.add(ProductPincode(None, product.id, "110001"))
    await pincodes.add(ProductPincode(None, product.id, "132001"))
    await trackings.create(UserProductTracking(None, user.id or 0, product.id))
    snapshot = AmazonProductSnapshot(
        "Sony PS5 Slim",
        Marketplace.AMAZON,
        "ASIN",
        None,
        "Amazon Retail",
        5499000,
        StockStatus.IN_STOCK,
        (
            AmazonDeliveryAvailability("110001", True),
            AmazonDeliveryAvailability("132001", False),
        ),
        datetime(2026, 7, 1, 11, 22, tzinfo=UTC),
    )
    adapter = FakeAmazonAdapter(snapshot)

    result = await service.check_amazon_product(user, product.id, adapter)

    assert result.snapshot == snapshot
    assert adapter.calls == [(product.product_url, ["110001", "132001"])]


def test_check_product_service_rejects_untracked_product() -> None:
    asyncio.run(_run_check_product_service_rejects_untracked_product())


async def _run_check_product_service_rejects_untracked_product() -> None:
    products = InMemoryProductRepository()
    service = CheckProductService(
        products, InMemoryPincodeRepository(), InMemoryTrackingRepository()
    )
    user = User(1, 123, "alice", "Alice")
    product = await products.create(
        Product(
            None,
            "ASIN",
            Marketplace.AMAZON,
            "https://amazon.in/dp/ASIN123456",
            "PS5",
            StockStatus.UNKNOWN,
        )
    )
    assert product.id is not None

    with pytest.raises(ProductCheckError, match="not tracked"):
        await service.check_amazon_product(user, product.id, FakeAmazonAdapter(_snapshot()))


def test_format_check_result_includes_live_details() -> None:
    product = Product(
        1,
        "ASIN",
        Marketplace.AMAZON,
        "https://amazon.in/dp/ASIN123456",
        "PS5",
        StockStatus.UNKNOWN,
    )
    result = ProductCheckResult(product, ["110001", "110045"], _snapshot())

    message = format_check_result(result)

    assert "🟢 Amazon" in message
    assert "Sony PS5 Slim" in message
    assert "In Stock" in message
    assert "₹54,990" in message
    assert "Seller:\nAmazon Retail" in message
    assert "110001 ✅ Available" in message
    assert "110045 ❌ Not Deliverable" in message
    assert "2026-07-01 11:22" in message


def test_format_price_handles_missing_and_decimal_prices() -> None:
    assert format_price(None) == "Not available"
    assert format_price(123456) == "₹1,234.56"


def _snapshot() -> AmazonProductSnapshot:
    return AmazonProductSnapshot(
        "Sony PS5 Slim",
        Marketplace.AMAZON,
        "ASIN",
        None,
        "Amazon Retail",
        5499000,
        StockStatus.IN_STOCK,
        (
            AmazonDeliveryAvailability("110001", True),
            AmazonDeliveryAvailability("110045", False),
        ),
        datetime(2026, 7, 1, 11, 22, tzinfo=UTC),
    )
