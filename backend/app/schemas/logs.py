from datetime import datetime

from pydantic import BaseModel


class LogEntryResponse(BaseModel):
    id: int
    session_id: int | None
    message_id: int | None
    username: str
    sanitized_content: str
    detected_entity_types: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}
