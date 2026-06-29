import asyncio
from dataclasses import replace
from datetime import UTC, datetime

from app.bot.routers.list_products import format_tracked_products
from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockStatus,
    User,
    UserProductTracking,
)
from app.services.products.list_products import ListProductsService, TrackedProduct


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.created: list[Product] = []
        self.products_by_key: dict[tuple[str, str], Product] = {}

    async def create(self, product: Product) -> Product:
        created = replace(product, id=len(self.created) + 1)
        self.created.append(created)
        self.products_by_key[(created.marketplace.value, created.product_id)] = created
        return created

    async def get(self, product_id: int) -> Product | None:
        return next((product for product in self.created if product.id == product_id), None)

    async def get_by_marketplace_product_id(
        self, marketplace: str, product_id: str
    ) -> Product | None:
        return self.products_by_key.get((marketplace, product_id))

    async def update(self, product: Product) -> Product:
        return product


class InMemoryPincodeRepository:
    def __init__(self) -> None:
        self.added: list[ProductPincode] = []

    async def add(self, pincode: ProductPincode) -> ProductPincode:
        created = replace(pincode, id=len(self.added) + 1)
        self.added.append(created)
        return created

    async def list_for_product(self, product_id: int) -> list[ProductPincode]:
        return [pincode for pincode in self.added if pincode.product_id == product_id]

    async def remove(self, product_id: int, pincode: str) -> None:
        self.added = [
            item for item in self.added if item.product_id != product_id or item.pincode != pincode
        ]


class InMemoryTrackingRepository:
    def __init__(self) -> None:
        self.created: list[UserProductTracking] = []

    async def create(self, tracking: UserProductTracking) -> UserProductTracking:
        created = replace(tracking, id=len(self.created) + 1)
        self.created.append(created)
        return created

    async def get(self, user_id: int, product_id: int) -> UserProductTracking | None:
        return next(
            (
                tracking
                for tracking in self.created
                if tracking.user_id == user_id and tracking.product_id == product_id
            ),
            None,
        )

    async def list_for_user(self, user_id: int) -> list[UserProductTracking]:
        return [tracking for tracking in self.created if tracking.user_id == user_id]

    async def list_for_product(self, product_id: int) -> list[UserProductTracking]:
        return [tracking for tracking in self.created if tracking.product_id == product_id]

    async def update_notification_state(self, tracking: UserProductTracking) -> UserProductTracking:
        return tracking

    async def delete(self, user_id: int, product_id: int) -> None:
        self.created = [
            item
            for item in self.created
            if item.user_id != user_id or item.product_id != product_id
        ]


def test_list_products_service_returns_products_with_pincodes_for_user() -> None:
    asyncio.run(_run_list_products_service_returns_products_with_pincodes_for_user())


async def _run_list_products_service_returns_products_with_pincodes_for_user() -> None:
    products = InMemoryProductRepository()
    pincodes = InMemoryPincodeRepository()
    trackings = InMemoryTrackingRepository()
    service = ListProductsService(products, pincodes, trackings)
    user = User(1, 123, "alice", "Alice")

    created_product = await products.create(
        Product(
            None,
            "SKU",
            Marketplace.AMAZON,
            "https://example.test/sku",
            "Console",
            StockStatus.UNKNOWN,
        )
    )
    assert created_product.id is not None
    await pincodes.add(ProductPincode(None, created_product.id, "560001"))
    await pincodes.add(ProductPincode(None, created_product.id, "110001"))
    await trackings.create(UserProductTracking(None, user.id or 0, created_product.id))

    tracked_products = await service.list_products(user)

    assert tracked_products == [TrackedProduct(created_product, ["560001", "110001"])]


def test_format_tracked_products_numbers_and_escapes_products() -> None:
    checked_at = datetime(2026, 6, 29, 12, tzinfo=UTC)
    unknown_product = Product(
        1,
        "SKU1",
        Marketplace.AMAZON,
        "https://example.test/sku?name=<Console>",
        "Console <Pro>",
        StockStatus.UNKNOWN,
    )
    in_stock_product = Product(
        2,
        "SKU2",
        Marketplace.FLIPKART,
        "https://example.test/sku2",
        "Handheld",
        StockStatus.IN_STOCK,
        checked_at,
    )

    message = format_tracked_products(
        [
            TrackedProduct(unknown_product, ["560001", "110001"]),
            TrackedProduct(in_stock_product, []),
        ]
    )

    assert "1. <b>Console &lt;Pro&gt;</b>" in message
    assert "URL: https://example.test/sku?name=&lt;Console&gt;" in message
    assert "Status: Unknown" in message
    assert "PIN Codes: 560001, 110001" in message
    assert "2. <b>Handheld</b>" in message
    assert "Status: In Stock" in message
    assert "PIN Codes: None" in message
