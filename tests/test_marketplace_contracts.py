import asyncio

import pytest

from app.domain.entities import Marketplace, StockStatus
from app.integrations.marketplaces import (
    BaseMarketplace,
    MarketplaceCheckRequest,
    MarketplaceCheckResult,
)


class ExampleMarketplace(BaseMarketplace):
    marketplace = Marketplace.AMAZON

    async def _check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult:
        return MarketplaceCheckResult(
            status=StockStatus.IN_STOCK,
            price_paise=12345,
            raw_summary=f"Checked {request.product_url} for {request.pincode}",
        )


def test_marketplace_check_request_captures_lookup_inputs() -> None:
    request = MarketplaceCheckRequest(
        marketplace=Marketplace.AMAZON,
        product_url="https://example.test/product",
        pincode="560001",
    )

    assert request.marketplace is Marketplace.AMAZON
    assert request.product_url == "https://example.test/product"
    assert request.pincode == "560001"


def test_marketplace_check_result_defaults_to_no_price_or_summary() -> None:
    result = MarketplaceCheckResult(status=StockStatus.UNKNOWN)

    assert result.status is StockStatus.UNKNOWN
    assert result.price_paise is None
    assert result.raw_summary is None


def test_base_marketplace_returns_adapter_result_for_supported_marketplace() -> None:
    request = MarketplaceCheckRequest(
        marketplace=Marketplace.AMAZON,
        product_url="https://example.test/product",
        pincode="560001",
    )

    result = asyncio.run(ExampleMarketplace().check_stock(request))

    assert result.status is StockStatus.IN_STOCK
    assert result.price_paise == 12345
    assert result.raw_summary == "Checked https://example.test/product for 560001"


def test_base_marketplace_rejects_requests_for_other_marketplaces() -> None:
    request = MarketplaceCheckRequest(
        marketplace=Marketplace.FLIPKART,
        product_url="https://example.test/product",
        pincode="560001",
    )

    with pytest.raises(ValueError, match="supports amazon, not flipkart"):
        asyncio.run(ExampleMarketplace().check_stock(request))
