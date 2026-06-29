from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.services.products.list_products import (
    ListProductsService,
    TrackedProduct,
    display_stock_status,
)

router = Router(name="list_products")

_EMPTY_LIST_MESSAGE = "You don't have any tracked products yet. Use /add to add your first product."


@router.message(Command("list"))
async def list_products_command(
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

    await message.answer(format_tracked_products(tracked_products))


def format_tracked_products(tracked_products: list[TrackedProduct]) -> str:
    sections = ["Your tracked products:"]
    for index, tracked_product in enumerate(tracked_products, start=1):
        product = tracked_product.product
        pincodes = ", ".join(tracked_product.pincodes) if tracked_product.pincodes else "None"
        sections.append(
            "\n".join(
                [
                    f"{index}. <b>{escape(product.product_name)}</b>",
                    f"URL: {escape(product.product_url)}",
                    f"Status: {display_stock_status(product)}",
                    f"PIN Codes: {escape(pincodes)}",
                ]
            )
        )
    return "\n\n".join(sections)
