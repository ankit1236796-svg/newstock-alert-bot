from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.entities import Marketplace, StockStatus

_STATUS_LEN: Final = 20
_MARKETPLACE_LEN: Final = 40


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trackings: Mapped[list["UserProductTrackingModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("marketplace", "product_id", name="uq_products_marketplace_product_id"),
        Index("idx_products_marketplace", "marketplace"),
        Index("idx_products_current_status", "current_status"),
        Index("idx_products_last_checked", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(String(_MARKETPLACE_LEN), nullable=False)
    product_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    current_status: Mapped[StockStatus] = mapped_column(String(_STATUS_LEN), nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pincodes: Mapped[list["ProductPincodeModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    trackings: Mapped[list["UserProductTrackingModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    stock_history: Mapped[list["StockHistoryModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductPincodeModel(Base):
    __tablename__ = "product_pincodes"
    __table_args__ = (
        UniqueConstraint("product_id", "pincode", name="uq_product_pincodes_product_id_pincode"),
        Index("idx_product_pincodes_product_id", "product_id"),
        Index("idx_product_pincodes_pincode", "pincode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    pincode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[ProductModel] = relationship(back_populates="pincodes")


class UserProductTrackingModel(Base):
    __tablename__ = "user_product_tracking"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product_tracking_user_product"),
        Index("idx_user_product_tracking_user_id", "user_id"),
        Index("idx_user_product_tracking_product_id", "product_id"),
        Index("idx_user_product_tracking_notifications", "notifications_enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    notifications_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_notified_status: Mapped[StockStatus | None] = mapped_column(String(_STATUS_LEN))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[UserModel] = relationship(back_populates="trackings")
    product: Mapped[ProductModel] = relationship(back_populates="trackings")


class StockHistoryModel(Base):
    __tablename__ = "stock_history"
    __table_args__ = (
        Index("idx_stock_history_product_id_changed_at", "product_id", "changed_at"),
        Index("idx_stock_history_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[StockStatus] = mapped_column(String(_STATUS_LEN), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[ProductModel] = relationship(back_populates="stock_history")
