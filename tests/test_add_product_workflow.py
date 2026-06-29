import asyncio
from dataclasses import replace

import pytest

from app.bot.routers.add_product import is_valid_pincode, is_valid_url, parse_pincodes
from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockStatus,
    User,
    UserProductTracking,
)
from app.services.products.add_product import AddProductCommand, AddProductService


def test_parse_pincodes_accepts_comma_separated_unique_valid_pincodes() -> None:
    assert parse_pincodes("560001, 110001,560001") == ["560001", "110001"]


def test_parse_pincodes_rejects_any_invalid_pincode() -> None:
    assert parse_pincodes("560001, invalid, 012345") == []


@pytest.mark.parametrize("pincode", ["560001", "110001", "999999"])
def test_is_valid_pincode_accepts_indian_six_digit_pin_codes(pincode: str) -> None:
    assert is_valid_pincode(pincode)


@pytest.mark.parametrize("pincode", ["", "12345", "1234567", "012345", "ABC123"])
def test_is_valid_pincode_rejects_invalid_pin_codes(pincode: str) -> None:
    assert not is_valid_pincode(pincode)


@pytest.mark.parametrize("url", ["https://example.test/product", "http://example.test/product"])
def test_is_valid_url_accepts_http_urls(url: str) -> None:
    assert is_valid_url(url)


@pytest.mark.parametrize(
    "url", ["example.test/product", "ftp://example.test/product", "https:///broken"]
)
def test_is_valid_url_rejects_invalid_urls(url: str) -> None:
    assert not is_valid_url(url)


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


def test_add_product_service_saves_product_pincodes_and_tracking() -> None:
    asyncio.run(_run_add_product_service_saves_product_pincodes_and_tracking())


async def _run_add_product_service_saves_product_pincodes_and_tracking() -> None:
    products = InMemoryProductRepository()
    pincodes = InMemoryPincodeRepository()
    trackings = InMemoryTrackingRepository()
    service = AddProductService(products, pincodes, trackings)

    added = await service.add_product(
        AddProductCommand(
            user=User(1, 1, None, None),
            product_name="Console",
            product_url="https://www.flipkart.com/product/p/itmx",
            pincodes=["560001", "110001"],
        )
    )

    assert added.product.id == 1
    assert added.product.marketplace == Marketplace.FLIPKART
    assert added.product.current_status == StockStatus.UNKNOWN
    assert [item.pincode for item in pincodes.added] == ["560001", "110001"]
    assert trackings.created == [UserProductTracking(1, 1, 1)]
