"""Per-organization AI usage governance and cost ledger

Revision ID: 20260808_0003
Revises: 20260808_0002
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0003"
down_revision: Union[str, Sequence[str], None] = "20260808_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mi_ai_organization_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monthly_request_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column(
            "monthly_input_token_limit", sa.BigInteger(), nullable=False, server_default="250000"
        ),
        sa.Column(
            "monthly_output_token_limit", sa.BigInteger(), nullable=False, server_default="50000"
        ),
        sa.Column(
            "monthly_budget_microusd", sa.BigInteger(), nullable=False, server_default="5000000"
        ),
        sa.Column(
            "per_request_input_token_limit", sa.Integer(), nullable=False, server_default="60000"
        ),
        sa.Column(
            "per_request_output_token_limit", sa.Integer(), nullable=False, server_default="3000"
        ),
        sa.Column(
            "max_concurrent_requests", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index(
        "ix_mi_ai_organization_policies_organization_id",
        "mi_ai_organization_policies",
        ["organization_id"],
        unique=True,
    )

    op.create_table(
        "mi_ai_usage_periods",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_microusd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("active_reservations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "reserved_input_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "reserved_output_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "reserved_cost_microusd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "period_start",
            name="uq_mi_ai_usage_period_org_month",
        ),
    )
    op.create_index(
        "ix_mi_ai_usage_periods_organization_id",
        "mi_ai_usage_periods",
        ["organization_id"],
    )
    op.create_index(
        "ix_mi_ai_usage_periods_period_start",
        "mi_ai_usage_periods",
        ["period_start"],
    )

    op.create_table(
        "mi_ai_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_run_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="reserved"),
        sa.Column("provider", sa.String(length=80), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("provider_response_id", sa.String(length=200), nullable=True),
        sa.Column(
            "input_count_method", sa.String(length=40), nullable=False, server_default="conservative"
        ),
        sa.Column("reserved_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reserved_output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reserved_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_microusd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("cost_basis", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("input_rate_microusd_per_million", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_rate_microusd_per_million", sa.BigInteger(), nullable=False),
        sa.Column("output_rate_microusd_per_million", sa.BigInteger(), nullable=False),
        sa.Column("price_multiplier_bps", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("pricing_source", sa.String(length=1000), nullable=False),
        sa.Column("pricing_effective_date", sa.String(length=20), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["intelligence_run_id"], ["mi_intelligence_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intelligence_run_id"),
    )
    op.create_index(
        "ix_mi_ai_usage_events_organization_id",
        "mi_ai_usage_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_mi_ai_usage_events_intelligence_run_id",
        "mi_ai_usage_events",
        ["intelligence_run_id"],
        unique=True,
    )
    op.create_index(
        "ix_mi_ai_usage_events_period_start", "mi_ai_usage_events", ["period_start"]
    )
    op.create_index("ix_mi_ai_usage_events_status", "mi_ai_usage_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_mi_ai_usage_events_status", table_name="mi_ai_usage_events")
    op.drop_index("ix_mi_ai_usage_events_period_start", table_name="mi_ai_usage_events")
    op.drop_index(
        "ix_mi_ai_usage_events_intelligence_run_id", table_name="mi_ai_usage_events"
    )
    op.drop_index("ix_mi_ai_usage_events_organization_id", table_name="mi_ai_usage_events")
    op.drop_table("mi_ai_usage_events")
    op.drop_index("ix_mi_ai_usage_periods_period_start", table_name="mi_ai_usage_periods")
    op.drop_index(
        "ix_mi_ai_usage_periods_organization_id", table_name="mi_ai_usage_periods"
    )
    op.drop_table("mi_ai_usage_periods")
    op.drop_index(
        "ix_mi_ai_organization_policies_organization_id",
        table_name="mi_ai_organization_policies",
    )
    op.drop_table("mi_ai_organization_policies")
