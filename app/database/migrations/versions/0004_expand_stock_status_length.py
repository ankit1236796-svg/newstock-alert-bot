"""expand stock status columns

Revision ID: 0004_expand_stock_status_length
Revises: 0003_merge_user_pincodes_and_alert_state
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_expand_stock_status_length"
down_revision = "0003_merge_user_pincodes_and_alert_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column(
            "current_status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
    with op.batch_alter_table("user_product_tracking") as batch_op:
        batch_op.alter_column(
            "last_notified_status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
    with op.batch_alter_table("stock_history") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_history") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
    with op.batch_alter_table("user_product_tracking") as batch_op:
        batch_op.alter_column(
            "last_notified_status",
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column(
            "current_status",
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
