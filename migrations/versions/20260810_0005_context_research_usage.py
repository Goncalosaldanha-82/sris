"""Governed context-research web search accounting

Revision ID: 20260810_0005
Revises: 20260809_0004
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0005"
down_revision: Union[str, Sequence[str], None] = "20260809_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mi_ai_usage_periods",
        sa.Column(
            "web_search_calls",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mi_ai_usage_periods",
        sa.Column(
            "reserved_web_search_calls",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mi_ai_usage_events",
        sa.Column(
            "reserved_web_search_calls",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mi_ai_usage_events",
        sa.Column(
            "web_search_calls",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mi_ai_usage_events",
        sa.Column(
            "web_search_cost_microusd",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mi_ai_usage_events",
        sa.Column(
            "web_search_rate_microusd_per_call",
            sa.BigInteger(),
            nullable=False,
            server_default="10000",
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "mi_ai_usage_events", "web_search_rate_microusd_per_call"
    )
    op.drop_column("mi_ai_usage_events", "web_search_cost_microusd")
    op.drop_column("mi_ai_usage_events", "web_search_calls")
    op.drop_column("mi_ai_usage_events", "reserved_web_search_calls")
    op.drop_column("mi_ai_usage_periods", "reserved_web_search_calls")
    op.drop_column("mi_ai_usage_periods", "web_search_calls")
