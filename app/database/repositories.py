from datetime import datetime
from typing import Any, cast

import aiosqlite

from app.domain.entities import Marketplace, Product, ProductPincode, StockCheck, StockStatus, User


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SqliteUserRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def upsert(self, user: User) -> User:
        cursor = await self._connection.execute(
            """
            INSERT INTO users (telegram_user_id, username, first_name, last_name, is_active)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                user.telegram_user_id,
                user.username,
                user.first_name,
                user.last_name,
                int(user.is_active),
            ),
        )
        row = await cursor.fetchone()
        await self._connection.commit()
        return self._user_from_row(cast(aiosqlite.Row, row))

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        cursor = await self._connection.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        )
        row = await cursor.fetchone()
        return self._user_from_row(row) if row else None

    @staticmethod
    def _user_from_row(row: aiosqlite.Row) -> User:
        data = dict(row)
        return User(
            id=cast(int, data["id"]),
            telegram_user_id=cast(int, data["telegram_user_id"]),
            username=cast(str | None, data["username"]),
            first_name=cast(str | None, data["first_name"]),
            last_name=cast(str | None, data["last_name"]),
            is_active=bool(data["is_active"]),
            created_at=_parse_datetime(cast(str | None, data["created_at"])),
            updated_at=_parse_datetime(cast(str | None, data["updated_at"])),
        )


class SqliteProductRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def create(self, product: Product) -> Product:
        cursor = await self._connection.execute(
            """
            INSERT INTO products (
                user_id, marketplace, product_url, display_name, target_price_paise, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING *
            """,
            (
                product.user_id,
                product.marketplace.value,
                product.product_url,
                product.display_name,
                product.target_price_paise,
                int(product.is_active),
            ),
        )
        row = await cursor.fetchone()
        await self._connection.commit()
        return self._product_from_row(cast(aiosqlite.Row, row))

    async def list_active_by_user(self, user_id: int) -> list[Product]:
        cursor = await self._connection.execute(
            "SELECT * FROM products WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [self._product_from_row(row) for row in rows]

    @staticmethod
    def _product_from_row(row: aiosqlite.Row) -> Product:
        data: dict[str, Any] = dict(row)
        return Product(
            id=cast(int, data["id"]),
            user_id=cast(int, data["user_id"]),
            marketplace=Marketplace(cast(str, data["marketplace"])),
            product_url=cast(str, data["product_url"]),
            display_name=cast(str, data["display_name"]),
            target_price_paise=cast(int | None, data["target_price_paise"]),
            is_active=bool(data["is_active"]),
            created_at=_parse_datetime(cast(str | None, data["created_at"])),
            updated_at=_parse_datetime(cast(str | None, data["updated_at"])),
        )


class SqliteProductPincodeRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def add(self, pincode: ProductPincode) -> ProductPincode:
        cursor = await self._connection.execute(
            """
            INSERT INTO product_pincodes (product_id, pincode, is_active)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id, pincode) DO UPDATE SET is_active = excluded.is_active
            RETURNING *
            """,
            (pincode.product_id, pincode.pincode, int(pincode.is_active)),
        )
        row = await cursor.fetchone()
        await self._connection.commit()
        return self._pincode_from_row(cast(aiosqlite.Row, row))

    async def list_active_for_product(self, product_id: int) -> list[ProductPincode]:
        cursor = await self._connection.execute(
            (
                "SELECT * FROM product_pincodes "
                "WHERE product_id = ? AND is_active = 1 ORDER BY pincode"
            ),
            (product_id,),
        )
        rows = await cursor.fetchall()
        return [self._pincode_from_row(row) for row in rows]

    @staticmethod
    def _pincode_from_row(row: aiosqlite.Row) -> ProductPincode:
        data = dict(row)
        return ProductPincode(
            id=cast(int, data["id"]),
            product_id=cast(int, data["product_id"]),
            pincode=cast(str, data["pincode"]),
            is_active=bool(data["is_active"]),
            created_at=_parse_datetime(cast(str | None, data["created_at"])),
        )


class SqliteStockCheckRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def record(self, stock_check: StockCheck) -> StockCheck:
        cursor = await self._connection.execute(
            """
            INSERT INTO stock_checks (product_id, pincode, status, price_paise, raw_summary)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
            """,
            (
                stock_check.product_id,
                stock_check.pincode,
                stock_check.status.value,
                stock_check.price_paise,
                stock_check.raw_summary,
            ),
        )
        row = await cursor.fetchone()
        await self._connection.commit()
        data = dict(cast(aiosqlite.Row, row))
        return StockCheck(
            id=cast(int, data["id"]),
            product_id=cast(int, data["product_id"]),
            pincode=cast(str, data["pincode"]),
            status=StockStatus(cast(str, data["status"])),
            price_paise=cast(int | None, data["price_paise"]),
            raw_summary=cast(str | None, data["raw_summary"]),
            checked_at=_parse_datetime(cast(str | None, data["checked_at"])),
        )
