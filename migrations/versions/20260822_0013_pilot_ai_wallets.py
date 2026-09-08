"""Pilot V1 AI wallet and credit ledger

Revision ID: 20260822_0013
Revises: 20260821_0012
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0013"
down_revision: Union[str, Sequence[str], None] = "20260821_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pilot_ai_wallets",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plan_code", sa.String(length=40), nullable=False, server_default="pilot"),
        sa.Column("credit_microeur", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("trial_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )

    op.create_table(
        "pilot_ai_wallet_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("amount_microeur", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pilot_ai_wallet_ledger_organization_id",
        "pilot_ai_wallet_ledger",
        ["organization_id"],
    )
    op.create_index(
        "ix_pilot_ai_wallet_ledger_created_at",
        "pilot_ai_wallet_ledger",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pilot_ai_wallet_ledger_created_at", table_name="pilot_ai_wallet_ledger")
    op.drop_index("ix_pilot_ai_wallet_ledger_organization_id", table_name="pilot_ai_wallet_ledger")
    op.drop_table("pilot_ai_wallet_ledger")
    op.drop_table("pilot_ai_wallets")
