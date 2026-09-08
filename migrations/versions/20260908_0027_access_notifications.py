"""Persist access request notifications and provider acknowledgements."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0027"
down_revision = "20260907_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sris_access_notifications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("sris_access_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("provider_id", sa.String(200)),
        sa.Column("error_code", sa.String(100)))
    for name in ("request_id", "status", "next_attempt_at"):
        op.create_index("ix_sris_access_notifications_" + name, "sris_access_notifications", [name])


def downgrade():
    op.drop_table("sris_access_notifications")
