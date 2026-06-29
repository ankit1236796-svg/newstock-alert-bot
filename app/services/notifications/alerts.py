import logging
from dataclasses import replace
from datetime import UTC, datetime
from html import escape

from app.domain.entities import Product, StockStatus, UserProductTracking
from app.domain.repositories import UserProductTrackingRepository, UserRepository
from app.integrations.marketplaces.amazon.adapter import AmazonProductSnapshot
from app.services.notifications.notifier import Notifier

logger = logging.getLogger(__name__)


class TelegramAlertService:
    def __init__(
        self,
        *,
        notifier: Notifier,
        user_repository: UserRepository,
        tracking_repository: UserProductTrackingRepository,
    ) -> None:
        self._notifier = notifier
        self._users = user_repository
        self._trackings = tracking_repository

    async def notify_product_changes(
        self, *, previous: Product, current: Product, snapshot: AmazonProductSnapshot
    ) -> None:
        if previous.id is None:
            logger.error("alert_error", extra={"reason": "missing_product_id"})
            return
        changes = _detect_changes(previous, current, snapshot)
        if not changes:
            logger.info("alert_skipped", extra={"product_id": previous.id, "reason": "no_changes"})
            return
        trackings = await self._trackings.list_for_product(previous.id)
        if not trackings:
            logger.info(
                "alert_skipped", extra={"product_id": previous.id, "reason": "no_trackings"}
            )
            return
        message = _format_message(previous, current, snapshot, changes)
        for tracking in trackings:
            await self._notify_tracking(tracking, current.current_status, message, changes)

    async def _notify_tracking(
        self,
        tracking: UserProductTracking,
        current_status: StockStatus,
        message: str,
        changes: list[str],
    ) -> None:
        if not tracking.notifications_enabled:
            logger.info("alert_skipped", extra={"tracking_id": tracking.id, "reason": "disabled"})
            return
        if tracking.last_notified_status is current_status and changes == ["stock"]:
            logger.info("alert_duplicate_ignored", extra={"tracking_id": tracking.id})
            return
        user = await self._users.get(tracking.user_id)
        if user is None:
            logger.error(
                "alert_error", extra={"tracking_id": tracking.id, "reason": "missing_user"}
            )
            return
        try:
            await self._notifier.send_stock_alert(user.telegram_user_id, message)
        except Exception as exc:
            logger.exception(
                "alert_error",
                extra={
                    "tracking_id": tracking.id,
                    "telegram_user_id": user.telegram_user_id,
                    "error": repr(exc),
                },
            )
            return
        await self._trackings.update_notification_state(
            replace(
                tracking, last_notified_status=current_status, last_notified_at=datetime.now(UTC)
            )
        )
        logger.info("alert_sent", extra={"tracking_id": tracking.id, "changes": changes})


def _detect_changes(
    previous: Product, current: Product, snapshot: AmazonProductSnapshot
) -> list[str]:
    changes: list[str] = []
    if previous.current_status is not current.current_status:
        changes.append("stock")
    if previous.current_price_paise != current.current_price_paise:
        changes.append("price")
    if previous.delivery_availability_by_pincode != current.delivery_availability_by_pincode:
        changes.append("delivery")
    return changes


def _format_message(
    previous: Product, current: Product, snapshot: AmazonProductSnapshot, changes: list[str]
) -> str:
    lines = [
        "🔔 <b>Stock Alert</b>",
        f"Product Name: {escape(current.product_name)}",
        f"Marketplace: {escape(current.marketplace.value.title())}",
        f"Product URL: {escape(current.product_url)}",
        f"Current Price: {_money(current.current_price_paise)}",
    ]
    if "price" in changes:
        lines.extend(
            [
                f"Previous Price: {_money(previous.current_price_paise)}",
                f"Difference: "
                f"{_money_diff(previous.current_price_paise, current.current_price_paise)}",
            ]
        )
    lines.extend(
        [
            f"Stock Status: {escape(current.current_status.value.replace('_', ' ').title())}",
            f"Delivery Status: {_delivery_summary(current.delivery_availability_by_pincode)}",
        ]
    )
    if "delivery" in changes:
        lines.append(
            "Delivery Changes: "
            + escape(
                _delivery_changes(
                    previous.delivery_availability_by_pincode,
                    current.delivery_availability_by_pincode,
                )
            )
        )
    lines.append(f"Checked Time: {current.last_checked or snapshot.last_checked}")
    return "\n".join(lines)


def _delivery_summary(delivery: dict[str, bool] | None) -> str:
    if not delivery:
        return "Unknown"
    return escape(
        ", ".join(
            f"{pin}: {'Available' if ok else 'Not Available'}"
            for pin, ok in sorted(delivery.items())
        )
    )


def _delivery_changes(
    previous: dict[str, bool] | None, current: dict[str, bool] | None
) -> str:
    previous = previous or {}
    current = current or {}
    changed = []
    for pin in sorted(set(previous) | set(current)):
        if previous.get(pin) != current.get(pin):
            changed.append(
                f"{pin}: {_availability(previous.get(pin))} "
                f"→ {_availability(current.get(pin))}"
            )
    return ", ".join(changed)


def _availability(value: bool | None) -> str:
    if value is None:
        return "Unknown"
    return "Available" if value else "Not Available"


def _money(value: int | None) -> str:
    return "Unknown" if value is None else f"₹{value / 100:,.2f}"


def _money_diff(old: int | None, new: int | None) -> str:
    if old is None or new is None:
        return "Unknown"
    diff = new - old
    sign = "+" if diff > 0 else ""
    return f"{sign}₹{diff / 100:,.2f}"
