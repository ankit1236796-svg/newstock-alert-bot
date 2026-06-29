"""Base marketplace contract for all shopping website integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Protocol, runtime_checkable

from .models import ProductLookup, ProductSnapshot


@runtime_checkable
class BaseMarketplace(Protocol):
    """Contract every marketplace adapter must satisfy.

    Implementations for Amazon, Flipkart, Croma, AJIO, Meesho, Zepto,
    Instamart, BigBasket, Savana, and future marketplaces should expose the
    same behavior and return ``ProductSnapshot`` objects only.
    """

    @property
    def marketplace_name(self) -> str:
        """Human-readable marketplace name used in alerts and logs."""
        ...

    def supports_url(self, product_url: str) -> bool:
        """Return True when this adapter can handle the supplied product URL."""
        ...

    async def fetch_product(self, lookup: ProductLookup) -> ProductSnapshot:
        """Fetch and normalize one product into the common data model."""
        ...


class AbstractMarketplace(ABC):
    """Optional ABC base class for marketplace adapters that prefer inheritance."""

    marketplace_name: str

    @abstractmethod
    def supports_url(self, product_url: str) -> bool:
        """Return True when this adapter can handle the supplied product URL."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_product(self, lookup: ProductLookup) -> ProductSnapshot:
        """Fetch and normalize one product into the common data model."""
        raise NotImplementedError

    async def fetch_products(
        self, lookups: Iterable[ProductLookup]
    ) -> list[ProductSnapshot]:
        """Fetch multiple products using the single-product contract."""
        return [await self.fetch_product(lookup) for lookup in lookups]
