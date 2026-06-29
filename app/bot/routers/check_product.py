import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.config import Settings
from app.domain.entities import Marketplace
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.integrations.marketplaces.amazon.adapter import AmazonMarketplaceAdapter
from app.services.products.check_product import (
    CheckProductService,
    ProductCheckError,
    ProductCheckResult,
    display_marketplace,
    display_status,
    format_checked_timestamp,
    format_price,
)
from app.services.products.list_products import ListProductsService

logger = logging.getLogger(__name__)
router = Router(name="check_product")
_CALLBACK_PREFIX = "check_product:"
_EMPTY_LIST_MESSAGE = "You don't have any tracked products yet. Use /add to add your first product."


@router.message(Command("check"))
async def check_command(
    message: Message,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("I couldn't identify your Telegram user. Please try again.")
        return

    user = await user_repository.get_by_telegram_id(telegram_user.id)
    if user is None:
        await message.answer(_EMPTY_LIST_MESSAGE)
        return

    service = ListProductsService(product_repository, pincode_repository, tracking_repository)
    tracked_products = await service.list_products(user)
    if not tracked_products:
        await message.answer(_EMPTY_LIST_MESSAGE)
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{item.product.marketplace.value.title()} · {item.product.product_name[:50]}",
                callback_data=f"{_CALLBACK_PREFIX}{item.product.id}",
            )
        ]
        for item in tracked_products
        if item.product.id is not None
    ]
    await message.answer(
        "Select a tracked product to check now:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith(_CALLBACK_PREFIX))
async def check_product_callback(
    callback: CallbackQuery,
    settings: Settings,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    if callback.message is None:
        await callback.answer("Unable to answer this check request.", show_alert=True)
        return
    if callback.from_user is None:
        await callback.answer("I couldn't identify your Telegram user.", show_alert=True)
        return

    product_id = _parse_callback_product_id(callback.data)
    if product_id is None:
        await callback.answer("Invalid product selection.", show_alert=True)
        return

    user = await user_repository.get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Please use /start before checking products.", show_alert=True)
        return

    await callback.answer("Checking live stock…")
    await callback.message.answer("Checking live stock for every configured PIN code…")

    service = CheckProductService(product_repository, pincode_repository, tracking_repository)
    adapter = AmazonMarketplaceAdapter(
        headless=settings.browser_headless,
        timeout_ms=settings.browser_timeout_seconds * 1000,
    )
    try:
        result = await service.check_amazon_product(user, product_id, adapter)
    except ProductCheckError as exc:
        logger.info(
            "manual_product_check_rejected",
            extra={
                "telegram_user_id": callback.from_user.id,
                "product_id": product_id,
                "error": str(exc),
            },
        )
        await callback.message.answer(escape(str(exc)))
        return
    except Exception:
        logger.exception(
            "manual_product_check_failed",
            extra={"telegram_user_id": callback.from_user.id, "product_id": product_id},
        )
        await callback.message.answer(
            "Sorry, I couldn't complete the live check. Please try again later."
        )
        return
    finally:
        await adapter.close()

    await callback.message.answer(format_check_result(result))


def _parse_callback_product_id(data: str | None) -> int | None:
    if data is None or not data.startswith(_CALLBACK_PREFIX):
        return None
    value = data.removeprefix(_CALLBACK_PREFIX)
    return int(value) if value.isdecimal() else None


def format_check_result(result: ProductCheckResult) -> str:
    product = result.product
    snapshot = result.snapshot
    name = snapshot.product_name or product.product_name
    delivery_by_pin = {delivery.pincode: delivery for delivery in snapshot.delivery_availability}
    pin_lines = []
    for pincode in result.pincodes:
        delivery = delivery_by_pin.get(pincode)
        available = delivery.is_available if delivery is not None else False
        label = "✅ Available" if available else "❌ Not Deliverable"
        pin_lines.append(f"{escape(pincode)} {label}")

    status_emoji = "🟢" if snapshot.current_stock_status.value == "in_stock" else "🔴"
    lines = [
        f"{status_emoji} {escape(display_marketplace(product.marketplace))}",
        "",
        "Product:",
        escape(name),
        "",
        "Status:",
        escape(display_status(snapshot.current_stock_status)),
        "",
        "Price:",
        escape(format_price(snapshot.current_price_paise)),
    ]
    if snapshot.seller_name:
        lines.extend(["", "Seller:", escape(snapshot.seller_name)])
    lines.extend(
        [
            "",
            "PIN Results:",
            "",
            *pin_lines,
            "",
            "Last Checked:",
            format_checked_timestamp(snapshot.last_checked),
        ]
    )
    if product.marketplace is not Marketplace.AMAZON:
        lines.insert(0, "Currently only Amazon live checks are supported.")
    return "\n".join(lines)
