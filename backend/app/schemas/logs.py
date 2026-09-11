from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LogEntryResponse(BaseModel):
    id: int
    session_id: int | None
    message_id: int | None
    scan_event_id: int | None
    username: str
    decision: Literal["allowed", "review", "blocked"]
    sanitized_content: str
    detected_entity_types: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}
