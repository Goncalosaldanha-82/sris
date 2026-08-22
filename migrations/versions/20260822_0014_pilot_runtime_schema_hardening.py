"""Harden Pilot V1 runtime schema compatibility

Revision ID: 20260822_0014
Revises: 20260822_0013
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0014"
down_revision: Union[str, Sequence[str], None] = "20260822_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    # Existing Railway databases may already contain additive Pilot objects
    # created by the runtime bootstrap. Inspect first so this migration is safe
    # on PostgreSQL and on the SQLite migration test used by CI.
    if "provider_cost_microusd" not in _column_names("pilot_ai_wallet_ledger"):
        op.add_column(
            "pilot_ai_wallet_ledger",
            sa.Column("provider_cost_microusd", sa.BigInteger(), nullable=True),
        )

    if "ix_pilot_wallet_ledger_org_created" not in _index_names("pilot_ai_wallet_ledger"):
        op.create_index(
            "ix_pilot_wallet_ledger_org_created",
            "pilot_ai_wallet_ledger",
            ["organization_id", "created_at"],
            unique=False,
        )

    inspector = sa.inspect(op.get_bind())
    if "pilot_password_reset_tokens" not in inspector.get_table_names():
        op.create_table(
            "pilot_password_reset_tokens",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )

    if "ix_pilot_password_reset_user" not in _index_names("pilot_password_reset_tokens"):
        op.create_index(
            "ix_pilot_password_reset_user",
            "pilot_password_reset_tokens",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    # Compatibility migration is intentionally additive for the isolated Pilot.
    pass
