"""Make monthly AI thresholds non-blocking unless explicitly enforced

Revision ID: 20260815_0011
Revises: 20260815_0010
Create Date: 2026-08-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_0011"
down_revision: Union[str, Sequence[str], None] = "20260815_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mi_ai_organization_policies",
        sa.Column(
            "enforce_monthly_limits",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "mi_ai_organization_policies",
        "enforce_monthly_limits",
    )
