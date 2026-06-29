import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ProductModel,
    ProductPincodeModel,
    StockHistoryModel,
    UserDefaultPincodeModel,
    UserModel,
    UserProductTrackingModel,
)
from app.domain.entities import (
    Marketplace,
    Product,
    ProductPincode,
    StockHistory,
    StockStatus,
    User,
    UserDefaultPincode,
    UserProductTracking,
)


def _status(value: str | StockStatus | None) -> StockStatus | None:
    return StockStatus(value) if value is not None else None


def _marketplace(value: str | Marketplace) -> Marketplace:
    return Marketplace(value)


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user: User) -> User:
        model = UserModel(
            telegram_user_id=user.telegram_user_id,
            username=user.username,
            first_name=user.first_name,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def upsert(self, user: User) -> User:
        existing = await self.get_by_telegram_id(user.telegram_user_id)
        if existing is None:
            return await self.create(user)
        model = await self._session.get(UserModel, existing.id)
        if model is None:
            raise RuntimeError("User disappeared during upsert")
        model.username = user.username
        model.first_name = user.first_name
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, user_id: int) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return self._to_entity(model) if model else None

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.telegram_user_id == telegram_user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            model.id, model.telegram_user_id, model.username, model.first_name, model.created_at
        )


class SqlAlchemyUserDefaultPincodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[UserDefaultPincode]:
        result = await self._session.execute(
            select(UserDefaultPincodeModel)
            .where(UserDefaultPincodeModel.user_id == user_id)
            .order_by(UserDefaultPincodeModel.pincode)
        )
        return [self._to_entity(model) for model in result.scalars()]

    async def replace_for_user(self, user_id: int, pincodes: list[str]) -> list[UserDefaultPincode]:
        await self._session.execute(
            delete(UserDefaultPincodeModel).where(UserDefaultPincodeModel.user_id == user_id)
        )
        models = [UserDefaultPincodeModel(user_id=user_id, pincode=pincode) for pincode in pincodes]
        self._session.add_all(models)
        await self._session.commit()
        for model in models:
            await self._session.refresh(model)
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: UserDefaultPincodeModel) -> UserDefaultPincode:
        return UserDefaultPincode(model.id, model.user_id, model.pincode, model.created_at)


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, product: Product) -> Product:
        model = ProductModel(
            product_id=product.product_id,
            marketplace=product.marketplace.value,
            product_url=product.product_url,
            product_name=product.product_name,
            current_status=product.current_status.value,
            last_checked=product.last_checked,
            current_price_paise=product.current_price_paise,
            delivery_availability_by_pincode=json.dumps(
                product.delivery_availability_by_pincode or {}
            ),
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, product_id: int) -> Product | None:
        model = await self._session.get(ProductModel, product_id)
        return self._to_entity(model) if model else None

    async def get_by_marketplace_product_id(
        self, marketplace: str, product_id: str
    ) -> Product | None:
        result = await self._session.execute(
            select(ProductModel).where(
                ProductModel.marketplace == marketplace, ProductModel.product_id == product_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update(self, product: Product) -> Product:
        if product.id is None:
            raise ValueError("Product id is required for update")
        model = await self._session.get(ProductModel, product.id)
        if model is None:
            raise ValueError(f"Product {product.id} does not exist")
        model.product_id = product.product_id
        model.marketplace = product.marketplace.value
        model.product_url = product.product_url
        model.product_name = product.product_name
        model.current_status = product.current_status.value
        model.last_checked = product.last_checked
        model.current_price_paise = product.current_price_paise
        model.delivery_availability_by_pincode = json.dumps(
            product.delivery_availability_by_pincode or {}
        )
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def delete(self, product_id: int) -> None:
        await self._session.execute(delete(ProductModel).where(ProductModel.id == product_id))
        await self._session.commit()

    async def list_active_tracked(self) -> list[Product]:
        result = await self._session.execute(
            select(ProductModel)
            .join(UserProductTrackingModel)
            .distinct()
            .order_by(ProductModel.id)
        )
        return [self._to_entity(model) for model in result.scalars()]

    @staticmethod
    def _to_entity(model: ProductModel) -> Product:
        return Product(
            model.id,
            model.product_id,
            _marketplace(model.marketplace),
            model.product_url,
            model.product_name,
            StockStatus(model.current_status),
            model.last_checked,
            model.created_at,
            model.current_price_paise,
            json.loads(model.delivery_availability_by_pincode or "{}"),
        )


class SqlAlchemyProductPincodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, pincode: ProductPincode) -> ProductPincode:
        existing = await self._session.execute(
            select(ProductPincodeModel).where(
                ProductPincodeModel.product_id == pincode.product_id,
                ProductPincodeModel.pincode == pincode.pincode,
            )
        )
        model = existing.scalar_one_or_none()
        if model is None:
            model = ProductPincodeModel(product_id=pincode.product_id, pincode=pincode.pincode)
            self._session.add(model)
            await self._session.commit()
            await self._session.refresh(model)
        return self._to_entity(model)

    async def list_for_product(self, product_id: int) -> list[ProductPincode]:
        result = await self._session.execute(
            select(ProductPincodeModel)
            .where(ProductPincodeModel.product_id == product_id)
            .order_by(ProductPincodeModel.pincode)
        )
        return [self._to_entity(model) for model in result.scalars()]

    async def remove(self, product_id: int, pincode: str) -> None:
        await self._session.execute(
            delete(ProductPincodeModel).where(
                ProductPincodeModel.product_id == product_id, ProductPincodeModel.pincode == pincode
            )
        )
        await self._session.commit()

    @staticmethod
    def _to_entity(model: ProductPincodeModel) -> ProductPincode:
        return ProductPincode(model.id, model.product_id, model.pincode, model.created_at)


class SqlAlchemyUserProductTrackingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tracking: UserProductTracking) -> UserProductTracking:
        model = UserProductTrackingModel(
            user_id=tracking.user_id,
            product_id=tracking.product_id,
            notifications_enabled=tracking.notifications_enabled,
            last_notified_status=(
                tracking.last_notified_status.value if tracking.last_notified_status else None
            ),
            last_notified_at=tracking.last_notified_at,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, user_id: int, product_id: int) -> UserProductTracking | None:
        result = await self._session.execute(
            select(UserProductTrackingModel).where(
                UserProductTrackingModel.user_id == user_id,
                UserProductTrackingModel.product_id == product_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_for_user(self, user_id: int) -> list[UserProductTracking]:
        result = await self._session.execute(
            select(UserProductTrackingModel).where(UserProductTrackingModel.user_id == user_id)
        )
        return [self._to_entity(model) for model in result.scalars()]

    async def list_for_product(self, product_id: int) -> list[UserProductTracking]:
        result = await self._session.execute(
            select(UserProductTrackingModel).where(
                UserProductTrackingModel.product_id == product_id
            )
        )
        return [self._to_entity(model) for model in result.scalars()]

    async def update_notification_state(self, tracking: UserProductTracking) -> UserProductTracking:
        if tracking.id is None:
            raise ValueError("Tracking id is required for update")
        model = await self._session.get(UserProductTrackingModel, tracking.id)
        if model is None:
            raise ValueError(f"Tracking {tracking.id} does not exist")
        model.notifications_enabled = tracking.notifications_enabled
        model.last_notified_status = (
            tracking.last_notified_status.value if tracking.last_notified_status else None
        )
        model.last_notified_at = tracking.last_notified_at
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def delete(self, user_id: int, product_id: int) -> None:
        await self._session.execute(
            delete(UserProductTrackingModel).where(
                UserProductTrackingModel.user_id == user_id,
                UserProductTrackingModel.product_id == product_id,
            )
        )
        await self._session.commit()

    @staticmethod
    def _to_entity(model: UserProductTrackingModel) -> UserProductTracking:
        return UserProductTracking(
            model.id,
            model.user_id,
            model.product_id,
            model.notifications_enabled,
            _status(model.last_notified_status),
            model.last_notified_at,
            model.created_at,
        )


class SqlAlchemyStockHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, stock_history: StockHistory) -> StockHistory:
        model = StockHistoryModel(
            product_id=stock_history.product_id,
            status=stock_history.status.value,
            changed_at=stock_history.changed_at,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def list_for_product(self, product_id: int) -> list[StockHistory]:
        result = await self._session.execute(
            select(StockHistoryModel)
            .where(StockHistoryModel.product_id == product_id)
            .order_by(StockHistoryModel.changed_at)
        )
        return [self._to_entity(model) for model in result.scalars()]

    @staticmethod
    def _to_entity(model: StockHistoryModel) -> StockHistory:
        return StockHistory(model.id, model.product_id, StockStatus(model.status), model.changed_at)


# Backwards-compatible aliases for the old SQLite repository names.
SqliteUserRepository = SqlAlchemyUserRepository
SqliteUserDefaultPincodeRepository = SqlAlchemyUserDefaultPincodeRepository
SqliteProductRepository = SqlAlchemyProductRepository
SqliteProductPincodeRepository = SqlAlchemyProductPincodeRepository
SqliteStockHistoryRepository = SqlAlchemyStockHistoryRepository
