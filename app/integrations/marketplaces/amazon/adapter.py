import asyncio
import logging
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Final, Literal

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.domain.entities import Marketplace, StockStatus
from app.integrations.marketplaces.base import (
    BaseMarketplace,
    MarketplaceCheckRequest,
    MarketplaceCheckResult,
)

logger = logging.getLogger(__name__)

_AMAZON_HOST_RE: Final[re.Pattern[str]] = re.compile(r"amazon\.in|amzn\.in", re.I)
_ASIN_RE: Final[re.Pattern[str]] = re.compile(
    r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)", re.I
)
_PRICE_RE: Final[re.Pattern[str]] = re.compile(r"(?:₹|INR|Rs\.?)\s*([0-9,]+(?:\.\d{1,2})?)", re.I)
_PRICE_WITHOUT_CURRENCY_RE: Final[re.Pattern[str]] = re.compile(r"^\s*([0-9,]+(?:\.\d{1,2})?)\s*$")
_DEFAULT_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class AmazonDeliveryAvailability:
    pincode: str
    is_available: bool
    message: str | None = None


@dataclass(frozen=True, slots=True)
class AmazonProductSnapshot:
    product_name: str | None
    marketplace: Marketplace
    product_id: str | None
    product_image: str | None
    seller_name: str | None
    current_price_paise: int | None
    current_stock_status: StockStatus
    delivery_availability: tuple[AmazonDeliveryAvailability, ...]
    last_checked: datetime
    raw_summary: str | None = None


