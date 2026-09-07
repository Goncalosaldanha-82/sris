"""Add governed commercial access lifecycle.

Revision ID: 20260907_0026
Revises: 20260907_0025
Create Date: 2026-09-07
"""

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0026"
down_revision: Union[str, Sequence[str], None] = "20260907_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sris_access_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("organization_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("entitlement_days", sa.Integer(), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("invitation_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"], ["user_invitations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sris_access_requests_email", "sris_access_requests", ["email"])
    op.create_index("ix_sris_access_requests_status", "sris_access_requests", ["status"])
    op.create_index(
        "ix_sris_access_requests_organization_id",
        "sris_access_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_sris_access_requests_requested_at",
        "sris_access_requests",
        ["requested_at"],
    )

    op.create_table(
        "sris_commercial_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commercial_reference", sa.String(length=200), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("renewal_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", name="uq_sris_commercial_entitlement_organization"
        ),
    )
    op.create_index(
        "ix_sris_commercial_entitlements_organization_id",
        "sris_commercial_entitlements",
        ["organization_id"],
    )
    op.create_index(
        "ix_sris_commercial_entitlements_status",
        "sris_commercial_entitlements",
        ["status"],
    )
    op.create_index(
        "ix_sris_commercial_entitlements_expires_at",
        "sris_commercial_entitlements",
        ["expires_at"],
    )

    # Preserve every workspace that existed before commercial entitlements were
    # introduced. These rows are active without an expiry until SRIS explicitly
    # assigns commercial terms; no staging customer is locked out by migration.
    connection = op.get_bind()
    organization_ids = [
        row[0]
        for row in connection.execute(sa.text("SELECT id FROM organizations")).fetchall()
    ]
    if organization_ids:
        now = datetime.now(timezone.utc)
        table = sa.table(
            "sris_commercial_entitlements",
            sa.column("id", sa.String),
            sa.column("organization_id", sa.String),
            sa.column("plan_code", sa.String),
            sa.column("status", sa.String),
            sa.column("starts_at", sa.DateTime(timezone=True)),
            sa.column("expires_at", sa.DateTime(timezone=True)),
            sa.column("commercial_reference", sa.String),
            sa.column("approved_by_user_id", sa.String),
            sa.column("renewal_count", sa.Integer),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            table,
            [
                {
                    "id": str(uuid4()),
                    "organization_id": organization_id,
                    "plan_code": "pilot",
                    "status": "grandfathered",
                    "starts_at": now,
                    "expires_at": None,
                    "commercial_reference": "migration-20260907-0026",
                    "approved_by_user_id": None,
                    "renewal_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                for organization_id in organization_ids
            ],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_sris_commercial_entitlements_expires_at",
        table_name="sris_commercial_entitlements",
    )
    op.drop_index(
        "ix_sris_commercial_entitlements_status",
        table_name="sris_commercial_entitlements",
    )
    op.drop_index(
        "ix_sris_commercial_entitlements_organization_id",
        table_name="sris_commercial_entitlements",
    )
    op.drop_table("sris_commercial_entitlements")

    op.drop_index(
        "ix_sris_access_requests_requested_at", table_name="sris_access_requests"
    )
    op.drop_index(
        "ix_sris_access_requests_organization_id", table_name="sris_access_requests"
    )
    op.drop_index("ix_sris_access_requests_status", table_name="sris_access_requests")
    op.drop_index("ix_sris_access_requests_email", table_name="sris_access_requests")
    op.drop_table("sris_access_requests")
