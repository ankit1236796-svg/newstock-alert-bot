from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.connection import get_session
from app.database.repositories import (
    SqlAlchemyProductPincodeRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyUserProductTrackingRepository,
    SqlAlchemyUserRepository,
)


class DatabaseSessionMiddleware(BaseMiddleware):
    """Provide per-update database dependencies to aiogram handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        async with get_session() as session:
            data["session"] = session
            data["user_repository"] = SqlAlchemyUserRepository(session)
            data["product_repository"] = SqlAlchemyProductRepository(session)
            data["pincode_repository"] = SqlAlchemyProductPincodeRepository(session)
            data["tracking_repository"] = SqlAlchemyUserProductTrackingRepository(session)
            return await handler(event, data)
