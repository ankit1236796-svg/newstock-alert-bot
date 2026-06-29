import asyncio
from datetime import UTC, datetime

from app.domain.entities import Marketplace, Product, StockStatus, User, UserProductTracking
from app.integrations.marketplaces.amazon.adapter import (
    AmazonDeliveryAvailability,
    AmazonProductSnapshot,
)
from app.services.notifications.alerts import TelegramAlertService


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_stock_alert(self, telegram_user_id: int, message: str) -> None:
        self.sent.append((telegram_user_id, message))


class Users:
    async def create(self, user: User) -> User:
        return user

    async def upsert(self, user: User) -> User:
        return user

    async def get(self, user_id: int) -> User | None:
        return User(user_id, 12345, "user", "User")

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        return None


class Trackings:
    def __init__(self, trackings: list[UserProductTracking]) -> None:
        self.trackings = trackings
        self.updated: list[UserProductTracking] = []

    async def create(self, tracking: UserProductTracking) -> UserProductTracking:
        return tracking

    async def get(self, user_id: int, product_id: int) -> UserProductTracking | None:
        return None

    async def list_for_user(self, user_id: int) -> list[UserProductTracking]:
        return []

    async def list_for_product(self, product_id: int) -> list[UserProductTracking]:
        return self.trackings

    async def update_notification_state(self, tracking: UserProductTracking) -> UserProductTracking:
        self.updated.append(tracking)
        return tracking

    async def delete(self, user_id: int, product_id: int) -> None:
        pass


def test_alert_service_sends_price_and_delivery_change_message() -> None:
    asyncio.run(_run_alert_service_sends_price_and_delivery_change_message())


async def _run_alert_service_sends_price_and_delivery_change_message() -> None:
    previous = Product(
        1,
        "B012345678",
        Marketplace.AMAZON,
        "https://amazon.in/dp/B012345678",
        "Old Name",
        StockStatus.OUT_OF_STOCK,
        current_price_paise=10_000,
        delivery_availability_by_pincode={"110001": True},
    )
    current = Product(
        1,
        "B012345678",
        Marketplace.AMAZON,
        "https://amazon.in/dp/B012345678",
        "New Name",
        StockStatus.IN_STOCK,
        datetime(2026, 6, 29, tzinfo=UTC),
        current_price_paise=12_500,
        delivery_availability_by_pincode={"110001": False},
    )
    snapshot = AmazonProductSnapshot(
        "New Name",
        Marketplace.AMAZON,
        "B012345678",
        None,
        None,
        12_500,
        StockStatus.IN_STOCK,
        (AmazonDeliveryAvailability("110001", False),),
        datetime(2026, 6, 29, tzinfo=UTC),
    )
    notifier = FakeNotifier()
    trackings = Trackings([UserProductTracking(7, 1, 1)])
    service = TelegramAlertService(
        notifier=notifier, user_repository=Users(), tracking_repository=trackings
    )

    await service.notify_product_changes(previous=previous, current=current, snapshot=snapshot)

    assert len(notifier.sent) == 1
    _, message = notifier.sent[0]
    assert "Current Price: ₹125.00" in message
    assert "Previous Price: ₹100.00" in message
    assert "Difference: +₹25.00" in message
    assert "110001: Available → Not Available" in message
    assert trackings.updated[0].last_notified_status is StockStatus.IN_STOCK


def test_alert_service_skips_when_nothing_changed() -> None:
    asyncio.run(_run_alert_service_skips_when_nothing_changed())


async def _run_alert_service_skips_when_nothing_changed() -> None:
    product = Product(
        1,
        "B012345678",
        Marketplace.AMAZON,
        "https://amazon.in/dp/B012345678",
        "Name",
        StockStatus.IN_STOCK,
        current_price_paise=10_000,
        delivery_availability_by_pincode={"110001": True},
    )
    snapshot = AmazonProductSnapshot(
        "Name",
        Marketplace.AMAZON,
        "B012345678",
        None,
        None,
        10_000,
        StockStatus.IN_STOCK,
        (),
        datetime.now(UTC),
    )
    notifier = FakeNotifier()
    service = TelegramAlertService(
        notifier=notifier,
        user_repository=Users(),
        tracking_repository=Trackings([UserProductTracking(7, 1, 1)]),
    )

    await service.notify_product_changes(previous=product, current=product, snapshot=snapshot)

    assert notifier.sent == []
