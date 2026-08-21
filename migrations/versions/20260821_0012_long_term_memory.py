"""Long-term organizational memory

Revision ID: 20260821_0012
Revises: 20260815_0011
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0012"
down_revision: Union[str, Sequence[str], None] = "20260815_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mi_memory_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=True),
        sa.Column("canonical_record_id", sa.String(length=160), nullable=True),
        sa.Column("item_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("confidence", sa.String(length=30), nullable=False, server_default="not_evaluable"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("source_content_hash", sa.String(length=64), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["mi_memory_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "mission_id", "canonical_record_id", name="uq_mi_memory_source_record"),
    )
    for name, cols in (
        ("ix_mi_memory_items_organization_id", ["organization_id"]),
        ("ix_mi_memory_items_mission_id", ["mission_id"]),
        ("ix_mi_memory_items_canonical_record_id", ["canonical_record_id"]),
        ("ix_mi_memory_items_item_type", ["item_type"]),
        ("ix_mi_memory_items_state", ["state"]),
        ("ix_mi_memory_items_supersedes_id", ["supersedes_id"]),
        ("ix_mi_memory_items_source_content_hash", ["source_content_hash"]),
    ):
        op.create_index(name, "mi_memory_items", cols, unique=False)

    op.create_table(
        "mi_memory_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_item_id", sa.String(length=36), nullable=False),
        sa.Column("target_item_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["mi_memory_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_item_id"], ["mi_memory_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "source_item_id", "target_item_id", "relation_type", name="uq_mi_memory_link"),
    )
    op.create_index("ix_mi_memory_links_organization_id", "mi_memory_links", ["organization_id"], unique=False)
    op.create_index("ix_mi_memory_links_source_item_id", "mi_memory_links", ["source_item_id"], unique=False)
    op.create_index("ix_mi_memory_links_target_item_id", "mi_memory_links", ["target_item_id"], unique=False)
    op.create_index("ix_mi_memory_links_relation_type", "mi_memory_links", ["relation_type"], unique=False)

    op.create_table(
        "mi_evidence_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=True),
        sa.Column("storage_backend", sa.String(length=40), nullable=False, server_default="external"),
        sa.Column("object_key", sa.String(length=1500), nullable=False),
        sa.Column("original_filename", sa.String(length=1000), nullable=False),
        sa.Column("media_type", sa.String(length=200), nullable=False, server_default="application/octet-stream"),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="registered"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mi_missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_mi_evidence_asset_org_sha256"),
    )
    op.create_index("ix_mi_evidence_assets_organization_id", "mi_evidence_assets", ["organization_id"], unique=False)
    op.create_index("ix_mi_evidence_assets_mission_id", "mi_evidence_assets", ["mission_id"], unique=False)
    op.create_index("ix_mi_evidence_assets_storage_backend", "mi_evidence_assets", ["storage_backend"], unique=False)
    op.create_index("ix_mi_evidence_assets_sha256", "mi_evidence_assets", ["sha256"], unique=False)
    op.create_index("ix_mi_evidence_assets_state", "mi_evidence_assets", ["state"], unique=False)


def downgrade() -> None:
    op.drop_table("mi_evidence_assets")
    op.drop_table("mi_memory_links")
    op.drop_table("mi_memory_items")
