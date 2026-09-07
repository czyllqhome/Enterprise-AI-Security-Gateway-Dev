from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    original_content: Mapped[str | None] = mapped_column(Text)
    sanitized_content: Mapped[str | None] = mapped_column(Text)
    used_content: Mapped[str | None] = mapped_column(Text)
    has_sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitive_entities_json: Mapped[list[dict] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("ChatSession", back_populates="messages")
    attachments = relationship("MessageAttachment", lazy="selectin", cascade="all, delete-orphan")
