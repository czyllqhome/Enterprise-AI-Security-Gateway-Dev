from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True, nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True, nullable=True)
    username: Mapped[str] = mapped_column(String(128), default="Guest", nullable=False)
    original_sensitive_content: Mapped[str] = mapped_column(Text, nullable=False)
    detected_entity_types: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def sanitized_content(self) -> str:
        return self.original_sensitive_content
