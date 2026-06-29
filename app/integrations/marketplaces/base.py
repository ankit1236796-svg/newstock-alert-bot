from dataclasses import dataclass
from typing import Protocol

from app.domain.entities import Marketplace, StockStatus


@dataclass(frozen=True, slots=True)
class MarketplaceCheckRequest:
    """Input every marketplace adapter receives for a single stock lookup."""

    marketplace: Marketplace
    product_url: str
    pincode: str


@dataclass(frozen=True, slots=True)
class MarketplaceCheckResult:
    """Normalized output returned by marketplace adapters after a stock lookup."""

    status: StockStatus
    price_paise: int | None = None
    raw_summary: str | None = None


class MarketplaceAdapter(Protocol):
    """Contract every future shopping website integration must implement."""

    marketplace: Marketplace

    async def check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult: ...


MarketplaceClient = MarketplaceAdapter
