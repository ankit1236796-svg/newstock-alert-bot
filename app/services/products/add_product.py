from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockStatus,
    User,
    UserProductTracking,
)
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
)


@dataclass(frozen=True, slots=True)
class AddProductCommand:
    user: User
    product_name: str
    product_url: str
    pincodes: list[str]


@dataclass(frozen=True, slots=True)
class AddedProduct:
    product: Product
    pincodes: list[str]


class AddProductService:
    def __init__(
        self,
        product_repository: ProductRepository,
        pincode_repository: ProductPincodeRepository,
        tracking_repository: UserProductTrackingRepository,
    ) -> None:
        self._products = product_repository
        self._pincodes = pincode_repository
        self._trackings = tracking_repository

    async def add_product(self, command: AddProductCommand) -> AddedProduct:
        if command.user.id is None:
            raise ValueError("User must be persisted before adding products")

        marketplace = infer_marketplace(command.product_url)
        marketplace_product_id = build_marketplace_product_id(command.product_url)
        product = await self._products.get_by_marketplace_product_id(
            marketplace.value,
            marketplace_product_id,
        )
        if product is None:
            product = await self._products.create(
                Product(
                    id=None,
                    product_id=marketplace_product_id,
                    marketplace=marketplace,
                    product_url=command.product_url,
                    product_name=command.product_name,
                    current_status=StockStatus.UNKNOWN,
                )
            )

        if product.id is None:
            raise ValueError("Product repository returned an unpersisted product")

        for pincode in command.pincodes:
            await self._pincodes.add(ProductPincode(None, product.id, pincode))

        existing_tracking = await self._trackings.get(command.user.id, product.id)
        if existing_tracking is None:
            await self._trackings.create(UserProductTracking(None, command.user.id, product.id))

        return AddedProduct(product, command.pincodes)


def build_marketplace_product_id(product_url: str) -> str:
    return sha256(product_url.encode("utf-8")).hexdigest()


def infer_marketplace(product_url: str) -> Marketplace:
    host = urlparse(product_url).netloc.lower()
    marketplace_by_host = {
        "amazon": Marketplace.AMAZON,
        "flipkart": Marketplace.FLIPKART,
        "croma": Marketplace.CROMA,
        "ajio": Marketplace.AJIO,
        "meesho": Marketplace.MEESHO,
        "zeptonow": Marketplace.ZEPTO,
        "instamart": Marketplace.INSTAMART,
        "bigbasket": Marketplace.BIGBASKET,
        "savana": Marketplace.SAVANA,
    }
    for host_fragment, marketplace in marketplace_by_host.items():
        if host_fragment in host:
            return marketplace
    return Marketplace.AMAZON
