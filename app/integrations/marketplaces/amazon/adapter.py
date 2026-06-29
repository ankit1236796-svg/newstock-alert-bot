import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

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
_PRICE_RE: Final[re.Pattern[str]] = re.compile(r"(?:₹|INR)\s*([0-9,]+(?:\.\d{1,2})?)")


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
    _playwright: Playwright | None = field(default=None, init=False, repr=False)
    _browsers: asyncio.Queue[Browser] = field(init=False, repr=False)
    _created: int = field(default=0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._browsers = asyncio.Queue(maxsize=self.max_browsers)

    async def acquire(self) -> Browser:
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            if not self._browsers.empty():
                browser = await self._browsers.get()
                if browser.is_connected():
                    return browser
                self._created -= 1
            if self._created < self.max_browsers:
                self._created += 1
                try:
                    return await self._playwright.chromium.launch(
                        headless=self.headless, timeout=self.launch_timeout_ms
                    )
                except Exception:
                    self._created -= 1
                    raise
        browser = await self._browsers.get()
        if browser.is_connected():
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


class AmazonMarketplaceAdapter(BaseMarketplace):
    marketplace = Marketplace.AMAZON

    def __init__(
        self,
        *,
        browser_pool: PlaywrightBrowserPool | None = None,
        headless: bool = True,
        timeout_ms: int = 15_000,
        retries: int = 2,
    ) -> None:
        self._browser_pool = browser_pool or PlaywrightBrowserPool(headless=headless)
        self._timeout_ms = timeout_ms
        self._retries = retries

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
                    "amazon_check_retryable_failure",
                    extra={
                        "attempt": attempt,
                        "max_attempts": self._retries + 1,
                        "product_url": product_url,
                        "error": repr(exc),
                    },
                )
                if attempt > self._retries:
                    break
                await asyncio.sleep(0.5 * attempt)
        raise RuntimeError("Amazon product check failed after retries") from last_error

    async def _check_product_once(
        self, product_url: str, pincodes: tuple[str, ...], attempt: int
    ) -> AmazonProductSnapshot:
        browser = await self._browser_pool.acquire()
        context = await browser.new_context(locale="en-IN")
        page = await context.new_page()
        page.set_default_timeout(self._timeout_ms)
        try:
            logger.info(
                "amazon_check_started",
                extra={"product_url": product_url, "pincodes": list(pincodes), "attempt": attempt},
            )
            await page.goto(product_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
            snapshot = await self._extract_snapshot(page, product_url, pincodes)
            logger.info(
                "amazon_check_completed",
                extra={
                    "product_id": snapshot.product_id,
                    "status": snapshot.current_stock_status.value,
                    "pincodes": list(pincodes),
                },
            )
            return snapshot
        finally:
            await context.close()
            await self._browser_pool.release(browser)

    async def _extract_snapshot(
        self, page: Page, product_url: str, pincodes: tuple[str, ...]
    ) -> AmazonProductSnapshot:
        text = await page.locator("body").inner_text(timeout=self._timeout_ms)
        name = await self._first_text(page, ["#productTitle", "#title", "h1"])
        image = await self._first_attribute(page, ["#landingImage", "#imgBlkFront"], "src")
        seller = await self._first_text(
            page,
            ["#sellerProfileTriggerId", "#merchant-info", "#tabular-buybox .tabular-buybox-text"],
        )
        price_text = await self._first_text(
            page, [".a-price .a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice"]
        )
        price_paise = self._parse_price(price_text or text)
        status = self._stock_status(text)
        product_id = self._product_id(product_url) or await self._first_attribute(
            page, ["input#ASIN"], "value"
        )
        deliveries = []
        for pincode in pincodes:
            deliveries.append(await self._check_delivery_for_pin(page, pincode))
        return AmazonProductSnapshot(
            product_name=name,
            marketplace=self.marketplace,
            product_id=product_id,
            product_image=image,
            seller_name=seller,
            current_price_paise=price_paise,
            current_stock_status=status,
            delivery_availability=tuple(deliveries),
            last_checked=datetime.now(UTC),
            raw_summary=self._summary(name, product_id, price_paise, status),
        )

    async def _check_delivery_for_pin(self, page: Page, pincode: str) -> AmazonDeliveryAvailability:
        selectors = [
            "#contextualIngressPtLabel_deliveryShortLine",
            "#deliveryBlockMessage",
            "#mir-layout-DELIVERY_BLOCK",
        ]
        before = " ".join(filter(None, [await self._first_text(page, selectors)]))
        try:
            await page.locator(
                "#contextualIngressPtLabel_deliveryShortLine, #deliver-to-address-text"
            ).first.click(timeout=3_000)
            await page.locator("#GLUXZipUpdateInput").fill(pincode, timeout=3_000)
            await page.locator("#GLUXZipUpdate").click(timeout=3_000)
            await page.wait_for_timeout(1_000)
        except PlaywrightError:
            logger.info("amazon_delivery_pin_form_unavailable", extra={"pincode": pincode})
        message = await self._first_text(page, selectors) or before
        unavailable = self._delivery_unavailable(message or "")
        return AmazonDeliveryAvailability(
            pincode=pincode, is_available=not unavailable, message=message
        )

    @staticmethod
    async def _first_text(page: Page, selectors: list[str]) -> str | None:
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count():
                text = (await locator.inner_text()).strip()
                if text:
                    return " ".join(text.split())
        return None

    @staticmethod
    async def _first_attribute(page: Page, selectors: list[str], name: str) -> str | None:
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count():
                value = await locator.get_attribute(name)
                if value:
                    return value
        return None

    @staticmethod
    def _product_id(url: str) -> str | None:
        match = _ASIN_RE.search(url)
        return match.group(1).upper() if match else None

    @staticmethod
    def _parse_price(text: str) -> int | None:
        match = _PRICE_RE.search(text)
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
        lowered = text.lower()
        if "currently unavailable" in lowered:
            return StockStatus.CURRENTLY_UNAVAILABLE
        if "out of stock" in lowered or "temporarily out of stock" in lowered:
            return StockStatus.OUT_OF_STOCK
        if "in stock" in lowered or "add to cart" in lowered or "buy now" in lowered:
            return StockStatus.IN_STOCK
        return StockStatus.UNKNOWN

    @staticmethod
    def _summary(
        name: str | None, product_id: str | None, price: int | None, status: StockStatus
    ) -> str:
        return (
            f"name={name!r} product_id={product_id!r} price_paise={price!r} status={status.value!r}"
        )
