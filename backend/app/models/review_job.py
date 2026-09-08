from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db import Base


class ReviewJob(Base):
    __tablename__ = "file_review_jobs"
    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
