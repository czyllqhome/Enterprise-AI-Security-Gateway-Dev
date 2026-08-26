from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models.chat_log import ChatLog


class LogService:
    def __init__(self, db: Session):
        self.db = db

    def create_log(
        self,
        *,
        session_id: int,
        message_id: int,
        username: str,
        sanitized_content: str,
        detected_entity_types: list[str],
    ) -> ChatLog:
        log = ChatLog(
            session_id=session_id,
            message_id=message_id,
            username=username,
            original_sensitive_content=sanitized_content,
            detected_entity_types=detected_entity_types,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def list_logs(self, *, limit: int = 100, offset: int = 0) -> list[ChatLog]:
        stmt = (
            select(ChatLog)
            .order_by(desc(ChatLog.created_at), desc(ChatLog.id))
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 500))
        )
        return list(self.db.scalars(stmt).all())
