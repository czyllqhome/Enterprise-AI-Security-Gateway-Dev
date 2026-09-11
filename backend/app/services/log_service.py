from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models.chat_log import ChatLog


LogDecision = Literal["allowed", "review", "blocked"]


class LogService:
    def __init__(self, db: Session):
        self.db = db

    def create_log(
        self,
        *,
        session_id: int,
        message_id: int | None,
        scan_event_id: int | None,
        username: str,
        decision: LogDecision,
        sanitized_content: str,
        detected_entity_types: list[str],
    ) -> ChatLog:
        log = ChatLog(
            session_id=session_id,
            message_id=message_id,
            scan_event_id=scan_event_id,
            username=username,
            decision=decision,
            original_sensitive_content=sanitized_content,
            detected_entity_types=detected_entity_types,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def attach_message(self, *, scan_event_id: int, message_id: int) -> ChatLog | None:
        log = self.db.scalar(select(ChatLog).where(ChatLog.scan_event_id == scan_event_id))
        if log is not None:
            log.message_id = message_id
            self.db.flush()
        return log

    def list_logs(
        self,
        *,
        decision: LogDecision | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatLog]:
        stmt = select(ChatLog)
        if decision is not None:
            stmt = stmt.where(ChatLog.decision == decision)
        stmt = (
            stmt
            .order_by(desc(ChatLog.created_at), desc(ChatLog.id))
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 500))
        )
        return list(self.db.scalars(stmt).all())
