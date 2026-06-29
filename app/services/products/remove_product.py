import logging
from dataclasses import dataclass

from app.domain.entities import Product, User
from app.domain.repositories import ProductRepository, UserProductTrackingRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RemoveProductResult:
    product: Product
    product_deleted: bool


class RemoveProductService:
    def __init__(
        self,
        product_repository: ProductRepository,
        tracking_repository: UserProductTrackingRepository,
    ) -> None:
        self._products = product_repository
        self._trackings = tracking_repository

    async def remove_product(self, user: User, product_id: int) -> RemoveProductResult | None:
        if user.id is None:
            logger.warning("Cannot remove product tracking for user without id")
            return None

        tracking = await self._trackings.get(user.id, product_id)
        if tracking is None:
            logger.info("User %s tried to remove untracked product %s", user.id, product_id)
            return None

        product = await self._products.get(product_id)
        if product is None:
            logger.warning("Tracking exists for missing product %s; deleting tracking", product_id)
            await self._trackings.delete(user.id, product_id)
            return None

        await self._trackings.delete(user.id, product_id)
        remaining_trackings = await self._trackings.list_for_product(product_id)
        product_deleted = not remaining_trackings
        if product_deleted:
            await self._products.delete(product_id)
            logger.info(
                "Deleted orphaned product %s after user %s removed tracking", product_id, user.id
            )
        else:
            logger.info("Removed tracking for user %s and retained product %s", user.id, product_id)

        return RemoveProductResult(product=product, product_deleted=product_deleted)
