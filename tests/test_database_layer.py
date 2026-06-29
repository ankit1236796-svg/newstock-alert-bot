# ruff: noqa: ANN001, ANN201, ANN202
import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Base
from app.database.repositories import (
    SqlAlchemyProductPincodeRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyStockHistoryRepository,
    SqlAlchemyUserDefaultPincodeRepository,
    SqlAlchemyUserProductTrackingRepository,
    SqlAlchemyUserRepository,
)
from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockHistory,
    StockStatus,
    User,
    UserProductTracking,
)


@pytest.fixture
def session_factory():
    async def setup_database():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.execute(text("PRAGMA foreign_keys=ON"))
            await connection.run_sync(Base.metadata.create_all)
        return engine, async_sessionmaker(engine, expire_on_commit=False)

    engine, factory = asyncio.run(setup_database())
    try:
        yield factory
    finally:
        asyncio.run(engine.dispose())


def test_async_repositories_support_tracking_database_flow(session_factory) -> None:
    async def run_test() -> None:
        async with session_factory() as session:
            users = SqlAlchemyUserRepository(session)
            products = SqlAlchemyProductRepository(session)
            pincodes = SqlAlchemyProductPincodeRepository(session)
            trackings = SqlAlchemyUserProductTrackingRepository(session)
            default_pins = SqlAlchemyUserDefaultPincodeRepository(session)
            history = SqlAlchemyStockHistoryRepository(session)

            user = await users.upsert(User(None, 123456789, "alice", "Alice"))
            product = await products.create(
                Product(
                    None,
                    "B0TEST",
                    Marketplace.AMAZON,
                    "https://example.test/product/B0TEST",
                    "Test Product",
                    StockStatus.OUT_OF_STOCK,
                )
            )
            assert user.id is not None
            assert product.id is not None

            await pincodes.add(ProductPincode(None, product.id, "560001"))
            await pincodes.add(ProductPincode(None, product.id, "110001"))
            assert [pin.pincode for pin in await pincodes.list_for_product(product.id)] == [
                "110001",
                "560001",
            ]
            saved_pins = await default_pins.replace_for_user(user.id, ["560001", "110001"])
            assert [pin.pincode for pin in saved_pins] == ["560001", "110001"]
            assert [pin.pincode for pin in await default_pins.list_for_user(user.id)] == [
                "110001",
                "560001",
            ]

            tracking = await trackings.create(UserProductTracking(None, user.id, product.id))
            notified_at = datetime(2026, 6, 29, 12, tzinfo=UTC)
            updated_tracking = await trackings.update_notification_state(
                UserProductTracking(
                    tracking.id,
                    user.id,
                    product.id,
                    True,
                    StockStatus.IN_STOCK,
                    notified_at,
                    tracking.created_at,
                )
            )
            assert updated_tracking.last_notified_status == StockStatus.IN_STOCK
            assert updated_tracking.last_notified_at == notified_at

            await history.record(StockHistory(None, product.id, StockStatus.OUT_OF_STOCK))
            await history.record(StockHistory(None, product.id, StockStatus.IN_STOCK))
            assert [item.status for item in await history.list_for_product(product.id)] == [
                StockStatus.OUT_OF_STOCK,
                StockStatus.IN_STOCK,
            ]

            product = await products.update(
                Product(
                    product.id,
                    product.product_id,
                    product.marketplace,
                    product.product_url,
                    product.product_name,
                    StockStatus.IN_STOCK,
                    notified_at,
                    product.created_at,
                )
            )
            assert product.current_status == StockStatus.IN_STOCK
            assert (await products.get_by_marketplace_product_id("amazon", "B0TEST")) == product

    asyncio.run(run_test())


def test_schema_has_expected_indexes_and_foreign_keys(session_factory) -> None:
    async def run_test():
        async with session_factory() as session:

            def inspect_schema(connection):
                inspector = inspect(connection.connection())
                indexes = {
                    table: {idx["name"] for idx in inspector.get_indexes(table)}
                    for table in inspector.get_table_names()
                }
                foreign_keys = {
                    table: len(inspector.get_foreign_keys(table))
                    for table in inspector.get_table_names()
                }
                return indexes, foreign_keys

            return await session.run_sync(inspect_schema)

    indexes, foreign_keys = asyncio.run(run_test())

    assert "idx_products_current_status" in indexes["products"]
    assert "idx_product_pincodes_product_id" in indexes["product_pincodes"]
    assert "idx_user_product_tracking_user_id" in indexes["user_product_tracking"]
    assert "idx_user_default_pincodes_user_id" in indexes["user_default_pincodes"]
    assert "idx_stock_history_product_id_changed_at" in indexes["stock_history"]
    assert foreign_keys["product_pincodes"] == 1
    assert foreign_keys["user_product_tracking"] == 2
    assert foreign_keys["user_default_pincodes"] == 1
    assert foreign_keys["stock_history"] == 1


def test_duplicate_tracking_is_prevented(session_factory) -> None:
    async def run_test() -> None:
        async with session_factory() as session:
            users = SqlAlchemyUserRepository(session)
            products = SqlAlchemyProductRepository(session)
            trackings = SqlAlchemyUserProductTrackingRepository(session)
            user = await users.create(User(None, 42, None, None))
            product = await products.create(
                Product(
                    None,
                    "SKU",
                    Marketplace.FLIPKART,
                    "https://example.test/sku",
                    "SKU",
                    StockStatus.OUT_OF_STOCK,
                )
            )
            assert user.id is not None and product.id is not None
            await trackings.create(UserProductTracking(None, user.id, product.id))
            with pytest.raises(IntegrityError):
                await trackings.create(UserProductTracking(None, user.id, product.id))

    asyncio.run(run_test())
