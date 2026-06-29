"""add product alert state

Revision ID: 0002_alert_state
Revises: 0001_initial
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_alert_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("current_price_paise", sa.Integer(), nullable=True))
    op.add_column(
        "products", sa.Column("delivery_availability_by_pincode", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("products", "delivery_availability_by_pincode")
    op.drop_column("products", "current_price_paise")
