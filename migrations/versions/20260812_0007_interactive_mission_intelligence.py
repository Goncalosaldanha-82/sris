"""Interactive Mission Intelligence dialogue and proposal review

Revision ID: 20260812_0007
Revises: 20260810_0006
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_0007"
down_revision: Union[str, Sequence[str], None] = "20260810_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mi_dialogue_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("mission_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="active",
        ),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mi_missions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mi_dialogue_sessions_organization_id",
        "mi_dialogue_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_mi_dialogue_sessions_mission_id",
        "mi_dialogue_sessions",
        ["mission_id"],
    )
    op.create_index(
        "ix_mi_dialogue_sessions_mission_code",
        "mi_dialogue_sessions",
        ["mission_code"],
    )
    op.create_index(
        "ix_mi_dialogue_sessions_status",
        "mi_dialogue_sessions",
        ["status"],
    )
    op.create_index(
        "ix_mi_dialogue_sessions_snapshot_hash",
        "mi_dialogue_sessions",
        ["snapshot_hash"],
    )

    op.create_table(
        "mi_dialogue_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("answers_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["intelligence_run_id"],
            ["mi_intelligence_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["mi_dialogue_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_mi_dialogue_turn_sequence",
        ),
        sa.UniqueConstraint("intelligence_run_id"),
    )
    op.create_index(
        "ix_mi_dialogue_turns_session_id",
        "mi_dialogue_turns",
        ["session_id"],
    )
    op.create_index(
        "ix_mi_dialogue_turns_intelligence_run_id",
        "mi_dialogue_turns",
        ["intelligence_run_id"],
        unique=True,
    )

    op.create_table(
        "mi_proposal_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=120), nullable=False),
        sa.Column("proposal_type", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["mi_dialogue_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["mi_dialogue_turns.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "turn_id",
            "proposal_id",
            name="uq_mi_proposal_review_turn_proposal",
        ),
    )
    op.create_index(
        "ix_mi_proposal_reviews_organization_id",
        "mi_proposal_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_mi_proposal_reviews_session_id",
        "mi_proposal_reviews",
        ["session_id"],
    )
    op.create_index(
        "ix_mi_proposal_reviews_turn_id",
        "mi_proposal_reviews",
        ["turn_id"],
    )
    op.create_index(
        "ix_mi_proposal_reviews_proposal_id",
        "mi_proposal_reviews",
        ["proposal_id"],
    )
    op.create_index(
        "ix_mi_proposal_reviews_decision",
        "mi_proposal_reviews",
        ["decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_mi_proposal_reviews_decision", table_name="mi_proposal_reviews")
    op.drop_index("ix_mi_proposal_reviews_proposal_id", table_name="mi_proposal_reviews")
    op.drop_index("ix_mi_proposal_reviews_turn_id", table_name="mi_proposal_reviews")
    op.drop_index("ix_mi_proposal_reviews_session_id", table_name="mi_proposal_reviews")
    op.drop_index(
        "ix_mi_proposal_reviews_organization_id",
        table_name="mi_proposal_reviews",
    )
    op.drop_table("mi_proposal_reviews")

    op.drop_index(
        "ix_mi_dialogue_turns_intelligence_run_id",
        table_name="mi_dialogue_turns",
    )
    op.drop_index("ix_mi_dialogue_turns_session_id", table_name="mi_dialogue_turns")
    op.drop_table("mi_dialogue_turns")

    op.drop_index(
        "ix_mi_dialogue_sessions_snapshot_hash",
        table_name="mi_dialogue_sessions",
    )
    op.drop_index("ix_mi_dialogue_sessions_status", table_name="mi_dialogue_sessions")
    op.drop_index(
        "ix_mi_dialogue_sessions_mission_code",
        table_name="mi_dialogue_sessions",
    )
    op.drop_index(
        "ix_mi_dialogue_sessions_mission_id",
        table_name="mi_dialogue_sessions",
    )
    op.drop_index(
        "ix_mi_dialogue_sessions_organization_id",
        table_name="mi_dialogue_sessions",
    )
    op.drop_table("mi_dialogue_sessions")
