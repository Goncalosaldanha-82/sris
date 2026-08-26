"""Install contextual learning columns before the application serves traffic.

Revision ID: 20260826_0018
Revises: 20260825_0017
Create Date: 2026-08-26

The learning tables predate their Alembic ownership and may already exist in
Railway.  This migration is deliberately additive: it upgrades existing tables
when present, while fresh databases continue to receive the complete columns
from the idempotent table bootstrap until those legacy tables are fully moved
into the canonical migration chain.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260826_0018"
down_revision: Union[str, Sequence[str], None] = "20260825_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    tables = _tables()
    if "pilot_learning_packets" in tables:
        if "canonical_status" not in _columns("pilot_learning_packets"):
            op.add_column(
                "pilot_learning_packets",
                sa.Column(
                    "canonical_status",
                    sa.String(length=40),
                    nullable=False,
                    server_default="valid",
                ),
            )

    if "pilot_learning_reviews" in tables:
        if "applicability" not in _columns("pilot_learning_reviews"):
            op.add_column(
                "pilot_learning_reviews",
                sa.Column(
                    "applicability",
                    sa.String(length=40),
                    nullable=False,
                    server_default="pending",
                ),
            )
        op.execute(
            """
            UPDATE pilot_learning_reviews
            SET applicability = CASE disposition
                WHEN 'still_valid' THEN 'reuse'
                WHEN 'requires_revalidation' THEN 'requires_revalidation'
                WHEN 'invalidated' THEN 'not_applicable'
                ELSE 'pending'
            END
            WHERE applicability IS NULL OR applicability = 'pending'
            """
        )


def downgrade() -> None:
    tables = _tables()
    if (
        "pilot_learning_reviews" in tables
        and "applicability" in _columns("pilot_learning_reviews")
    ):
        with op.batch_alter_table("pilot_learning_reviews") as batch_op:
            batch_op.drop_column("applicability")
    if (
        "pilot_learning_packets" in tables
        and "canonical_status" in _columns("pilot_learning_packets")
    ):
        with op.batch_alter_table("pilot_learning_packets") as batch_op:
            batch_op.drop_column("canonical_status")
