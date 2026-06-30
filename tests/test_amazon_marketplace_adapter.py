import asyncio
from collections.abc import Iterable
from datetime import datetime

import pytest

from app.domain.entities import Marketplace, StockStatus
from app.integrations.marketplaces.amazon.adapter import (
    AmazonDeliveryAvailability,
    AmazonMarketplaceAdapter,
    AmazonProductSnapshot,
)


def test_amazon_adapter_declares_marketplace() -> None:
    assert AmazonMarketplaceAdapter.marketplace is Marketplace.AMAZON


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.amazon.in/dp/B0ABCDEF12", "B0ABCDEF12"),
        ("https://www.amazon.in/gp/product/b0abcdef12?th=1", "B0ABCDEF12"),
        ("https://amzn.in/d/B0ABCDEF12", None),
    ],
)
def test_extracts_asin_from_supported_product_urls(url: str, expected: str | None) -> None:
    assert AmazonMarketplaceAdapter._product_id(url) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Deal Price: ₹1,234.56", 123456),
        ("INR 99", 9900),
        ("Rs. 2,499", 249900),
        ("No price", None),
    ],
)
def test_parses_indian_price_to_paise(text: str, expected: int | None) -> None:
    assert AmazonMarketplaceAdapter._parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In stock. Add to Cart", StockStatus.IN_STOCK),
        ("Temporarily out of stock", StockStatus.TEMPORARILY_UNAVAILABLE),
        ("Temporarily unavailable", StockStatus.TEMPORARILY_UNAVAILABLE),
        ("Currently unavailable", StockStatus.CURRENTLY_UNAVAILABLE),
        ("Currently unavailable. Add to Cart", StockStatus.CURRENTLY_UNAVAILABLE),
        ("Only 2 left in stock - order soon.", StockStatus.IN_STOCK),
        ("Something unexpected", StockStatus.UNKNOWN),
    ],
)
def test_maps_amazon_stock_copy_to_stock_status(text: str, expected: StockStatus) -> None:
    assert AmazonMarketplaceAdapter._stock_status(text) is expected


def test_delivery_unavailable_detection() -> None:
    assert AmazonMarketplaceAdapter._delivery_unavailable(
        "This item cannot be shipped to your location"
    )
    assert not AmazonMarketplaceAdapter._delivery_unavailable("FREE delivery by tomorrow")


def test_check_stock_uses_snapshot_for_base_marketplace_contract() -> None:
    async def run_check() -> None:
        class StubAmazonAdapter(AmazonMarketplaceAdapter):
            async def check_product(
                self, product_url: str, pincodes: Iterable[str]
            ) -> AmazonProductSnapshot:
                assert product_url == "https://www.amazon.in/dp/B0ABCDEF12"
                assert list(pincodes) == ["560001"]
                return AmazonProductSnapshot(
                    product_name="Test Product",
                    marketplace=Marketplace.AMAZON,
                    product_id="B0ABCDEF12",
                    product_image="https://example.test/image.jpg",
                    seller_name="Test Seller",
                    current_price_paise=12345,
                    current_stock_status=StockStatus.IN_STOCK,
                    delivery_availability=(
                        AmazonDeliveryAvailability("560001", True, "Delivery tomorrow"),
                    ),
                    last_checked=datetime.now(),
                    raw_summary="ok",
                )

        from app.integrations.marketplaces import MarketplaceCheckRequest

        result = await StubAmazonAdapter().check_stock(
            MarketplaceCheckRequest(
                marketplace=Marketplace.AMAZON,
                product_url="https://www.amazon.in/dp/B0ABCDEF12",
                pincode="560001",
            )
        )

        assert result.status is StockStatus.IN_STOCK
        assert result.price_paise == 12345
        assert result.raw_summary == "ok"

    asyncio.run(run_check())


def test_amazon_adapter_normalizes_retry_and_delay_configuration() -> None:
    adapter = AmazonMarketplaceAdapter(retries=-1, min_delay_ms=500, max_delay_ms=100)

    assert adapter._retries == 0
    assert adapter._min_delay_ms == 500
    assert adapter._max_delay_ms == 500


def test_product_content_selector_targets_real_product_containers() -> None:
    selector = AmazonMarketplaceAdapter._product_content_selector()

    for required in ("#dp", "#centerCol", "#title", "#productTitle", "#ppd"):
        assert required in selector


def test_wait_for_product_content_reloads_and_retries_when_container_is_missing() -> None:
    async def run_check() -> None:
        class FakePage:
            def __init__(self) -> None:
                self.waits = 0
                self.reloads = 0
                self.evaluations: list[str] = []
                self.timeouts: list[int] = []

            async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
                assert "#centerCol" in selector
                assert kwargs == {"state": "visible", "timeout": 1_000}
                self.waits += 1
                if self.waits == 1:
                    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

                    raise PlaywrightTimeoutError("missing product container")

            async def reload(self, *, wait_until: str, timeout: int) -> None:  # noqa: ASYNC109
                assert wait_until == "domcontentloaded"
                assert timeout == 1_000
                self.reloads += 1

            async def evaluate(self, script: str) -> None:
                self.evaluations.append(script)

            async def wait_for_timeout(self, timeout: int) -> None:  # noqa: ASYNC109
                self.timeouts.append(timeout)

        page = FakePage()
        await AmazonMarketplaceAdapter(timeout_ms=1_000)._wait_for_product_content(page)  # type: ignore[arg-type]

        assert page.waits == 2
        assert page.reloads == 1
        assert page.evaluations

    asyncio.run(run_check())
