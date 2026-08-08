"""Mission Intelligence canonical foundation v1.3

Revision ID: 20260808_0002
Revises: 20260802_0001
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_0002"
down_revision: Union[str, Sequence[str], None] = "20260802_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mi_missions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False, server_default="1.3"),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_mi_mission_org_code"),
    )
    op.create_index("ix_mi_missions_organization_id", "mi_missions", ["organization_id"])
    op.create_index("ix_mi_missions_code", "mi_missions", ["code"])
    op.create_index("ix_mi_missions_content_hash", "mi_missions", ["content_hash"])

    op.create_table(
        "mi_mission_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "revision", name="uq_mi_revision_number"),
    )
    op.create_index("ix_mi_mission_revisions_mission_id", "mi_mission_revisions", ["mission_id"])
    op.create_index("ix_mi_mission_revisions_content_hash", "mi_mission_revisions", ["content_hash"])

    op.create_table(
        "mi_intelligence_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("mission_code", sa.String(length=80), nullable=False),
        sa.Column("execution_mode", sa.String(length=30), nullable=False, server_default="deterministic"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
        sa.Column("engine_version", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("provider_response_id", sa.String(length=200), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("deterministic_json", sa.Text(), nullable=False),
        sa.Column("ai_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="required"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mi_intelligence_runs_organization_id", "mi_intelligence_runs", ["organization_id"])
    op.create_index("ix_mi_intelligence_runs_mission_id", "mi_intelligence_runs", ["mission_id"])
    op.create_index("ix_mi_intelligence_runs_mission_code", "mi_intelligence_runs", ["mission_code"])
    op.create_index("ix_mi_intelligence_runs_snapshot_hash", "mi_intelligence_runs", ["snapshot_hash"])
    op.create_index("ix_mi_intelligence_runs_review_status", "mi_intelligence_runs", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_mi_intelligence_runs_review_status", table_name="mi_intelligence_runs")
    op.drop_index("ix_mi_intelligence_runs_snapshot_hash", table_name="mi_intelligence_runs")
    op.drop_index("ix_mi_intelligence_runs_mission_code", table_name="mi_intelligence_runs")
    op.drop_index("ix_mi_intelligence_runs_mission_id", table_name="mi_intelligence_runs")
    op.drop_index("ix_mi_intelligence_runs_organization_id", table_name="mi_intelligence_runs")
    op.drop_table("mi_intelligence_runs")
    op.drop_index("ix_mi_mission_revisions_content_hash", table_name="mi_mission_revisions")
    op.drop_index("ix_mi_mission_revisions_mission_id", table_name="mi_mission_revisions")
    op.drop_table("mi_mission_revisions")
    op.drop_index("ix_mi_missions_content_hash", table_name="mi_missions")
    op.drop_index("ix_mi_missions_code", table_name="mi_missions")
    op.drop_index("ix_mi_missions_organization_id", table_name="mi_missions")
    op.drop_table("mi_missions")
