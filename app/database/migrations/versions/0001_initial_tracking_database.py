"""initial tracking database

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("marketplace", sa.String(length=40), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=False),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("current_status", sa.String(length=20), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("marketplace", "product_id", name="uq_products_marketplace_product_id"),
    )
    op.create_index("idx_products_marketplace", "products", ["marketplace"])
    op.create_index("idx_products_current_status", "products", ["current_status"])
    op.create_index("idx_products_last_checked", "products", ["last_checked"])
    op.create_table(
        "product_pincodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("pincode", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "pincode", name="uq_product_pincodes_product_id_pincode"),
    )
    op.create_index("idx_product_pincodes_product_id", "product_pincodes", ["product_id"])
    op.create_index("idx_product_pincodes_pincode", "product_pincodes", ["pincode"])
    op.create_table(
        "user_product_tracking",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_notified_status", sa.String(length=20), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_user_product_tracking_user_product"),
    )
    op.create_index("idx_user_product_tracking_user_id", "user_product_tracking", ["user_id"])
    op.create_index("idx_user_product_tracking_product_id", "user_product_tracking", ["product_id"])
    op.create_index(
        "idx_user_product_tracking_notifications",
        "user_product_tracking",
        ["notifications_enabled"],
    )
    op.create_table(
        "stock_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_stock_history_product_id_changed_at", "stock_history", ["product_id", "changed_at"]
    )
    op.create_index("idx_stock_history_status", "stock_history", ["status"])


def downgrade() -> None:
    op.drop_table("stock_history")
    op.drop_table("user_product_tracking")
    op.drop_table("product_pincodes")
    op.drop_table("products")
    op.drop_table("users")
