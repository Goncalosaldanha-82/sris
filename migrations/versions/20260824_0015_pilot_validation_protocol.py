"""Add governed measurable validation protocols to Pilot V1.

Revision ID: 20260824_0015
Revises: 20260822_0014
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0015"
down_revision: Union[str, Sequence[str], None] = "20260822_0014"
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
    if "pilot_validation_protocols" not in tables:
        op.create_table(
            "pilot_validation_protocols",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("profile", sa.String(length=80), nullable=False),
            sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("subject_type", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("problem_statement", sa.Text(), nullable=False, server_default=""),
            sa.Column("indicator_name", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("indicator_unit", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("desired_direction", sa.String(length=30), nullable=False, server_default="decrease"),
            sa.Column("denominator_name", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("denominator_unit", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("target_value", sa.Numeric(24, 8), nullable=True),
            sa.Column("target_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("guardrails", sa.Text(), nullable=False, server_default=""),
            sa.Column("intervention_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("intervention_start_date", sa.Date(), nullable=True),
            sa.Column("intervention_end_date", sa.Date(), nullable=True),
            sa.Column("review_date", sa.Date(), nullable=True),
            sa.Column("attribution_method", sa.Text(), nullable=False, server_default=""),
            sa.Column("attribution_confidence", sa.String(length=30), nullable=True),
            sa.Column("review_rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
            sa.Column("external_factors", sa.Text(), nullable=False, server_default=""),
            sa.Column("implementation_deviation", sa.Text(), nullable=False, server_default=""),
            sa.Column("reviewed_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "mission_id", name="uq_pilot_validation_org_mission"),
        )

    if "pilot_validation_measurements" not in tables:
        op.create_table(
            "pilot_validation_measurements",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("protocol_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("phase", sa.String(length=20), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("numerator_value", sa.Numeric(24, 8), nullable=False),
            sa.Column("denominator_value", sa.Numeric(24, 8), nullable=True),
            sa.Column("normalized_value", sa.Numeric(24, 8), nullable=False),
            sa.Column("evidence_node_id", sa.String(length=64), nullable=False),
            sa.Column("data_quality", sa.String(length=30), nullable=False, server_default="moderate"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["protocol_id"], ["pilot_validation_protocols.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("protocol_id", "phase", name="uq_pilot_validation_protocol_phase"),
        )

    if "pilot_validation_events" not in tables:
        op.create_table(
            "pilot_validation_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("protocol_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["protocol_id"], ["pilot_validation_protocols.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("protocol_id", "revision", name="uq_pilot_validation_event_revision"),
        )

    if "ix_pilot_validation_org_mission" not in _indexes("pilot_validation_protocols"):
        op.create_index(
            "ix_pilot_validation_org_mission",
            "pilot_validation_protocols",
            ["organization_id", "mission_id"],
            unique=False,
        )
    if "ix_pilot_validation_measurements_mission" not in _indexes("pilot_validation_measurements"):
        op.create_index(
            "ix_pilot_validation_measurements_mission",
            "pilot_validation_measurements",
            ["organization_id", "mission_id", "phase"],
            unique=False,
        )
    if "ix_pilot_validation_events_protocol" not in _indexes("pilot_validation_events"):
        op.create_index(
            "ix_pilot_validation_events_protocol",
            "pilot_validation_events",
            ["protocol_id", "revision"],
            unique=False,
        )


def downgrade() -> None:
    tables = _tables()
    if "pilot_validation_events" in tables:
        op.drop_table("pilot_validation_events")
    if "pilot_validation_measurements" in tables:
        op.drop_table("pilot_validation_measurements")
    if "pilot_validation_protocols" in tables:
        op.drop_table("pilot_validation_protocols")
