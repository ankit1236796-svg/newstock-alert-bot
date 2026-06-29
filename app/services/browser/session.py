from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, async_playwright

from app.core.config import Settings


@asynccontextmanager
async def browser_session(settings: Settings) -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.browser_headless)
        try:
            yield browser
        finally:
            await browser.close()
