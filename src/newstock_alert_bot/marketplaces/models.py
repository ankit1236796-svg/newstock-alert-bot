"""Shared marketplace data contracts.

These models are intentionally marketplace-agnostic so new shopping websites can be
plugged into the bot without changing downstream alerting code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class StockStatus(str, Enum):
    """Normalized stock states returned by every marketplace adapter."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LIMITED_STOCK = "limited_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """Common product data model returned by all marketplace adapters."""

    product_name: str
    product_url: str
    product_id: str
    current_price: Optional[Decimal]
    mrp: Optional[Decimal]
    discount_percentage: Optional[Decimal]
    stock_status: StockStatus
    delivery_available: bool
    delivery_pin_code: Optional[str]
    seller_name: Optional[str]
    image_url: Optional[str]
    marketplace_name: str
    last_checked_time: datetime


@dataclass(frozen=True, slots=True)
class ProductLookup:
    """Input contract for checking a product on any marketplace."""

    product_url: str
    delivery_pin_code: Optional[str] = None
    product_id: Optional[str] = None
