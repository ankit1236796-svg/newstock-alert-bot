"""add user default pincodes

Revision ID: 0002_user_default_pincodes
Revises: 0001_initial
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_user_default_pincodes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_default_pincodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pincode", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "pincode", name="uq_user_default_pincodes_user_pincode"),
    )
    op.create_index("idx_user_default_pincodes_user_id", "user_default_pincodes", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_user_default_pincodes_user_id", table_name="user_default_pincodes")
    op.drop_table("user_default_pincodes")
