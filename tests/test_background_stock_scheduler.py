import asyncio
from datetime import UTC, datetime

from app.domain.entities import Marketplace, Product, ProductPincode, StockHistory, StockStatus
from app.integrations.marketplaces.amazon.adapter import AmazonProductSnapshot
from app.services.scheduler.jobs import BackgroundStockChecker


class InMemoryProducts:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self.updated: list[Product] = []

    async def create(self, product: Product) -> Product:
        return product

    async def get(self, product_id: int) -> Product | None:
        return next((product for product in self.products if product.id == product_id), None)

    async def get_by_marketplace_product_id(
        self, marketplace: str, product_id: str
    ) -> Product | None:
        return None

    async def update(self, product: Product) -> Product:
        self.updated.append(product)
        self.products = [product if item.id == product.id else item for item in self.products]
        return product

    async def delete(self, product_id: int) -> None:
        pass

    async def list_active_tracked(self) -> list[Product]:
        return self.products


class InMemoryPincodes:
    def __init__(self, pins_by_product: dict[int, list[str]]) -> None:
        self.pins_by_product = pins_by_product

    async def add(self, pincode: ProductPincode) -> ProductPincode:
        return pincode

    async def list_for_product(self, product_id: int) -> list[ProductPincode]:
        return [
            ProductPincode(index, product_id, pin)
            for index, pin in enumerate(self.pins_by_product[product_id], start=1)
        ]

    async def remove(self, product_id: int, pincode: str) -> None:
        pass


class InMemoryStockHistory:
    def __init__(self) -> None:
        self.records: list[StockHistory] = []

    async def record(self, stock_history: StockHistory) -> StockHistory:
        self.records.append(stock_history)
        return stock_history

    async def list_for_product(self, product_id: int) -> list[StockHistory]:
        return [record for record in self.records if record.product_id == product_id]


class InMemoryUnitOfWork:
    def __init__(
        self,
        products: InMemoryProducts,
        pincodes: InMemoryPincodes,
        history: InMemoryStockHistory,
    ) -> None:
        self.products = products
        self.pincodes = pincodes
        self.stock_history = history

    async def __aenter__(self) -> "InMemoryUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        pass


class FakeAmazonAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def check_product(self, product_url: str, pincodes: list[str]) -> AmazonProductSnapshot:
        self.calls.append((product_url, pincodes))
        return AmazonProductSnapshot(
            "Fresh Name",
            Marketplace.AMAZON,
            "B012345678",
            None,
            None,
            None,
            StockStatus.IN_STOCK,
            tuple(),
            datetime.now(UTC),
        )


def test_background_checker_updates_database_without_notifications() -> None:
    asyncio.run(_run_background_checker_updates_database_without_notifications())


async def _run_background_checker_updates_database_without_notifications() -> None:
    product = Product(
        1,
        "B012345678",
        Marketplace.AMAZON,
        "https://amazon.in/dp/B012345678",
        "Old",
        StockStatus.UNKNOWN,
    )
    products = InMemoryProducts([product])
    pincodes = InMemoryPincodes({1: ["110001", "560001"]})
    history = InMemoryStockHistory()
    adapter = FakeAmazonAdapter()
    checker = BackgroundStockChecker(
        uow_factory=lambda: InMemoryUnitOfWork(products, pincodes, history),
        amazon_adapter=adapter,
        worker_limit=1,
    )

    await checker.check_all_active_products()

    assert adapter.calls == [(product.product_url, ["110001", "560001"])]
    assert len(products.updated) == 1
    assert products.updated[0].product_name == "Fresh Name"
    assert products.updated[0].current_status is StockStatus.IN_STOCK
    assert products.updated[0].last_checked is not None
    assert history.records[0].product_id == product.id
    assert history.records[0].status is StockStatus.IN_STOCK


def test_background_checker_skips_unsupported_marketplaces() -> None:
    asyncio.run(_run_background_checker_skips_unsupported_marketplaces())


async def _run_background_checker_skips_unsupported_marketplaces() -> None:
    product = Product(
        1, "SKU", Marketplace.FLIPKART, "https://example.test/sku", "Item", StockStatus.UNKNOWN
    )
    products = InMemoryProducts([product])
    adapter = FakeAmazonAdapter()
    checker = BackgroundStockChecker(
        uow_factory=lambda: InMemoryUnitOfWork(
            products, InMemoryPincodes({1: ["110001"]}), InMemoryStockHistory()
        ),
        amazon_adapter=adapter,
        worker_limit=1,
    )

    await checker.check_all_active_products()

    assert adapter.calls == []
    assert products.updated == []


class SometimesFailingAmazonAdapter(FakeAmazonAdapter):
    async def check_product(self, product_url: str, pincodes: list[str]) -> AmazonProductSnapshot:
        if "fail" in product_url:
            raise RuntimeError("temporary Amazon failure")
        return await super().check_product(product_url, pincodes)


def test_background_checker_continues_after_product_failure() -> None:
    asyncio.run(_run_background_checker_continues_after_product_failure())


async def _run_background_checker_continues_after_product_failure() -> None:
    failing = Product(
        1,
        "FAILSKU",
        Marketplace.AMAZON,
        "https://amazon.in/dp/fail",
        "Failing",
        StockStatus.UNKNOWN,
    )
    healthy = Product(
        2,
        "B012345678",
        Marketplace.AMAZON,
        "https://amazon.in/dp/B012345678",
        "Healthy",
        StockStatus.UNKNOWN,
    )
    products = InMemoryProducts([failing, healthy])
    pincodes = InMemoryPincodes({1: ["110001"], 2: ["560001"]})
    history = InMemoryStockHistory()
    adapter = SometimesFailingAmazonAdapter()
    checker = BackgroundStockChecker(
        uow_factory=lambda: InMemoryUnitOfWork(products, pincodes, history),
        amazon_adapter=adapter,
        worker_limit=2,
    )

    await checker.check_all_active_products()

    assert adapter.calls == [(healthy.product_url, ["560001"])]
    assert [product.id for product in products.updated] == [healthy.id]
    assert [record.product_id for record in history.records] == [healthy.id]
