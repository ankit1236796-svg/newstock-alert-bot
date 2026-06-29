from typing import Protocol

from app.domain.entities import Product, ProductPincode, StockCheck, User


class UserRepository(Protocol):
    async def upsert(self, user: User) -> User: ...

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None: ...


class ProductRepository(Protocol):
    async def create(self, product: Product) -> Product: ...

    async def list_active_by_user(self, user_id: int) -> list[Product]: ...


class ProductPincodeRepository(Protocol):
    async def add(self, pincode: ProductPincode) -> ProductPincode: ...

    async def list_active_for_product(self, product_id: int) -> list[ProductPincode]: ...


class StockCheckRepository(Protocol):
    async def record(self, stock_check: StockCheck) -> StockCheck: ...
