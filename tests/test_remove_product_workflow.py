import asyncio
from dataclasses import replace

from app.bot.routers.remove_product import build_confirmation_keyboard, build_remove_keyboard
from app.domain.entities import Marketplace, Product, StockStatus, User, UserProductTracking
from app.services.products.list_products import TrackedProduct
from app.services.products.remove_product import RemoveProductService
from tests.test_list_products_workflow import InMemoryProductRepository, InMemoryTrackingRepository


def test_remove_product_service_deletes_orphan_product() -> None:
    asyncio.run(_run_remove_product_service_deletes_orphan_product())


async def _run_remove_product_service_deletes_orphan_product() -> None:
    products = RemovableProductRepository()
    trackings = InMemoryTrackingRepository()
    service = RemoveProductService(products, trackings)
    user = User(1, 123, "alice", "Alice")
    product = await products.create(
        Product(
            None,
            "SKU",
            Marketplace.AMAZON,
            "https://example.test/sku",
            "Console",
            StockStatus.UNKNOWN,
        )
    )
    assert product.id is not None
    await trackings.create(UserProductTracking(None, user.id or 0, product.id))

    result = await service.remove_product(user, product.id)

    assert result is not None
    assert result.product == product
    assert result.product_deleted is True
    assert await trackings.list_for_product(product.id) == []
    assert await products.get(product.id) is None


def test_remove_product_service_keeps_product_tracked_by_other_users() -> None:
    asyncio.run(_run_remove_product_service_keeps_product_tracked_by_other_users())


async def _run_remove_product_service_keeps_product_tracked_by_other_users() -> None:
    products = RemovableProductRepository()
    trackings = InMemoryTrackingRepository()
    service = RemoveProductService(products, trackings)
    user = User(1, 123, "alice", "Alice")
    product = await products.create(
        Product(
            None,
            "SKU",
            Marketplace.AMAZON,
            "https://example.test/sku",
            "Console",
            StockStatus.UNKNOWN,
        )
    )
    assert product.id is not None
    await trackings.create(UserProductTracking(None, 1, product.id))
    await trackings.create(UserProductTracking(None, 2, product.id))

    result = await service.remove_product(user, product.id)

    assert result is not None
    assert result.product_deleted is False
    assert await products.get(product.id) == product
    assert [tracking.user_id for tracking in await trackings.list_for_product(product.id)] == [2]


def test_remove_keyboards_include_expected_actions() -> None:
    product = Product(
        7, "SKU", Marketplace.FLIPKART, "https://example.test/sku", "Handheld", StockStatus.UNKNOWN
    )

    remove_keyboard = build_remove_keyboard([TrackedProduct(product, ["560001"])])
    confirmation_keyboard = build_confirmation_keyboard()

    assert remove_keyboard.inline_keyboard[0][0].text == "1. Handheld"
    assert remove_keyboard.inline_keyboard[0][0].callback_data == "remove:select:7"
    assert remove_keyboard.inline_keyboard[-1][0].callback_data == "remove:cancel"
    assert confirmation_keyboard.inline_keyboard[0][0].callback_data == "remove:confirm"
    assert confirmation_keyboard.inline_keyboard[0][1].callback_data == "remove:cancel"


class RemovableProductRepository(InMemoryProductRepository):
    async def delete(self, product_id: int) -> None:
        self.created = [product for product in self.created if product.id != product_id]
        self.products_by_key = {
            (product.marketplace.value, product.product_id): product for product in self.created
        }

    async def update(self, product: Product) -> Product:
        if product.id is None:
            return product
        self.created = [
            replace(product) if item.id == product.id else item for item in self.created
        ]
        return product
