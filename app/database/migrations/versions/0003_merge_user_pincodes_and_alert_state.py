"""merge user default pincodes and alert state heads

Revision ID: 0003_merge_user_pincodes_and_alert_state
Revises: 0002_user_default_pincodes, 0002_alert_state
Create Date: 2026-06-29
"""

revision = "0003_merge_user_pincodes_and_alert_state"
down_revision = ("0002_user_default_pincodes", "0002_alert_state")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
