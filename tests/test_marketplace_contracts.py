from app.domain.entities import Marketplace, StockStatus
from app.integrations.marketplaces import MarketplaceCheckRequest, MarketplaceCheckResult


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
