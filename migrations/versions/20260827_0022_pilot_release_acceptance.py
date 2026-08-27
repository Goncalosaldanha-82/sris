"""Add build-scoped external-pilot acceptance evidence.

Revision ID: 20260827_0022
Revises: 20260826_0021
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_0022"
down_revision: Union[str, Sequence[str], None] = "20260826_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pilot_release_acceptances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("build", sa.String(length=120), nullable=False),
        sa.Column("check_key", sa.String(length=80), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("tested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "build",
            "check_key",
            name="uq_pilot_release_acceptance_org_build_check",
        ),
    )
    op.create_index(
        "ix_pilot_release_acceptances_organization_id",
        "pilot_release_acceptances",
        ["organization_id"],
    )
    op.create_index(
        "ix_pilot_release_acceptances_build",
        "pilot_release_acceptances",
        ["build"],
    )
    op.create_index(
        "ix_pilot_release_acceptances_check_key",
        "pilot_release_acceptances",
        ["check_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_pilot_release_acceptances_check_key", table_name="pilot_release_acceptances")
    op.drop_index("ix_pilot_release_acceptances_build", table_name="pilot_release_acceptances")
    op.drop_index("ix_pilot_release_acceptances_organization_id", table_name="pilot_release_acceptances")
    op.drop_table("pilot_release_acceptances")
