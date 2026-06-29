from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Marketplace(StrEnum):
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    CROMA = "croma"
    AJIO = "ajio"
    MEESHO = "meesho"
    ZEPTO = "zepto"
    INSTAMART = "instamart"
    BIGBASKET = "bigbasket"
    SAVANA = "savana"


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class User:
    id: int | None
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Product:
    id: int | None
    user_id: int
    marketplace: Marketplace
    product_url: str
    display_name: str
    target_price_paise: int | None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProductPincode:
    id: int | None
    product_id: int
    pincode: str
    is_active: bool
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StockCheck:
    id: int | None
    product_id: int
    pincode: str
    status: StockStatus
    price_paise: int | None
    raw_summary: str | None
    checked_at: datetime | None = None
