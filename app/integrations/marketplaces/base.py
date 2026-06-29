from typing import Protocol

from app.domain.entities import StockStatus


class MarketplaceClient(Protocol):
    """Contract every future shopping website integration must implement."""

    async def check_stock(self, product_url: str, pincode: str) -> StockStatus: ...
