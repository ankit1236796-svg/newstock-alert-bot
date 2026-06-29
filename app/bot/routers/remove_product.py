import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.services.products.list_products import ListProductsService, TrackedProduct
from app.services.products.remove_product import RemoveProductService

logger = logging.getLogger(__name__)
router = Router(name="remove_product")

_EMPTY_REMOVE_MESSAGE = (
    "You don't have any tracked products to remove. Use /add to track a product."
)
_CANCELLED_MESSAGE = "❌ Product removal cancelled."
_PRODUCT_NOT_FOUND_MESSAGE = (
    "I couldn't find that tracked product anymore. Please try /remove again."
)


class RemoveProductStates(StatesGroup):
    waiting_for_selection = State()
    waiting_for_confirmation = State()


@router.message(Command("remove"))
async def remove_product_command(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    await state.clear()
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("I couldn't identify your Telegram user. Please try again.")
        return

    user = await user_repository.get_by_telegram_id(telegram_user.id)
    if user is None:
        await message.answer(_EMPTY_REMOVE_MESSAGE)
        return

    tracked_products = await ListProductsService(
        product_repository, pincode_repository, tracking_repository
    ).list_products(user)
    if not tracked_products:
        await message.answer(_EMPTY_REMOVE_MESSAGE)
        return

    await state.set_state(RemoveProductStates.waiting_for_selection)
    await message.answer(
        "Select a tracked product to remove:",
        reply_markup=build_remove_keyboard(tracked_products),
    )


@router.callback_query(
    RemoveProductStates.waiting_for_selection, F.data.startswith("remove:select:")
)
async def select_product_to_remove(
    callback: CallbackQuery,
    state: FSMContext,
    product_repository: ProductRepository,
) -> None:
    await callback.answer()
    product_id = _parse_product_id(callback.data)
    if product_id is None:
        await state.clear()
        await _edit_or_answer(callback, _PRODUCT_NOT_FOUND_MESSAGE)
        return

    product = await product_repository.get(product_id)
    if product is None:
        await state.clear()
        await _edit_or_answer(callback, _PRODUCT_NOT_FOUND_MESSAGE)
        return

    await state.update_data(product_id=product_id)
    await state.set_state(RemoveProductStates.waiting_for_confirmation)
    await _edit_or_answer(
        callback,
        f"Remove tracking for <b>{product.product_name}</b>?",
        reply_markup=build_confirmation_keyboard(),
    )


@router.callback_query(RemoveProductStates.waiting_for_selection, F.data == "remove:cancel")
@router.callback_query(RemoveProductStates.waiting_for_confirmation, F.data == "remove:cancel")
async def cancel_remove_product(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Cancelled")
    await state.clear()
    await _edit_or_answer(callback, _CANCELLED_MESSAGE)


@router.callback_query(RemoveProductStates.waiting_for_confirmation, F.data == "remove:confirm")
async def confirm_remove_product(
    callback: CallbackQuery,
    state: FSMContext,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    telegram_user = callback.from_user
    user = await user_repository.get_by_telegram_id(telegram_user.id)
    data = await state.get_data()
    await state.clear()

    product_id = data.get("product_id")
    if user is None or not isinstance(product_id, int):
        logger.warning("Remove confirmation missing user or product_id")
        await callback.answer()
        await _edit_or_answer(callback, _PRODUCT_NOT_FOUND_MESSAGE)
        return

    result = await RemoveProductService(product_repository, tracking_repository).remove_product(
        user, product_id
    )
    await callback.answer("Deleted" if result else "Not found")
    if result is None:
        await _edit_or_answer(callback, _PRODUCT_NOT_FOUND_MESSAGE)
        return

    suffix = (
        " The product record was also cleaned up because no one else tracks it."
        if result.product_deleted
        else ""
    )
    await _edit_or_answer(
        callback,
        f"✅ Removed <b>{result.product.product_name}</b> from your tracked products.{suffix}",
    )


@router.callback_query(RemoveProductStates.waiting_for_selection)
@router.callback_query(RemoveProductStates.waiting_for_confirmation)
async def invalid_remove_callback(callback: CallbackQuery) -> None:
    await callback.answer("Please use the buttons shown above.", show_alert=True)


def build_remove_keyboard(tracked_products: list[TrackedProduct]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for index, tracked_product in enumerate(tracked_products, start=1):
        product = tracked_product.product
        if product.id is None:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{index}. {product.product_name}",
                    callback_data=f"remove:select:{product.id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="remove:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Delete", callback_data="remove:confirm"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="remove:cancel"),
            ]
        ]
    )


def _parse_product_id(callback_data: str | None) -> int | None:
    if callback_data is None:
        return None
    try:
        return int(callback_data.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return None


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    else:
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
