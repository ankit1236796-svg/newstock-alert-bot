"""Marketplace extension contracts."""

from .base import AbstractMarketplace, BaseMarketplace
from .models import ProductLookup, ProductSnapshot, StockStatus

__all__ = [
    "AbstractMarketplace",
    "BaseMarketplace",
    "ProductLookup",
    "ProductSnapshot",
    "StockStatus",
]
