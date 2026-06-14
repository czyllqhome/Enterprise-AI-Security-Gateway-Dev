from pydantic import BaseModel

from ..services.guardrails.business_sensitive_scanner import BusinessSensitiveResult


class GuardrailEntity(BaseModel):
    type: str
    original: str
    masked: str
    replacement: str
    start: int
    end: int
    source: str
    sources: list[str] = []


class GuardrailScanResult(BaseModel):
    original_text: str
    sanitized_text: str
    has_sensitive_data: bool
    entities: list[GuardrailEntity]
    bancode_triggered: bool = False
    prompt_injection_triggered: bool = False
    ban_topics_triggered: bool = False
    banned_topics: list[str] = []
    blocked_reason: str | None = None
    llm_guard_hit_count: int = 0
    secrets_hit_count: int = 0
    privacy_filter_hit_count: int = 0
    custom_regex_hit_count: int = 0
    scanners: list[str] = []
    enabled_scanners: list[str] = []
    entity_types: list[str] = []
    business_sensitive_result: BusinessSensitiveResult = BusinessSensitiveResult()
