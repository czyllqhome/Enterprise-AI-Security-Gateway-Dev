from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class ScanEvent(Base):
    __tablename__ = "scan_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="SET NULL"), index=True, nullable=True)
    username: Mapped[str] = mapped_column(String(128), default="Guest", nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="openai", nullable=False)
    model: Mapped[str] = mapped_column(String(128), default="gpt-4.1-mini", nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(255))
    has_sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    llm_guard_hit_count: Mapped[int] = mapped_column(default=0, nullable=False)
    privacy_filter_hit_count: Mapped[int] = mapped_column(default=0, nullable=False)
    custom_regex_hit_count: Mapped[int] = mapped_column(default=0, nullable=False)
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_input: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_raw_output: Mapped[str | None] = mapped_column(Text)
    assistant_display_output: Mapped[str | None] = mapped_column(Text)
    scanners_json: Mapped[list[str] | None] = mapped_column(JSON)
    entity_types_json: Mapped[list[str] | None] = mapped_column(JSON)
    detected_entities_json: Mapped[list[dict] | None] = mapped_column(JSON)
    business_sensitive_result_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
