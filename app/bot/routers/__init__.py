from aiogram import Router

from app.bot.routers import add_product, commands, list_products, remove_product


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(commands.router)
    router.include_router(add_product.router)
    router.include_router(list_products.router)
    router.include_router(remove_product.router)
    return router
