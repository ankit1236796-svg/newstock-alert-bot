from abc import ABC, abstractmethod
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
    """Structural contract every shopping website integration must implement."""

    marketplace: Marketplace

    async def check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult: ...


class BaseMarketplace(ABC):
    """Base class for concrete marketplace stock-check adapters.

    Subclasses declare the single marketplace they support and implement the
    protected lookup method. The public ``check_stock`` method enforces that
    callers do not accidentally route a request to the wrong adapter.
    """

    marketplace: Marketplace

    async def check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult:
        """Validate the request marketplace before running the adapter lookup."""

        if request.marketplace is not self.marketplace:
            msg = (
                f"{self.__class__.__name__} supports {self.marketplace.value}, "
                f"not {request.marketplace.value}"
            )
            raise ValueError(msg)
        return await self._check_stock(request)

    @abstractmethod
    async def _check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult:
        """Run the marketplace-specific stock lookup."""


MarketplaceClient = MarketplaceAdapter
