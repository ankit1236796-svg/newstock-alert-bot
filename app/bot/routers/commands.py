from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.domain.entities import User
from app.domain.repositories import UserRepository

router = Router(name="commands")


@router.message(CommandStart())
async def start_command(message: Message, user_repository: UserRepository) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("I couldn't identify your Telegram user. Please try again.")
        return

    await user_repository.upsert(
        User(
            id=None,
            telegram_user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
        )
    )

    await message.answer(
        "Welcome to NewStock Alert Bot!\n\n"
        "I'll help you track product availability once tracking features are enabled. "
        "Use /help to see the available commands."
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Available commands:\n"
        "/start - Register and initialize your bot profile\n"
        "/help - Show this help message\n"
        "/add - Add a product to track\n"
        "/list - Show your tracked products\n"
        "/remove - Remove a tracked product\n"
        "/ping - Check whether the bot is responsive"
    )


@router.message(Command("ping"))
async def ping_command(message: Message) -> None:
    await message.answer("pong")
