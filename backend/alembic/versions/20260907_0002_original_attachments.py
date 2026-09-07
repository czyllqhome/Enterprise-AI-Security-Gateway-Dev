"""Bind original files and confirmation snapshots to immutable identities."""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0002"
down_revision = "20260825_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attachment_identities",
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("verified_mime", sa.String(255), nullable=False),
        sa.Column("review_policy", sa.String(64)),
        sa.Column("reviewed_sha256", sa.String(64)),
        sa.Column("decision", sa.String(32), nullable=False),
    )
    op.create_table(
        "chat_send_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_event_id", sa.Integer(), sa.ForeignKey("scan_events.id"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("sanitized_prompt", sa.Text(), nullable=False),
        sa.Column("attachments_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("user_message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="SET NULL")),
        sa.Column("assistant_message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "message_attachments",
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("uploaded_files.id"), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
    )


def downgrade():
    op.drop_table("message_attachments")
    op.drop_table("chat_send_snapshots")
    op.drop_table("attachment_identities")
