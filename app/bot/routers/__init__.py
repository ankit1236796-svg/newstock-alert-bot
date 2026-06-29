from aiogram import Router

from app.bot.routers import add_product, commands


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(commands.router)
    router.include_router(add_product.router)
    return router
