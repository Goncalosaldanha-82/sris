"""Add the governed mission state and observable decision lineage.

Revision ID: 20260826_0020
Revises: 20260826_0019
Create Date: 2026-08-26

The migration is additive and inspects runtime-created Pilot tables before
altering them.  It is therefore safe for databases that already received the
older idempotent runtime bootstrap.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260826_0020"
down_revision: Union[str, Sequence[str], None] = "20260826_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _indexes(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
        if item.get("name")
    }


DECISION_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("action_started_at", sa.Date()),
    ("actual_outcome_at", sa.Date()),
    ("outcome_evidence_node_id", sa.String(length=64)),
    ("mission_revision", sa.Integer()),
    ("mission_content_hash", sa.String(length=64)),
    ("mission_governance_hash", sa.String(length=64)),
    ("matrix_revision", sa.Integer()),
    ("matrix_content_hash", sa.String(length=64)),
    ("business_case_revision", sa.Integer()),
    ("business_case_content_hash", sa.String(length=64)),
    ("validation_revision", sa.Integer()),
    ("validation_content_hash", sa.String(length=64)),
    ("decision_node_id", sa.String(length=64)),
    ("action_node_id", sa.String(length=64)),
    ("outcome_node_id", sa.String(length=64)),
    ("learning_node_id", sa.String(length=64)),
)


def upgrade() -> None:
    tables = _tables()
    if "pilot_decision_cycles" not in tables:
        op.create_table(
            "pilot_decision_cycles",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("decision", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=True),
            sa.Column("owner", sa.String(length=200), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="proposed"),
            sa.Column("expected_outcome", sa.Text(), nullable=True),
            sa.Column("actual_outcome", sa.Text(), nullable=True),
            sa.Column("learning", sa.Text(), nullable=True),
            sa.Column("evidence_node_id", sa.String(length=64), nullable=True),
            *(
                sa.Column(name, column_type, nullable=True)
                for name, column_type in DECISION_COLUMNS
            ),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        columns = _columns("pilot_decision_cycles")
        for name, column_type in DECISION_COLUMNS:
            if name not in columns:
                op.add_column(
                    "pilot_decision_cycles",
                    sa.Column(name, column_type, nullable=True),
                )

    if "ix_pilot_decision_cycles_org_mission" not in _indexes("pilot_decision_cycles"):
        op.create_index(
            "ix_pilot_decision_cycles_org_mission",
            "pilot_decision_cycles",
            ["organization_id", "mission_code", "created_at"],
            unique=False,
        )

    tables = _tables()
    if "pilot_mission_governance_policies" not in tables:
        op.create_table(
            "pilot_mission_governance_policies",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("alternatives_applicability", sa.String(length=30), nullable=False, server_default="required"),
            sa.Column("economics_applicability", sa.String(length=30), nullable=False, server_default="required"),
            sa.Column("measurement_applicability", sa.String(length=30), nullable=False, server_default="optional"),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("mission_revision", sa.Integer(), nullable=False),
            sa.Column("mission_content_hash", sa.String(length=64), nullable=False),
            sa.Column("mission_governance_hash", sa.String(length=64), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("reviewed_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "alternatives_applicability IN ('required','optional','not_applicable')",
                name="ck_pilot_mission_policy_alternatives",
            ),
            sa.CheckConstraint(
                "economics_applicability IN ('required','optional','not_applicable')",
                name="ck_pilot_mission_policy_economics",
            ),
            sa.CheckConstraint(
                "measurement_applicability IN ('required','optional','not_applicable')",
                name="ck_pilot_mission_policy_measurement",
            ),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "mission_id", name="uq_pilot_mission_governance_policy"),
        )
    elif "mission_governance_hash" not in _columns("pilot_mission_governance_policies"):
        op.add_column(
            "pilot_mission_governance_policies",
            sa.Column("mission_governance_hash", sa.String(length=64), nullable=True),
        )

    tables = _tables()
    if "pilot_mission_module_reviews" not in tables:
        op.create_table(
            "pilot_mission_module_reviews",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("module_key", sa.String(length=40), nullable=False),
            sa.Column("module_revision", sa.Integer(), nullable=True),
            sa.Column("module_content_hash", sa.String(length=64), nullable=False),
            sa.Column("upstream_hashes_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("reviewed_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "ix_pilot_mission_module_reviews_latest" not in _indexes("pilot_mission_module_reviews"):
        op.create_index(
            "ix_pilot_mission_module_reviews_latest",
            "pilot_mission_module_reviews",
            ["organization_id", "mission_id", "module_key", "reviewed_at"],
            unique=False,
        )


def downgrade() -> None:
    tables = _tables()
    if "pilot_mission_module_reviews" in tables:
        op.drop_table("pilot_mission_module_reviews")
    if "pilot_mission_governance_policies" in tables:
        op.drop_table("pilot_mission_governance_policies")
    if "pilot_decision_cycles" in tables:
        op.drop_table("pilot_decision_cycles")
