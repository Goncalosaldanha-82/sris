"""Add transversal Pilot & Mission Intelligence platform.

Revision ID: 20260901_0023
Revises: 20260827_0022
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0023"
down_revision: Union[str, Sequence[str], None] = "20260827_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sris_pilots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("sector_profile", sa.String(length=80), nullable=False, server_default="cross_sector"),
        sa.Column("template_key", sa.String(length=100), nullable=False, server_default="universal_decision_pilot"),
        sa.Column("program_source", sa.String(length=200), nullable=False, server_default="direct"),
        sa.Column("partner_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("context_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("context_type", sa.String(length=80), nullable=False, server_default="unit"),
        sa.Column("location", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("decision_question", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("exclusions", sa.Text(), nullable=False, server_default=""),
        sa.Column("sponsor", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("pilot_owner", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("data_owner", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("operator", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("reviewer", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("charter_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("data_readiness_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("implementation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("scale_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_sris_pilot_org_code"),
    )
    op.create_index("ix_sris_pilots_organization_id", "sris_pilots", ["organization_id"])
    op.create_index("ix_sris_pilots_code", "sris_pilots", ["code"])
    op.create_index("ix_sris_pilots_sector_profile", "sris_pilots", ["sector_profile"])
    op.create_index("ix_sris_pilots_lifecycle_state", "sris_pilots", ["lifecycle_state"])

    op.create_table(
        "sris_pilot_missions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("link_role", sa.String(length=40), nullable=False, server_default="primary"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pilot_id", "mission_id", name="uq_sris_pilot_mission_link"),
    )
    op.create_index("ix_sris_pilot_missions_pilot_id", "sris_pilot_missions", ["pilot_id"])
    op.create_index("ix_sris_pilot_missions_mission_id", "sris_pilot_missions", ["mission_id"])

    op.create_table(
        "sris_pilot_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("metric_key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="operational"),
        sa.Column("unit", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("direction", sa.String(length=20), nullable=False, server_default="decrease"),
        sa.Column("baseline_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("target_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("current_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("normalized_by", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("method", sa.Text(), nullable=False, server_default=""),
        sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default="not_evaluable"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="not_measured"),
        sa.Column("baseline_period", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("result_period", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pilot_id", "metric_key", name="uq_sris_pilot_metric_key"),
    )
    op.create_index("ix_sris_pilot_metrics_pilot_id", "sris_pilot_metrics", ["pilot_id"])

    op.create_table(
        "sris_pilot_data_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False, server_default="file"),
        sa.Column("system_name", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("data_format", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("owner", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("frequency", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("access_method", sa.String(length=160), nullable=False, server_default="manual_upload"),
        sa.Column("readiness_state", sa.String(length=30), nullable=False, server_default="identified"),
        sa.Column("quality_state", sa.String(length=30), nullable=False, server_default="unknown"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sris_pilot_data_sources_pilot_id", "sris_pilot_data_sources", ["pilot_id"])

    op.create_table(
        "sris_pilot_work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False, server_default="action"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="planned"),
        sa.Column("owner", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sris_pilot_work_items_pilot_id", "sris_pilot_work_items", ["pilot_id"])


def downgrade() -> None:
    op.drop_index("ix_sris_pilot_work_items_pilot_id", table_name="sris_pilot_work_items")
    op.drop_table("sris_pilot_work_items")
    op.drop_index("ix_sris_pilot_data_sources_pilot_id", table_name="sris_pilot_data_sources")
    op.drop_table("sris_pilot_data_sources")
    op.drop_index("ix_sris_pilot_metrics_pilot_id", table_name="sris_pilot_metrics")
    op.drop_table("sris_pilot_metrics")
    op.drop_index("ix_sris_pilot_missions_mission_id", table_name="sris_pilot_missions")
    op.drop_index("ix_sris_pilot_missions_pilot_id", table_name="sris_pilot_missions")
    op.drop_table("sris_pilot_missions")
    op.drop_index("ix_sris_pilots_lifecycle_state", table_name="sris_pilots")
    op.drop_index("ix_sris_pilots_sector_profile", table_name="sris_pilots")
    op.drop_index("ix_sris_pilots_code", table_name="sris_pilots")
    op.drop_index("ix_sris_pilots_organization_id", table_name="sris_pilots")
    op.drop_table("sris_pilots")
