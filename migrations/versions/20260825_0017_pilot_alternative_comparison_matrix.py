"""Add governed alternative comparison matrix revisions.

Revision ID: 20260825_0017
Revises: 20260824_0016
Create Date: 2026-08-25

Each save produces a new immutable assessment revision.  Scores remain tied
to canonical alternative and evidence nodes so a later decision can be read
and audited without relying on transient interface state.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_0017"
down_revision: Union[str, Sequence[str], None] = "20260824_0016"
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


def _columns(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    tables = _tables()
    if "pilot_alternative_matrices" not in tables:
        op.create_table(
            "pilot_alternative_matrices",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("mission_code", sa.String(length=80), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("weights_json", sa.Text(), nullable=False),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(length=64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "organization_id",
                "mission_id",
                "revision",
                name="uq_pilot_alt_matrix_org_mission_revision",
            ),
        )
    elif "snapshot_json" not in _columns("pilot_alternative_matrices"):
        op.add_column(
            "pilot_alternative_matrices",
            sa.Column("snapshot_json", sa.Text(), nullable=True),
        )
        op.execute(
            "UPDATE pilot_alternative_matrices "
            "SET snapshot_json = '{}' WHERE snapshot_json IS NULL"
        )
        op.alter_column("pilot_alternative_matrices", "snapshot_json", nullable=False)

    tables = _tables()
    if "pilot_alternative_matrix_scores" not in tables:
        op.create_table(
            "pilot_alternative_matrix_scores",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("matrix_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("mission_id", sa.String(length=64), nullable=False),
            sa.Column("alternative_node_id", sa.String(length=64), nullable=False),
            sa.Column("criterion", sa.String(length=50), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("evidence_node_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("score >= 1 AND score <= 5", name="ck_pilot_alt_matrix_score_range"),
            sa.ForeignKeyConstraint(["matrix_id"], ["pilot_alternative_matrices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "matrix_id",
                "alternative_node_id",
                "criterion",
                name="uq_pilot_alt_matrix_score_entry",
            ),
        )

    if "ix_pilot_alt_matrix_org_mission" not in _indexes("pilot_alternative_matrices"):
        op.create_index(
            "ix_pilot_alt_matrix_org_mission",
            "pilot_alternative_matrices",
            ["organization_id", "mission_id", "revision"],
            unique=False,
        )
    if "ix_pilot_alt_matrix_scores_matrix" not in _indexes("pilot_alternative_matrix_scores"):
        op.create_index(
            "ix_pilot_alt_matrix_scores_matrix",
            "pilot_alternative_matrix_scores",
            ["matrix_id", "alternative_node_id", "criterion"],
            unique=False,
        )


def downgrade() -> None:
    tables = _tables()
    if "pilot_alternative_matrix_scores" in tables:
        op.drop_table("pilot_alternative_matrix_scores")
    if "pilot_alternative_matrices" in tables:
        op.drop_table("pilot_alternative_matrices")