@dataclass(slots=True)
class PlaywrightBrowserPool:
    headless: bool = True
    max_browsers: int = 1
    launch_timeout_ms: int = 30_000
    user_agent: str = _DEFAULT_USER_AGENT
    _playwright: Playwright | None = field(default=None, init=False, repr=False)
    _browsers: asyncio.Queue[Browser] = field(init=False, repr=False)
    _created: int = field(default=0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.max_browsers = max(1, self.max_browsers)
        self._browsers = asyncio.Queue(maxsize=self.max_browsers)

    async def acquire(self) -> Browser:
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            while not self._browsers.empty():
                browser = await self._browsers.get()
                if browser.is_connected():
                    logger.info("amazon_browser_reused", extra={"pool_size": self._created})
                    return browser
                self._created -= 1
            if self._created < self.max_browsers:
                self._created += 1
                logger.info(
                    "amazon_browser_launching",
                    extra={"pool_size": self._created, "max_browsers": self.max_browsers},
                )
                try:
                    return await self._playwright.chromium.launch(
                        headless=self.headless, timeout=self.launch_timeout_ms
                    )
                except Exception:
                    self._created -= 1
                    raise
        browser = await self._browsers.get()
        if browser.is_connected():
            logger.info("amazon_browser_reused", extra={"pool_size": self._created})
            return browser
        async with self._lock:
            self._created -= 1
        return await self.acquire()

    async def release(self, browser: Browser) -> None:
        if browser.is_connected():
            await self._browsers.put(browser)
            return
        async with self._lock:
            self._created -= 1

    async def close(self) -> None:
        while not self._browsers.empty():
            browser = await self._browsers.get()
            if browser.is_connected():
                await browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._created = 0
        logger.info("amazon_browser_pool_closed")


class AmazonMarketplaceAdapter(BaseMarketplace):
    marketplace = Marketplace.AMAZON

    def __init__(
        self,
        *,
        browser_pool: PlaywrightBrowserPool | None = None,
        headless: bool = True,
        timeout_ms: int = 15_000,
        retries: int = 2,
        retry_backoff_seconds: float = 0.75,
        min_delay_ms: int = 250,
        max_delay_ms: int = 1_500,
        user_agent: str = _DEFAULT_USER_AGENT,
    ) -> None:
        self._browser_pool = browser_pool or PlaywrightBrowserPool(
            headless=headless, user_agent=user_agent
        )
        self._timeout_ms = timeout_ms
        self._retries = max(0, retries)
        self._retry_backoff_seconds = retry_backoff_seconds
        self._min_delay_ms = min_delay_ms
        self._max_delay_ms = max(min_delay_ms, max_delay_ms)
        self._user_agent = user_agent

    async def close(self) -> None:
        await self._browser_pool.close()

    async def _check_stock(self, request: MarketplaceCheckRequest) -> MarketplaceCheckResult:
        snapshot = await self.check_product(request.product_url, [request.pincode])
        return MarketplaceCheckResult(
            status=snapshot.current_stock_status,
            price_paise=snapshot.current_price_paise,
            raw_summary=snapshot.raw_summary,
        )

    async def check_product(
        self, product_url: str, pincodes: Iterable[str]
    ) -> AmazonProductSnapshot:
        if not _AMAZON_HOST_RE.search(product_url):
            raise ValueError("AmazonMarketplaceAdapter only supports Amazon India URLs")
        normalized_pins = tuple(dict.fromkeys(pin.strip() for pin in pincodes if pin.strip()))
        if not normalized_pins:
            raise ValueError("At least one PIN code is required")
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 2):
            try:
                return await self._check_product_once(product_url, normalized_pins, attempt)
            except (PlaywrightTimeoutError, PlaywrightError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "amazon_check_retry_attempt",
                    extra={
                        "attempt": attempt,
                        "max_attempts": self._retries + 1,
                        "product_url": product_url,
                        "error": repr(exc),
                    },
                )
                if attempt > self._retries:
                    break
                delay = self._retry_backoff_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, self._retry_backoff_seconds)
                await asyncio.sleep(delay)
        logger.error("amazon_check_failed", extra={"product_url": product_url})
        raise RuntimeError("Amazon product check failed after retries") from last_error

    async def _check_product_once(
        self, product_url: str, pincodes: tuple[str, ...], attempt: int
    ) -> AmazonProductSnapshot:
        browser = await self._browser_pool.acquire()
        context: BrowserContext | None = None
        started = perf_counter()
        try:
            context = await browser.new_context(locale="en-IN", user_agent=self._user_agent)
            page = await context.new_page()
            page.set_default_timeout(self._timeout_ms)
            page.set_default_navigation_timeout(self._timeout_ms)
            logger.info(
                "amazon_check_started",
                extra={"product_url": product_url, "pincodes": list(pincodes), "attempt": attempt},
            )
            await self._human_delay()
            await page.goto(product_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            await self._wait_for_product_content(page)
            snapshot = await self._extract_snapshot(page, product_url, pincodes)
            logger.info(
                "amazon_check_succeeded",
                extra={
                    "product_id": snapshot.product_id,
                    "status": snapshot.current_stock_status.value,
                    "pincodes": list(pincodes),
                    "duration_seconds": round(perf_counter() - started, 3),
                },
            )
            return snapshot
        finally:
            try:
                if context is not None:
                    await context.close()
            finally:
                await self._browser_pool.release(browser)

    async def _extract_snapshot(
        self, page: Page, product_url: str, pincodes: tuple[str, ...]
    ) -> AmazonProductSnapshot:
        text = await self._safe_body_text(page)
        name = await self._first_text(page, ["#productTitle", "#title", "#titleSection h1", "h1"])
        image = await self._first_attribute(
            page, ["#landingImage", "#imgBlkFront", "#main-image", "img[data-old-hires]"], "src"
        )
        seller = await self._first_text(
            page,
            [
                "#sellerProfileTriggerId",
                "#merchant-info",
                "#tabular-buybox .tabular-buybox-text",
                "#buybox-tabular .tabular-buybox-text",
            ],
        )
        price_text = await self._current_price_text(page)
        availability_text = await self._availability_text(page)
        status = self._stock_status(availability_text or text)
        price_paise = self._parse_price(price_text or "")
        if price_paise is not None and status is StockStatus.UNKNOWN:
            status = StockStatus.IN_STOCK
        if price_paise is None and status is not StockStatus.CURRENTLY_UNAVAILABLE:
            price_paise = self._parse_price(text)
        product_id = self._product_id(product_url) or await self._first_attribute(
            page, ["input#ASIN", "input[name='ASIN']"], "value"
        )
        deliveries = [await self._check_delivery_for_pin(page, pin) for pin in pincodes]
        return AmazonProductSnapshot(
            name,
            self.marketplace,
            product_id,
            image,
            seller,
            price_paise,
            status,
            tuple(deliveries),
            datetime.now(UTC),
            self._summary(name, product_id, price_paise, status),
        )

    async def _check_delivery_for_pin(self, page: Page, pincode: str) -> AmazonDeliveryAvailability:
        selectors = [
            "#contextualIngressPtLabel_deliveryShortLine",
            "#deliveryBlockMessage",
            "#mir-layout-DELIVERY_BLOCK",
            "#ddmDeliveryMessage",
        ]
        before = await self._first_text(page, selectors)
        try:
            trigger = page.locator(
                "#contextualIngressPtLabel_deliveryShortLine, #deliver-to-address-text, "
                "#nav-global-location-popover-link"
            ).first
            if await trigger.count():
                await trigger.click(timeout=min(3_000, self._timeout_ms))
                await self._human_delay()
                await page.locator("#GLUXZipUpdateInput, input[name='zipCode']").first.fill(
                    pincode, timeout=min(3_000, self._timeout_ms)
                )
                await page.locator(
                    "#GLUXZipUpdate, input[aria-labelledby='GLUXZipUpdate']"
                ).first.click(timeout=min(3_000, self._timeout_ms))
                await self._human_delay()
            else:
                logger.info("amazon_delivery_pin_trigger_unavailable", extra={"pincode": pincode})
        except PlaywrightError as exc:
            logger.info(
                "amazon_delivery_pin_form_unavailable",
                extra={"pincode": pincode, "error": repr(exc)},
            )
        message = await self._first_text(page, selectors) or before
        unavailable = self._delivery_unavailable(message or "")
        return AmazonDeliveryAvailability(pincode, not unavailable, message)

    async def _human_delay(self) -> None:
        await asyncio.sleep(random.uniform(self._min_delay_ms, self._max_delay_ms) / 1000)

    async def _wait_for_product_content(self, page: Page) -> None:
        selector = self._product_content_selector()
        timeout = min(self._timeout_ms, 8_000)
        last_error: PlaywrightTimeoutError | None = None
        for attempt in range(1, 3):
            try:
                await page.wait_for_selector(selector, state="attached", timeout=timeout)
                logger.info("amazon_product_content_ready", extra={"attempt": attempt})
                await self._settle_lazy_product_content(page)
                return
            except PlaywrightTimeoutError as exc:
                last_error = exc
                logger.info(
                    "amazon_product_content_timeout",
                    extra={"attempt": attempt, "selector": selector},
                )
                await self._nudge_lazy_product_page(page)
                if attempt == 1:
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=self._timeout_ms)
                    except PlaywrightTimeoutError:
                        logger.info("amazon_load_state_timeout", extra={"state": "reload"})
        if last_error is not None:
            raise last_error

    @staticmethod
    def _product_content_selector() -> str:
        return ", ".join(
            [
                "#dp",
                "#centerCol",
                "#title",
                "#productTitle",
                "#titleSection h1",
                "#ppd",
                "#availability",
                "#availability_feature_div",
                "#buybox",
                "#buybox_feature_div",
                "#desktop_buybox",
                "#corePriceDisplay_desktop_feature_div",
                "#corePrice_feature_div",
                "#apex_desktop",
            ]
        )

    async def _settle_lazy_product_content(self, page: Page) -> None:
        await self._nudge_lazy_product_page(page)
        try:
            await page.wait_for_timeout(500)
        except PlaywrightError:
            return

    async def _nudge_lazy_product_page(self, page: Page) -> None:
        try:
            await page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 900))")
            await page.wait_for_timeout(250)
            await page.evaluate("window.scrollTo(0, 0)")
        except PlaywrightError:
            return

    async def _safe_load_state(
        self, page: Page, state: Literal["domcontentloaded", "load", "networkidle"]
    ) -> None:
        try:
            await page.wait_for_load_state(state, timeout=min(self._timeout_ms, 5_000))
        except PlaywrightTimeoutError:
            logger.info("amazon_load_state_timeout", extra={"state": state})

    async def _safe_body_text(self, page: Page) -> str:
        try:
            return await page.locator("body").inner_text(timeout=self._timeout_ms)
        except PlaywrightError:
            return ""

    @staticmethod
    async def _first_text(page: Page, selectors: list[str]) -> str | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count():
                    text = (await locator.inner_text(timeout=2_000)).strip()
                    if text:
                        return " ".join(text.split())
            except PlaywrightError:
                continue
        return None

    async def _availability_text(self, page: Page) -> str | None:
        selectors = [
            "#availability",
            "#availabilityInsideBuyBox_feature_div",
            "#availability_feature_div",
            "#outOfStock",
            "#desktop_qualifiedBuyBox",
            "#buybox",
            "#buybox_feature_div",
            "#desktop_buybox",
            "#mobile_buybox",
            "#addToCart",
            "#addToCart_feature_div",
            "#exports_desktop_qualifiedBuybox_tlc_feature_div",
            "#merchant-info",
            "#tabular-buybox",
            "#buybox-tabular",
            "#olp_feature_div",
            "#moreBuyingChoices_feature_div",
            "#all-offers-display",
            "#buybox-see-all-buying-choices",
            "#fresh-merchant-info",
            "#almAvailability",
            "#almBuyBox",
            "#pantryAvailability",
            "#snsAvailability",
            "#deliveryBlockMessage",
            "#mir-layout-DELIVERY_BLOCK",
            "span.a-button:has(input[name='submit.add-to-cart'])",
            "span.a-button:has(input[name='submit.buy-now'])",
            "input[name='submit.add-to-cart']",
            "input[name='submit.buy-now']",
        ]
        parts = await self._texts_for_selectors(page, selectors)
        disabled = await self._disabled_purchase_text(page)
        if disabled:
            parts.append(disabled)
        return " ".join(dict.fromkeys(parts)) or None

    async def _texts_for_selectors(self, page: Page, selectors: list[str]) -> list[str]:
        parts: list[str] = []
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = min(await locator.count(), 5)
                for index in range(count):
                    text = (await locator.nth(index).inner_text(timeout=2_000)).strip()
                    if text:
                        parts.append(" ".join(text.split()))
            except PlaywrightError:
                continue
        return parts

    async def _disabled_purchase_text(self, page: Page) -> str | None:
        selectors = [
            "#add-to-cart-button",
            "#buy-now-button",
            "input[name='submit.add-to-cart']",
            "input[name='submit.buy-now']",
        ]
        labels: list[str] = []
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if not await locator.count():
                    continue
                disabled = await locator.get_attribute("disabled", timeout=2_000)
                aria_disabled = await locator.get_attribute("aria-disabled", timeout=2_000)
                value = await locator.get_attribute("value", timeout=2_000)
                label = await locator.get_attribute("aria-label", timeout=2_000)
                if value or label:
                    labels.append(value or label or "")
                if disabled is not None or aria_disabled == "true":
                    labels.append("purchase button disabled")
            except PlaywrightError:
                continue
        return " ".join(labels) or None

    async def _current_price_text(self, page: Page) -> str | None:
        selectors = [
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
            "#corePrice_feature_div .a-price .a-offscreen",
            "#corePrice_feature_div .a-price-whole",
            "#apex_desktop .a-price .a-offscreen",
            "#apex_desktop .a-price-whole",
            "#tp_price_block_total_price_ww .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            "#price_inside_buybox",
            "#newBuyBoxPrice",
            "#sns-base-price .a-offscreen",
            "#buyNewSection .a-color-price",
            "#usedBuySection .a-color-price",
            "#olp_feature_div .a-color-price",
            "#moreBuyingChoices_feature_div .a-color-price",
            "#corePriceDisplay_mobile_feature_div .a-price .a-offscreen",
            "#corePriceDisplay_mobile_feature_div .a-price-whole",
            ".reinventPricePriceToPayMargin .a-price .a-offscreen",
            ".priceToPay .a-offscreen",
            ".a-price[data-a-color='price'] .a-offscreen",
            ".a-price .a-offscreen",
        ]
        for selector in selectors:
            for text in await self._texts_for_selectors(page, [selector]):
                price = self._parse_price(text) or self._parse_price_without_currency(text)
                if price is not None:
                    has_currency = "₹" in text or "inr" in text.lower() or "rs" in text.lower()
                    return text if has_currency else f"₹{text}"
        composed = await self._composed_price_text(page)
        if composed:
            return composed
        return None

    async def _composed_price_text(self, page: Page) -> str | None:
        containers = [
            "#corePriceDisplay_desktop_feature_div",
            "#corePrice_feature_div",
            "#apex_desktop",
            "#corePriceDisplay_mobile_feature_div",
            ".priceToPay",
        ]
        for container in containers:
            whole = await self._first_text(page, [f"{container} .a-price-whole"])
            if not whole:
                continue
            fraction = await self._first_text(page, [f"{container} .a-price-fraction"]) or "00"
            whole = whole.replace(".", "").strip()
            return f"₹{whole}.{fraction}"
        return None

    @staticmethod
    async def _first_attribute(page: Page, selectors: list[str], name: str) -> str | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count():
                    value = await locator.get_attribute(name, timeout=2_000)
                    if value:
                        return value
            except PlaywrightError:
                continue
        return None

    @staticmethod
    def _product_id(url: str) -> str | None:
        match = _ASIN_RE.search(url)
        return match.group(1).upper() if match else None

    @staticmethod
    def _parse_price(text: str) -> int | None:
        matches = list(_PRICE_RE.finditer(text))
        if not matches:
            return None
        return int(round(float(matches[0].group(1).replace(",", "")) * 100))

    @staticmethod
    def _parse_price_without_currency(text: str) -> int | None:
        match = _PRICE_WITHOUT_CURRENCY_RE.search(text.replace("₹", ""))
        if not match:
            return None
        return int(round(float(match.group(1).replace(",", "")) * 100))

    @staticmethod
    def _delivery_unavailable(text: str) -> bool:
        lowered = text.lower()
        return any(
            token in lowered
            for token in ["cannot be shipped", "not deliver", "not available", "unavailable"]
        )

    @staticmethod
    def _stock_status(text: str) -> StockStatus:
        lowered = " ".join(text.lower().split())
        unavailable_patterns = [
            "currently unavailable",
            "we don't know when or if this item will be back in stock",
            "we do not know when or if this item will be back in stock",
        ]
        if any(pattern in lowered for pattern in unavailable_patterns):
            return StockStatus.CURRENTLY_UNAVAILABLE
        temporarily_unavailable_patterns = [
            "temporarily out of stock",
            "temporarily unavailable",
        ]
        if any(pattern in lowered for pattern in temporarily_unavailable_patterns):
            return StockStatus.TEMPORARILY_UNAVAILABLE
        out_of_stock_patterns = [
            "out of stock",
            "sold out",
            "unavailable from this seller",
            "no sellers are currently delivering",
            "no featured offers available",
            "purchase button disabled",
        ]
        if any(pattern in lowered for pattern in out_of_stock_patterns):
            return StockStatus.OUT_OF_STOCK
        in_stock_patterns = [
            "in stock",
            "only ",
            "left in stock",
            "add to cart",
            "buy now",
            "available to ship",
            "fulfilled by amazon",
            "free delivery",
            "fastest delivery",
            "get it by",
            "get it tomorrow",
            "see all buying options",
        ]
        if any(pattern in lowered for pattern in in_stock_patterns):
            return StockStatus.IN_STOCK
        return StockStatus.UNKNOWN

    @staticmethod
    def _summary(
        name: str | None, product_id: str | None, price: int | None, status: StockStatus
    ) -> str:
        return (
            f"name={name!r} product_id={product_id!r} price_paise={price!r} status={status.value!r}"
        )
