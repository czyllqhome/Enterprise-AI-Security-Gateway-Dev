from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class AttachmentIdentity(Base):
    __tablename__ = "attachment_identities"

    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_mime: Mapped[str] = mapped_column(String(255), nullable=False)
    review_policy: Mapped[str | None] = mapped_column(String(64))
    reviewed_sha256: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)


class ChatSendSnapshot(Base):
    __tablename__ = "chat_send_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    scan_event_id: Mapped[int] = mapped_column(ForeignKey("scan_events.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitized_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    attachments_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    user_message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"))
    assistant_message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
