"""Store short-lived mailbox proofs for existing-account invitation activation."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0028"
down_revision = "20260908_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sris_invitation_activation_proofs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("user_invitations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitation_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("delivery_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sris_invitation_activation_proofs_invitation_id", "sris_invitation_activation_proofs", ["invitation_id"])
    op.create_index("ix_sris_invitation_activation_proofs_user_id", "sris_invitation_activation_proofs", ["user_id"])


def downgrade():
    op.drop_index("ix_sris_invitation_activation_proofs_user_id", "sris_invitation_activation_proofs")
    op.drop_index("ix_sris_invitation_activation_proofs_invitation_id", "sris_invitation_activation_proofs")
    op.drop_table("sris_invitation_activation_proofs")
