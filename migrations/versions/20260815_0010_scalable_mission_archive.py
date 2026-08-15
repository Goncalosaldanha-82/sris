"""Scalable encrypted mission archive retrieval index

Revision ID: 20260815_0010
Revises: 20260815_0009
Create Date: 2026-08-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_0010"
down_revision: Union[str, Sequence[str], None] = "20260815_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mi_archive_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("source_label", sa.String(length=500), nullable=False),
        sa.Column("attachment_id", sa.String(length=36), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("encrypted_text", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mi_missions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["mi_mission_attachments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "ordinal",
            name="uq_mi_archive_chunk_source_ordinal",
        ),
    )
    op.create_index(
        "ix_mi_archive_chunks_organization_id",
        "mi_archive_chunks",
        ["organization_id"],
    )
    op.create_index(
        "ix_mi_archive_chunks_mission_id", "mi_archive_chunks", ["mission_id"]
    )
    op.create_index(
        "ix_mi_archive_chunks_attachment_id",
        "mi_archive_chunks",
        ["attachment_id"],
    )
    op.create_index(
        "ix_mi_archive_chunks_source_type",
        "mi_archive_chunks",
        ["source_type"],
    )
    op.create_index(
        "ix_mi_archive_chunks_source_id",
        "mi_archive_chunks",
        ["source_id"],
    )
    op.create_index(
        "ix_mi_archive_chunks_content_sha256",
        "mi_archive_chunks",
        ["content_sha256"],
    )

    op.create_table(
        "mi_archive_chunk_terms",
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("term_hash", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"], ["mi_archive_chunks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chunk_id", "term_hash"),
    )
    op.create_index(
        "ix_mi_archive_chunk_terms_term_hash",
        "mi_archive_chunk_terms",
        ["term_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mi_archive_chunk_terms_term_hash",
        table_name="mi_archive_chunk_terms",
    )
    op.drop_table("mi_archive_chunk_terms")
    op.drop_index(
        "ix_mi_archive_chunks_content_sha256", table_name="mi_archive_chunks"
    )
    op.drop_index(
        "ix_mi_archive_chunks_attachment_id", table_name="mi_archive_chunks"
    )
    op.drop_index("ix_mi_archive_chunks_source_id", table_name="mi_archive_chunks")
    op.drop_index("ix_mi_archive_chunks_source_type", table_name="mi_archive_chunks")
    op.drop_index("ix_mi_archive_chunks_mission_id", table_name="mi_archive_chunks")
    op.drop_index(
        "ix_mi_archive_chunks_organization_id", table_name="mi_archive_chunks"
    )
    op.drop_table("mi_archive_chunks")
