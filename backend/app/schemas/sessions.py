from datetime import datetime

from pydantic import BaseModel

from .messages import MessageResponse


class SessionCreateRequest(BaseModel):
    title: str | None = None
    username: str | None = None
    provider: str | None = None
    model: str | None = None


class SessionSettingsUpdateRequest(BaseModel):
    provider: str
    model: str


class SessionSummary(BaseModel):
    id: int
    title: str
    created_by: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(SessionSummary):
    messages: list[MessageResponse]
