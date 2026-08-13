"""Mission portfolios and recursive mission hierarchy

Revision ID: 20260813_0008
Revises: 20260812_0007
Create Date: 2026-08-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0008"
down_revision: Union[str, Sequence[str], None] = "20260812_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mi_missions") as batch:
        batch.add_column(sa.Column("parent_mission_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("mission_kind", sa.String(length=30), nullable=False, server_default="mission"))
        batch.add_column(sa.Column("domain", sa.String(length=80), nullable=False, server_default="cross_domain"))
        batch.add_column(sa.Column("priority", sa.String(length=20), nullable=False, server_default="strategic"))
        batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key(
            "fk_mi_missions_parent_mission_id",
            "mi_missions",
            ["parent_mission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_mi_missions_parent_mission_id", ["parent_mission_id"])
        batch.create_index("ix_mi_missions_mission_kind", ["mission_kind"])
        batch.create_index("ix_mi_missions_domain", ["domain"])
        batch.create_index("ix_mi_missions_priority", ["priority"])


def downgrade() -> None:
    with op.batch_alter_table("mi_missions") as batch:
        batch.drop_index("ix_mi_missions_priority")
        batch.drop_index("ix_mi_missions_domain")
        batch.drop_index("ix_mi_missions_mission_kind")
        batch.drop_index("ix_mi_missions_parent_mission_id")
        batch.drop_constraint("fk_mi_missions_parent_mission_id", type_="foreignkey")
        batch.drop_column("sort_order")
        batch.drop_column("priority")
        batch.drop_column("domain")
        batch.drop_column("mission_kind")
        batch.drop_column("parent_mission_id")
