"""Initial product schema.

Revision ID: 20260614_0001
Revises:
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260614_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_sessions_id", "chat_sessions", ["id"])

    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("api_key", sa.String(length=512), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("default_model", sa.String(length=128), nullable=False),
        sa.Column("models_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_provider_credentials_id", "provider_credentials", ["id"])
    op.create_index("ix_provider_credentials_provider", "provider_credentials", ["provider"], unique=True)

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_settings_id", "system_settings", ["id"])
    op.create_index("ix_system_settings_key", "system_settings", ["key"], unique=True)

    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("extraction_summary", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_segments_json", sa.JSON(), nullable=True),
        sa.Column("review_result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_uploaded_files_id", "uploaded_files", ["id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=True),
        sa.Column("sanitized_content", sa.Text(), nullable=True),
        sa.Column("used_content", sa.Text(), nullable=True),
        sa.Column("has_sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("sensitive_entities_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_messages_id", "chat_messages", ["id"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    op.create_table(
        "chat_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("original_sensitive_content", sa.Text(), nullable=False),
        sa.Column("detected_entity_types", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_logs_id", "chat_logs", ["id"])
    op.create_index("ix_chat_logs_message_id", "chat_logs", ["message_id"])
    op.create_index("ix_chat_logs_session_id", "chat_logs", ["session_id"])

    op.create_table(
        "scan_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("blocked_reason", sa.String(length=255), nullable=True),
        sa.Column("has_sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("llm_guard_hit_count", sa.Integer(), nullable=False),
        sa.Column("privacy_filter_hit_count", sa.Integer(), nullable=False),
        sa.Column("custom_regex_hit_count", sa.Integer(), nullable=False),
        sa.Column("original_input", sa.Text(), nullable=False),
        sa.Column("sanitized_input", sa.Text(), nullable=False),
        sa.Column("assistant_raw_output", sa.Text(), nullable=True),
        sa.Column("assistant_display_output", sa.Text(), nullable=True),
        sa.Column("scanners_json", sa.JSON(), nullable=True),
        sa.Column("entity_types_json", sa.JSON(), nullable=True),
        sa.Column("detected_entities_json", sa.JSON(), nullable=True),
        sa.Column("business_sensitive_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scan_events_id", "scan_events", ["id"])
    op.create_index("ix_scan_events_session_id", "scan_events", ["session_id"])


def downgrade() -> None:
    op.drop_table("scan_events")
    op.drop_table("chat_logs")
    op.drop_table("chat_messages")
    op.drop_table("uploaded_files")
    op.drop_table("system_settings")
    op.drop_table("provider_credentials")
    op.drop_table("chat_sessions")
    op.drop_table("users")
