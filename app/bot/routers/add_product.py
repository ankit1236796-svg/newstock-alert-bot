from dataclasses import dataclass, field
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.domain.entities import Marketplace, User
from app.domain.repositories import (
    ProductPincodeRepository,
    ProductRepository,
    UserDefaultPincodeRepository,
    UserProductTrackingRepository,
    UserRepository,
)
from app.services.products.add_product import (
    AddProductCommand,
    AddProductService,
    infer_marketplace,
)

router = Router(name="add_product")
MAX_BULK_PRODUCTS = 25
_SINGLE_PRODUCT = "➕ Single Product"
_BULK_PRODUCTS = "📦 Bulk Products"
_DEFAULT_PINS = "⭐ Use Default PIN Codes"
_USE_SAVED_PINS = "✅ Yes"
_ENTER_NEW_PINS = "✏️ Enter New PIN Codes"


class AddProductStates(StatesGroup):
    waiting_for_mode = State()
    waiting_for_name = State()
    waiting_for_url = State()
    waiting_for_pincodes = State()
    waiting_for_bulk_urls = State()
    waiting_for_pin_choice = State()
    waiting_for_bulk_pin_choice = State()
    waiting_for_bulk_pincodes = State()


class DefaultPincodeStates(StatesGroup):
    waiting_for_pincodes = State()


@dataclass(frozen=True, slots=True)
class BulkUrlParseResult:
    urls: list[str] = field(default_factory=list)
    invalid_urls: list[str] = field(default_factory=list)
    unsupported_urls: list[str] = field(default_factory=list)
    duplicate_urls: list[str] = field(default_factory=list)
    too_many_count: int = 0


