"""Repair success criteria that were stored as observed outcomes.

Revision ID: 20260826_0021
Revises: 20260826_0020
Create Date: 2026-08-26

The Pilot evidence graph uses an open VARCHAR discriminator, so introducing
the ``target`` semantic type requires no structural table change.  This data
repair is deliberately narrow: only mission-onboarding success criteria that
were previously generated as outcomes are reclassified.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260826_0021"
down_revision: Union[str, Sequence[str], None] = "20260826_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _graph_can_be_repaired() -> bool:
    inspector = sa.inspect(op.get_bind())
    table = "pilot_evidence_graph_nodes"
    if table not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns(table)}
    return {
        "node_type",
        "label",
        "source_kind",
        "provenance_json",
        "updated_at",
    }.issubset(columns)


def _repair(from_type: str, to_type: str) -> None:
    # Some supported upgrade paths contain a deliberately minimal compatibility
    # table.  A semantic data repair must never assume columns that an earlier
    # hot-table migration intentionally did not create.
    if not _graph_can_be_repaired():
        return
    op.get_bind().execute(
        sa.text(
            """
            UPDATE pilot_evidence_graph_nodes
            SET node_type=:to_type,
                provenance_json=REPLACE(
                    REPLACE(
                        provenance_json,
                        '"canonical_kind": "' || :from_type || '"',
                        '"canonical_kind": "' || :to_type || '"'
                    ),
                    '"canonical_kind":"' || :from_type || '"',
                    '"canonical_kind":"' || :to_type || '"'
                ),
                updated_at=CURRENT_TIMESTAMP
            WHERE node_type=:from_type
              AND source_kind='human_entry'
              AND LOWER(TRIM(label))='critério de sucesso'
              AND provenance_json LIKE '%mission_onboarding%'
            """
        ),
        {"from_type": from_type, "to_type": to_type},
    )


def upgrade() -> None:
    _repair("outcome", "target")


def downgrade() -> None:
    _repair("target", "outcome")
