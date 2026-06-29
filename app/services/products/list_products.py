from dataclasses import dataclass

from app.domain.entities import Product, StockStatus, User
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
)


@dataclass(frozen=True, slots=True)
class TrackedProduct:
    product: Product
    pincodes: list[str]


class ListProductsService:
    def __init__(
        self,
        product_repository: ProductRepository,
        pincode_repository: ProductPincodeRepository,
        tracking_repository: UserProductTrackingRepository,
    ) -> None:
        self._products = product_repository
        self._pincodes = pincode_repository
        self._trackings = tracking_repository

    async def list_products(self, user: User) -> list[TrackedProduct]:
        if user.id is None:
            return []

        tracked_products: list[TrackedProduct] = []
        trackings = await self._trackings.list_for_user(user.id)
        for tracking in trackings:
            product = await self._products.get(tracking.product_id)
            if product is None:
                continue
            if product.id is None:
                continue
            pincodes = await self._pincodes.list_for_product(product.id)
            tracked_products.append(
                TrackedProduct(
                    product=product,
                    pincodes=[pincode.pincode for pincode in pincodes],
                )
            )

        return tracked_products


def display_stock_status(product: Product) -> str:
    if product.last_checked is None or product.current_status == StockStatus.UNKNOWN:
        return "Unknown"
    return product.current_status.value.replace("_", " ").title()
