"""Add privacy-minimized internal analytics.

Revision ID: 20260907_0025
Revises: 20260901_0024
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0025"
down_revision: Union[str, Sequence[str], None] = "20260901_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sris_internal_analytics_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("path", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=128), nullable=False, server_default="direct"),
        sa.Column("medium", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("campaign", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("referrer_host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sris_internal_analytics_occurred_at",
        "sris_internal_analytics_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_sris_internal_analytics_event_name",
        "sris_internal_analytics_events",
        ["event_name"],
    )
    op.create_index(
        "ix_sris_internal_analytics_surface",
        "sris_internal_analytics_events",
        ["surface"],
    )
    op.create_index(
        "ix_sris_internal_analytics_source",
        "sris_internal_analytics_events",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sris_internal_analytics_source",
        table_name="sris_internal_analytics_events",
    )
    op.drop_index(
        "ix_sris_internal_analytics_surface",
        table_name="sris_internal_analytics_events",
    )
    op.drop_index(
        "ix_sris_internal_analytics_event_name",
        table_name="sris_internal_analytics_events",
    )
    op.drop_index(
        "ix_sris_internal_analytics_occurred_at",
        table_name="sris_internal_analytics_events",
    )
    op.drop_table("sris_internal_analytics_events")
