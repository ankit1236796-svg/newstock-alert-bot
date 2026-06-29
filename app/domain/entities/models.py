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
    CURRENTLY_UNAVAILABLE = "currently_unavailable"
    DELIVERY_NOT_AVAILABLE = "delivery_not_available"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class User:
    id: int | None
    telegram_user_id: int
    username: str | None
    first_name: str | None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Product:
    id: int | None
    product_id: str
    marketplace: Marketplace
    product_url: str
    product_name: str
    current_status: StockStatus
    last_checked: datetime | None = None
    created_at: datetime | None = None
    current_price_paise: int | None = None
    delivery_availability_by_pincode: dict[str, bool] | None = None


@dataclass(frozen=True, slots=True)
class ProductPincode:
    id: int | None
    product_id: int
    pincode: str
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserProductTracking:
    id: int | None
    user_id: int
    product_id: int
    notifications_enabled: bool = True
    last_notified_status: StockStatus | None = None
    last_notified_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StockHistory:
    id: int | None
    product_id: int
    status: StockStatus
    changed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserDefaultPincode:
    id: int | None
    user_id: int
    pincode: str
    created_at: datetime | None = None
