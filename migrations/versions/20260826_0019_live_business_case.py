"""Add the governed live business case to Pilot V1.

Revision ID: 20260826_0019
Revises: 20260826_0018
Create Date: 2026-08-26

The migration creates new tables only.  It does not alter the hot learning or
mission tables, so the replacement Railway container does not need an
exclusive lock on data used by the currently serving deployment.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260826_0019"
down_revision: Union[str, Sequence[str], None] = "20260826_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
        if item.get("name")
    }


def upgrade() -> None:
    tables = _tables()
    if "pilot_business_cases" not in tables:
        op.create_table(
            "pilot_business_cases",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("case_kind", sa.String(length=40), nullable=False, server_default="hybrid"),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
            sa.Column("horizon_months", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("discount_rate_pct", sa.Numeric(12, 6), nullable=False, server_default="8"),
            sa.Column("decision_context", sa.Text(), nullable=False, server_default=""),
            sa.Column("baseline", sa.Text(), nullable=False, server_default=""),
            sa.Column("counterfactual", sa.Text(), nullable=False, server_default=""),
            sa.Column("planned_start_date", sa.Date(), nullable=True),
            sa.Column("planned_end_date", sa.Date(), nullable=True),
            sa.Column("forecast_end_date", sa.Date(), nullable=True),
            sa.Column("actual_start_date", sa.Date(), nullable=True),
            sa.Column("actual_end_date", sa.Date(), nullable=True),
            sa.Column("outcome_name", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("outcome_unit", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("planned_outcome_quantity", sa.Numeric(24, 8), nullable=True),
            sa.Column("actual_outcome_quantity", sa.Numeric(24, 8), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("review_rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("reviewed_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("horizon_months >= 1 AND horizon_months <= 600", name="ck_pilot_business_case_horizon"),
            sa.CheckConstraint("discount_rate_pct >= 0 AND discount_rate_pct <= 100", name="ck_pilot_business_case_discount"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "mission_id", name="uq_pilot_business_case_org_mission"),
        )

    tables = _tables()
    if "pilot_business_case_items" not in tables:
        op.create_table(
            "pilot_business_case_items",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("business_case_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("financial_treatment", sa.String(length=20), nullable=False),
            sa.Column("category", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("label", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("phase", sa.String(length=30), nullable=False, server_default="execution"),
            sa.Column("unit", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("amount_basis", sa.String(length=20), nullable=False, server_default="total"),
            sa.Column("planned_quantity", sa.Numeric(24, 8), nullable=True),
            sa.Column("actual_quantity", sa.Numeric(24, 8), nullable=True),
            sa.Column("conservative_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("base_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("favorable_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("committed_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("realized_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("forecast_amount", sa.Numeric(24, 8), nullable=True),
            sa.Column("start_month", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("end_month", sa.Integer(), nullable=True),
            sa.Column("recurrence", sa.String(length=20), nullable=False, server_default="one_off"),
            sa.Column("source_label", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("evidence_node_id", sa.String(length=64), nullable=True),
            sa.Column("alternative_node_id", sa.String(length=64), nullable=True),
            sa.Column("responsible", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("operational_status", sa.String(length=20), nullable=False, server_default="planned"),
            sa.Column("blocker", sa.Text(), nullable=False, server_default=""),
            sa.Column("assumption", sa.Text(), nullable=False, server_default=""),
            sa.Column("confidence", sa.String(length=20), nullable=False, server_default="moderate"),
            sa.Column("include_in_totals", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("start_month >= 0", name="ck_pilot_business_case_item_start"),
            sa.ForeignKeyConstraint(["business_case_id"], ["pilot_business_cases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    tables = _tables()
    if "pilot_business_case_events" not in tables:
        op.create_table(
            "pilot_business_case_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("business_case_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["business_case_id"], ["pilot_business_cases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("business_case_id", "revision", name="uq_pilot_business_case_event_revision"),
        )

    if "ix_pilot_business_case_org_mission" not in _indexes("pilot_business_cases"):
        op.create_index(
            "ix_pilot_business_case_org_mission",
            "pilot_business_cases",
            ["organization_id", "mission_id"],
            unique=False,
        )
    if "ix_pilot_business_case_items_case" not in _indexes("pilot_business_case_items"):
        op.create_index(
            "ix_pilot_business_case_items_case",
            "pilot_business_case_items",
            ["business_case_id", "alternative_node_id", "kind", "phase", "retired_at"],
            unique=False,
        )
    if "ix_pilot_business_case_events_case" not in _indexes("pilot_business_case_events"):
        op.create_index(
            "ix_pilot_business_case_events_case",
            "pilot_business_case_events",
            ["business_case_id", "revision"],
            unique=False,
        )


def downgrade() -> None:
    tables = _tables()
    if "pilot_business_case_events" in tables:
        op.drop_table("pilot_business_case_events")
    if "pilot_business_case_items" in tables:
        op.drop_table("pilot_business_case_items")
    if "pilot_business_cases" in tables:
        op.drop_table("pilot_business_cases")