@router.message(Command("add"))
async def add_product_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddProductStates.waiting_for_mode)
    await message.answer(
        "How would you like to add products?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=_SINGLE_PRODUCT)],
                [KeyboardButton(text=_BULK_PRODUCTS)],
                [KeyboardButton(text=_DEFAULT_PINS)],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


@router.message(Command("pins"))
async def pins_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(DefaultPincodeStates.waiting_for_pincodes)
    await message.answer(
        "Please send one or more default PIN codes, one per line or separated by commas.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(DefaultPincodeStates.waiting_for_pincodes, F.text)
async def receive_default_pincodes(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    default_pincode_repository: UserDefaultPincodeRepository,
) -> None:
    pincodes = parse_pincodes(message.text or "")
    if not pincodes:
        await message.answer("Please send valid 6-digit PIN codes, for example: 560001, 110001.")
        return
    user = await _upsert_message_user(message, user_repository)
    if user is None or user.id is None:
        await message.answer("I couldn't identify your Telegram user. Please try /pins again.")
        await state.clear()
        return
    await default_pincode_repository.replace_for_user(user.id, pincodes)
    await state.clear()
    await message.answer(f"✅ Saved default PIN Codes: {', '.join(pincodes)}")


@router.message(AddProductStates.waiting_for_mode, F.text == _SINGLE_PRODUCT)
async def choose_single_product(message: Message, state: FSMContext) -> None:
    await state.update_data(use_default_pins=False)
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer("Please send the Product Name.", reply_markup=ReplyKeyboardRemove())


@router.message(AddProductStates.waiting_for_mode, F.text == _BULK_PRODUCTS)
async def choose_bulk_products(message: Message, state: FSMContext) -> None:
    await state.set_state(AddProductStates.waiting_for_bulk_urls)
    await message.answer(
        f"Please paste product URLs, one per line. Maximum {MAX_BULK_PRODUCTS} products.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AddProductStates.waiting_for_mode, F.text == _DEFAULT_PINS)
async def choose_default_pin_add(message: Message, state: FSMContext) -> None:
    await state.update_data(use_default_pins=True)
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer("Please send the Product Name.", reply_markup=ReplyKeyboardRemove())


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
async def receive_product_url(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    default_pincode_repository: UserDefaultPincodeRepository,
) -> None:
    product_url = _clean_text(message.text)
    if product_url is None or not is_valid_url(product_url):
        await message.answer("Please send a valid Product URL starting with http:// or https://.")
        return
    if detect_marketplace(product_url) is None:
        await message.answer("Unsupported website. Please send a supported product URL.")
        return
    await state.update_data(product_url=product_url)
    if await _maybe_ask_saved_pins(message, state, user_repository, default_pincode_repository):
        return
    await state.set_state(AddProductStates.waiting_for_pincodes)
    await message.answer(
        "Please send one or more PIN codes. You can separate multiple PIN codes with commas."
    )


@router.message(AddProductStates.waiting_for_bulk_urls, F.text)
async def receive_bulk_urls(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    default_pincode_repository: UserDefaultPincodeRepository,
) -> None:
    parsed = parse_bulk_urls(message.text or "")
    if not parsed.urls:
        await message.answer("No supported product URLs found. Please paste one URL per line.")
        return
    await state.update_data(bulk_urls=parsed.urls, bulk_parse=parsed)
    if await _maybe_ask_saved_pins(
        message, state, user_repository, default_pincode_repository, bulk=True
    ):
        return
    await state.set_state(AddProductStates.waiting_for_bulk_pincodes)
    await message.answer("Please send PIN codes once. They will be applied to every product.")


@router.message(AddProductStates.waiting_for_pin_choice, F.text == _USE_SAVED_PINS)
async def single_use_saved_pins(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    data = await state.get_data()
    await _add_single_product(
        message,
        state,
        list(data["saved_pins"]),
        user_repository,
        product_repository,
        pincode_repository,
        tracking_repository,
    )


@router.message(AddProductStates.waiting_for_pin_choice, F.text == _ENTER_NEW_PINS)
async def single_enter_new_pins(message: Message, state: FSMContext) -> None:
    await state.set_state(AddProductStates.waiting_for_pincodes)
    await message.answer(
        "Please send one or more PIN codes. You can separate multiple PIN codes with commas.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AddProductStates.waiting_for_bulk_pin_choice, F.text == _USE_SAVED_PINS)
async def bulk_use_saved_pins(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    data = await state.get_data()
    await _add_bulk_products(
        message,
        state,
        list(data["saved_pins"]),
        user_repository,
        product_repository,
        pincode_repository,
        tracking_repository,
    )


@router.message(AddProductStates.waiting_for_bulk_pin_choice, F.text == _ENTER_NEW_PINS)
async def bulk_enter_new_pins(message: Message, state: FSMContext) -> None:
    await state.set_state(AddProductStates.waiting_for_bulk_pincodes)
    await message.answer(
        "Please send PIN codes once. They will be applied to every product.",
        reply_markup=ReplyKeyboardRemove(),
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
    await _add_single_product(
        message,
        state,
        pincodes,
        user_repository,
        product_repository,
        pincode_repository,
        tracking_repository,
    )


@router.message(AddProductStates.waiting_for_bulk_pincodes, F.text)
async def receive_bulk_pincodes(
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
    await _add_bulk_products(
        message,
        state,
        pincodes,
        user_repository,
        product_repository,
        pincode_repository,
        tracking_repository,
    )


@router.message(AddProductStates.waiting_for_pin_choice)
@router.message(AddProductStates.waiting_for_bulk_pin_choice)
async def receive_invalid_pin_choice(message: Message) -> None:
    await message.answer("Please choose whether to use saved PIN codes or enter new PIN codes.")


@router.message(AddProductStates.waiting_for_name)
@router.message(AddProductStates.waiting_for_url)
@router.message(AddProductStates.waiting_for_pincodes)
@router.message(AddProductStates.waiting_for_mode)
@router.message(AddProductStates.waiting_for_pin_choice)
@router.message(AddProductStates.waiting_for_bulk_urls)
@router.message(AddProductStates.waiting_for_bulk_pincodes)
@router.message(DefaultPincodeStates.waiting_for_pincodes)
async def receive_invalid_add_product_message(message: Message) -> None:
    await message.answer("Please send text to continue adding the product.")


async def _add_single_product(
    message: Message,
    state: FSMContext,
    pincodes: list[str],
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    user = await _upsert_message_user(message, user_repository)
    if user is None:
        await message.answer("I couldn't identify your Telegram user. Please try /add again.")
        await state.clear()
        return
    data = await state.get_data()
    service = AddProductService(product_repository, pincode_repository, tracking_repository)
    added = await service.add_product(
        AddProductCommand(
            user=user,
            product_name=str(data["product_name"]),
            product_url=str(data["product_url"]),
            pincodes=pincodes,
        )
    )
    await state.clear()
    status = "⚠️ Already Tracked" if added.already_tracked else "✅ Product Added"
    await message.answer(
        (
            f"{status}\n\n"
            f"Product: {added.product.product_name}\n"
            f"URL: {added.product.product_url}\n"
            f"PIN Codes: {', '.join(added.pincodes)}"
        ),
        reply_markup=ReplyKeyboardRemove(),
    )


async def _add_bulk_products(
    message: Message,
    state: FSMContext,
    pincodes: list[str],
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pincode_repository: ProductPincodeRepository,
    tracking_repository: UserProductTrackingRepository,
) -> None:
    user = await _upsert_message_user(message, user_repository)
    if user is None:
        await message.answer("I couldn't identify your Telegram user. Please try /add again.")
        await state.clear()
        return
    data = await state.get_data()
    parsed: BulkUrlParseResult = data["bulk_parse"]
    service = AddProductService(product_repository, pincode_repository, tracking_repository)
    added = already = 0
    for url in parsed.urls:
        result = await service.add_product(
            AddProductCommand(
                user=user,
                product_name=build_bulk_product_name(url),
                product_url=url,
                pincodes=pincodes,
            )
        )
        if result.already_tracked:
            already += 1
        else:
            added += 1
    await state.clear()
    await message.answer(
        format_bulk_summary(
            added,
            already,
            len(parsed.invalid_urls),
            len(parsed.unsupported_urls),
            len(parsed.duplicate_urls),
            parsed.too_many_count,
        ),
        reply_markup=ReplyKeyboardRemove(),
    )


async def _maybe_ask_saved_pins(
    message: Message,
    state: FSMContext,
    user_repository: UserRepository,
    default_pincode_repository: UserDefaultPincodeRepository,
    bulk: bool = False,
) -> bool:
    user = await _upsert_message_user(message, user_repository)
    if user is None or user.id is None:
        return False
    saved = await default_pincode_repository.list_for_user(user.id)
    pins = [item.pincode for item in saved]
    if not pins:
        return False
    await state.update_data(saved_pins=pins)
    await state.set_state(
        AddProductStates.waiting_for_bulk_pin_choice
        if bulk
        else AddProductStates.waiting_for_pin_choice
    )
    await message.answer(
        "Use saved PIN codes?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=_USE_SAVED_PINS)],
                [KeyboardButton(text=_ENTER_NEW_PINS)],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return True


async def _upsert_message_user(message: Message, user_repository: UserRepository) -> User | None:
    telegram_user = message.from_user
    if telegram_user is None:
        return None
    return await user_repository.upsert(
        User(None, telegram_user.id, telegram_user.username, telegram_user.first_name)
    )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def detect_marketplace(product_url: str) -> Marketplace | None:
    try:
        return infer_marketplace(product_url)
    except ValueError:
        return None


def parse_bulk_urls(value: str) -> BulkUrlParseResult:
    valid: list[str] = []
    invalid: list[str] = []
    unsupported: list[str] = []
    duplicates: list[str] = []
    for raw in value.splitlines():
        url = raw.strip()
        if not url:
            continue
        if not is_valid_url(url):
            invalid.append(url)
            continue
        if detect_marketplace(url) is None:
            unsupported.append(url)
            continue
        if url in valid:
            duplicates.append(url)
            continue
        valid.append(url)
    too_many = max(0, len(valid) - MAX_BULK_PRODUCTS)
    return BulkUrlParseResult(valid[:MAX_BULK_PRODUCTS], invalid, unsupported, duplicates, too_many)


def parse_pincodes(value: str) -> list[str]:
    parts = value.replace("\n", ",").split(",")
    pincodes = [part.strip() for part in parts if part.strip()]
    unique_pincodes = list(dict.fromkeys(pincodes))
    if not unique_pincodes or any(not is_valid_pincode(pincode) for pincode in unique_pincodes):
        return []
    return unique_pincodes


def is_valid_pincode(value: str) -> bool:
    return len(value) == 6 and value.isdecimal() and value[0] != "0"


def build_bulk_product_name(url: str) -> str:
    marketplace = detect_marketplace(url)
    label = marketplace.value.title() if marketplace else "Product"
    return f"{label} Product"


def format_bulk_summary(
    added: int,
    already_tracked: int,
    invalid_urls: int,
    unsupported_urls: int,
    duplicate_urls: int = 0,
    too_many_urls: int = 0,
) -> str:
    lines = [
        f"✅ Added: {added}",
        f"⚠️ Already Tracked: {already_tracked}",
        f"❌ Invalid URLs: {invalid_urls}",
        f"❌ Unsupported Websites: {unsupported_urls}",
    ]
    if duplicate_urls:
        lines.append(f"⚠️ Duplicate URLs Removed: {duplicate_urls}")
    if too_many_urls:
        lines.append(f"⚠️ Over Limit Skipped: {too_many_urls}")
    return "\n".join(lines)
