from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.domain.entities import User
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.services.products.add_product import AddProductCommand, AddProductService

router = Router(name="add_product")


class AddProductStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_url = State()
    waiting_for_pincodes = State()


@router.message(Command("add"))
async def add_product_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer("Please send the Product Name.")


@router.message(AddProductStates.waiting_for_name, F.text)
async def receive_product_name(message: Message, state: FSMContext) -> None:
    product_name = _clean_text(message.text)
    if product_name is None:
        await message.answer("Product Name can't be empty. Please send the Product Name.")
        return

    await state.update_data(product_name=product_name)
    await state.set_state(AddProductStates.waiting_for_url)
    await message.answer("Please send the Product URL.")


@router.message(AddProductStates.waiting_for_url, F.text)
async def receive_product_url(message: Message, state: FSMContext) -> None:
    product_url = _clean_text(message.text)
    if product_url is None or not is_valid_url(product_url):
        await message.answer("Please send a valid Product URL starting with http:// or https://.")
        return

    await state.update_data(product_url=product_url)
    await state.set_state(AddProductStates.waiting_for_pincodes)
    await message.answer(
        "Please send one or more PIN codes. You can separate multiple PIN codes with commas."
    )


@router.message(AddProductStates.waiting_for_pincodes, F.text)
async def receive_pincodes(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    pincodes = parse_pincodes(message.text or "")
    if not pincodes:
        await message.answer(
            "Please send valid 6-digit PIN codes separated by commas, for example: 560001, 110001."
        )
        return

    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("I couldn't identify your Telegram user. Please try /add again.")
        await state.clear()
        return

    data = await state.get_data()
    user = await user_repository.upsert(
        User(None, telegram_user.id, telegram_user.username, telegram_user.first_name)
    )
    service = AddProductService(product_repository, pincode_repository, tracking_repository)
    added_product = await service.add_product(
        AddProductCommand(
            user=user,
            product_name=str(data["product_name"]),
            product_url=str(data["product_url"]),
            pincodes=pincodes,
        )
    )

    await state.clear()
    await message.answer(
        "✅ Product Added\n\n"
        f"Product: {added_product.product.product_name}\n"
        f"URL: {added_product.product.product_url}\n"
        f"PIN Codes: {', '.join(added_product.pincodes)}"
    )


@router.message(AddProductStates.waiting_for_name)
@router.message(AddProductStates.waiting_for_url)
@router.message(AddProductStates.waiting_for_pincodes)
async def receive_invalid_add_product_message(message: Message) -> None:
    await message.answer("Please send text to continue adding the product.")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_pincodes(value: str) -> list[str]:
    pincodes = [part.strip() for part in value.split(",")]
    unique_pincodes = list(dict.fromkeys(pincodes))
    if not unique_pincodes or any(not is_valid_pincode(pincode) for pincode in unique_pincodes):
        return []
    return unique_pincodes


def is_valid_pincode(value: str) -> bool:
    return len(value) == 6 and value.isdecimal() and value[0] != "0"
