"""Separate documentary source integrity from factual validation.

Revision ID: 20260824_0016
Revises: 20260824_0015
Create Date: 2026-08-24

Document extraction, hashing and a human selecting an excerpt prove which
source was used.  They do not prove that the source's statements are true.
This data repair downgrades only evidence nodes that the application itself
had automatically marked as verified/authoritative without a factual review.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260824_0016"
down_revision: Union[str, Sequence[str], None] = "20260824_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pilot_evidence_graph_nodes" not in inspector.get_table_names():
        return

    rows = bind.execute(
        sa.text(
            """
            SELECT id, status, source_kind, provenance_json
            FROM pilot_evidence_graph_nodes
            WHERE node_type='evidence'
              AND source_kind IN ('document_chunk', 'visual_document')
            """
        )
    ).mappings().all()

    for row in rows:
        try:
            provenance = json.loads(row["provenance_json"] or "{}")
        except (TypeError, ValueError):
            provenance = {}

        # Never undo a separate, explicit factual review.  The repair targets
        # the old automatic classification only.
        if provenance.get("factual_review_completed") or provenance.get("factual_validation") == "verified":
            continue
        was_automatic = bool(
            provenance.get("authoritative_source") is True
            or provenance.get("human_promoted") is True
            or provenance.get("retrieval")
        )
        if not was_automatic:
            continue

        provenance.update(
            {
                "source_integrity_verified": True,
                "factual_validation": "not_assessed",
                "authoritative_source": False,
                "epistemic_separation_version": "20260824-1",
            }
        )
        bind.execute(
            sa.text(
                """
                UPDATE pilot_evidence_graph_nodes
                SET status='proposed', provenance_json=:provenance,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
                """
            ),
            {
                "id": row["id"],
                "provenance": json.dumps(provenance, ensure_ascii=False, sort_keys=True),
            },
        )


def downgrade() -> None:
    # Do not restore an epistemically invalid "verified" state.  The schema is
    # unchanged and the corrected provenance remains valid on older code.
    pass
