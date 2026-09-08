"""Record the contextual-learning compatibility boundary.

Revision ID: 20260826_0018
Revises: 20260825_0017
Create Date: 2026-08-26

The learning tables predate their Alembic ownership and are queried by the
currently serving deployment while Railway starts its replacement. Altering
those hot tables in the new container can wait indefinitely for an exclusive
PostgreSQL lock and make the healthcheck kill an otherwise valid deployment.

The application therefore keeps the stable physical schema and maps legacy
``disposition`` values to the contextual-applicability vocabulary at the API
boundary. Published packets remain canonically valid independently. This
revision intentionally performs no DDL; it advances the migration ledger so a
later maintenance migration can alter the tables during an explicit downtime
window if physical columns ever become necessary.
"""

from typing import Sequence, Union

revision: str = "20260826_0018"
down_revision: Union[str, Sequence[str], None] = "20260825_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
