from aiogram import Router

from app.bot.routers import commands


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(commands.router)
    return router
