"""Harden Pilot V1 runtime schema compatibility

Revision ID: 20260822_0014
Revises: 20260822_0013
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260822_0014"
down_revision: Union[str, Sequence[str], None] = "20260822_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Older Pilot databases may already have these tables because the UI/runtime
    # created them idempotently before the canonical migration existed. Use
    # PostgreSQL IF NOT EXISTS so startup is safe in both fresh and existing DBs.
    op.execute(
        "ALTER TABLE pilot_ai_wallet_ledger "
        "ADD COLUMN IF NOT EXISTS provider_cost_microusd BIGINT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pilot_wallet_ledger_org_created "
        "ON pilot_ai_wallet_ledger (organization_id, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pilot_password_reset_tokens (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pilot_password_reset_user "
        "ON pilot_password_reset_tokens (user_id, created_at DESC)"
    )


def downgrade() -> None:
    # This migration is deliberately additive/self-healing for the isolated Pilot.
    # Downgrade leaves operational compatibility columns/tables in place.
    pass
