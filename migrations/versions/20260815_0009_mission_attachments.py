"""Encrypted mission attachments and turn linkage

Revision ID: 20260815_0009
Revises: 20260813_0008
Create Date: 2026-08-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_0009"
down_revision: Union[str, Sequence[str], None] = "20260813_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mi_dialogue_turns") as batch:
        batch.add_column(
            sa.Column(
                "attachment_ids_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )

    op.create_table(
        "mi_mission_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("mission_code", sa.String(length=80), nullable=False),
        sa.Column("dialogue_session_id", sa.String(length=36), nullable=True),
        sa.Column("question_id", sa.String(length=120), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("extension", sa.String(length=24), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("extraction_status", sa.String(length=40), nullable=False, server_default="ready"),
        sa.Column("extraction_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dialogue_session_id"], ["mi_dialogue_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "mission_id",
            "sha256",
            name="uq_mi_attachment_org_mission_sha256",
        ),
    )
    op.create_index("ix_mi_mission_attachments_organization_id", "mi_mission_attachments", ["organization_id"])
    op.create_index("ix_mi_mission_attachments_mission_id", "mi_mission_attachments", ["mission_id"])
    op.create_index("ix_mi_mission_attachments_mission_code", "mi_mission_attachments", ["mission_code"])
    op.create_index("ix_mi_mission_attachments_dialogue_session_id", "mi_mission_attachments", ["dialogue_session_id"])
    op.create_index("ix_mi_mission_attachments_sha256", "mi_mission_attachments", ["sha256"])
    op.create_index("ix_mi_mission_attachments_extraction_status", "mi_mission_attachments", ["extraction_status"])


def downgrade() -> None:
    op.drop_index("ix_mi_mission_attachments_extraction_status", table_name="mi_mission_attachments")
    op.drop_index("ix_mi_mission_attachments_sha256", table_name="mi_mission_attachments")
    op.drop_index("ix_mi_mission_attachments_dialogue_session_id", table_name="mi_mission_attachments")
    op.drop_index("ix_mi_mission_attachments_mission_code", table_name="mi_mission_attachments")
    op.drop_index("ix_mi_mission_attachments_mission_id", table_name="mi_mission_attachments")
    op.drop_index("ix_mi_mission_attachments_organization_id", table_name="mi_mission_attachments")
    op.drop_table("mi_mission_attachments")
    with op.batch_alter_table("mi_dialogue_turns") as batch:
        batch.drop_column("attachment_ids_json")
