from datetime import datetime

from pydantic import BaseModel

from .guardrail import GuardrailEntity
from ..services.guardrails.business_sensitive_scanner import BusinessSensitiveResult


class MessageResponse(BaseModel):
    id: int
    role: str
    original_content: str | None
    sanitized_content: str | None
    used_content: str | None
    has_sensitive_data: bool
    sensitive_entities_json: list[dict] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatPreviewRequest(BaseModel):
    session_id: int
    message: str
    attachment_file_id: int | None = None
    username: str | None = None


class ChatPreviewResponse(BaseModel):
    scan_event_id: int | None = None
    session_id: int
    attachment_file_id: int | None = None
    status: str
    blocked_reason: str | None = None
    original_message: str
    sanitized_message: str
    detected_entities: list[GuardrailEntity]
    has_sensitive_data: bool
    llm_guard_hit_count: int
    secrets_hit_count: int
    privacy_filter_hit_count: int
    custom_regex_hit_count: int
    scanners: list[str]
    enabled_scanners: list[str]
    entity_types: list[str]
    business_sensitive_result: BusinessSensitiveResult


class ChatConfirmRequest(BaseModel):
    session_id: int
    original_message: str
    sanitized_message: str
    attachment_file_id: int | None = None
    username: str | None = None
    scan_event_id: int | None = None
    enabled_scanners: list[str] | None = None


class AssistantReplyResponse(BaseModel):
    session_id: int
    session_title: str
    user_message: MessageResponse
    assistant_message: MessageResponse
