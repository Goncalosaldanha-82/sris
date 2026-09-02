"""Add evidence-backed pilot value and collaboration.

Revision ID: 20260901_0024
Revises: 20260901_0023
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0024"
down_revision: Union[str, Sequence[str], None] = "20260901_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sris_pilot_value_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("value_status", sa.String(length=30), nullable=False, server_default="expected"),
        sa.Column("numeric_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("period", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("baseline_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("calculation", sa.Text(), nullable=False, server_default=""),
        sa.Column("attribution", sa.Text(), nullable=False, server_default=""),
        sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default="not_evaluable"),
        sa.Column("owner", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sris_pilot_value_items_pilot_id",
        "sris_pilot_value_items",
        ["pilot_id"],
    )
    op.create_index(
        "ix_sris_pilot_value_items_dimension",
        "sris_pilot_value_items",
        ["dimension"],
    )
    op.create_index(
        "ix_sris_pilot_value_items_value_status",
        "sris_pilot_value_items",
        ["value_status"],
    )

    op.create_table(
        "sris_pilot_collaborators",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pilot_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("role_key", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("organization_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["sris_pilots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pilot_id",
            "role_key",
            "email",
            name="uq_sris_pilot_collaborator_role_email",
        ),
    )
    op.create_index(
        "ix_sris_pilot_collaborators_pilot_id",
        "sris_pilot_collaborators",
        ["pilot_id"],
    )
    op.create_index(
        "ix_sris_pilot_collaborators_user_id",
        "sris_pilot_collaborators",
        ["user_id"],
    )
    op.create_index(
        "ix_sris_pilot_collaborators_role_key",
        "sris_pilot_collaborators",
        ["role_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sris_pilot_collaborators_role_key",
        table_name="sris_pilot_collaborators",
    )
    op.drop_index(
        "ix_sris_pilot_collaborators_user_id",
        table_name="sris_pilot_collaborators",
    )
    op.drop_index(
        "ix_sris_pilot_collaborators_pilot_id",
        table_name="sris_pilot_collaborators",
    )
    op.drop_table("sris_pilot_collaborators")

    op.drop_index(
        "ix_sris_pilot_value_items_value_status",
        table_name="sris_pilot_value_items",
    )
    op.drop_index(
        "ix_sris_pilot_value_items_dimension",
        table_name="sris_pilot_value_items",
    )
    op.drop_index(
        "ix_sris_pilot_value_items_pilot_id",
        table_name="sris_pilot_value_items",
    )
    op.drop_table("sris_pilot_value_items")
