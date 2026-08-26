from typing import Any

from pydantic import BaseModel, Field

from ..services.guardrails.business_sensitive_scanner import BusinessSensitiveResult


class GuardrailEntity(BaseModel):
    type: str
    original: str
    masked: str
    replacement: str
    start: int
    end: int
    source: str
    sources: list[str] = Field(default_factory=list)


class GuardrailScanResult(BaseModel):
    original_text: str
    sanitized_text: str
    has_sensitive_data: bool
    entities: list[GuardrailEntity]
    bancode_triggered: bool = False
    prompt_injection_triggered: bool = False
    ban_topics_triggered: bool = False
    banned_topics: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    llm_guard_hit_count: int = 0
    secrets_hit_count: int = 0
    privacy_filter_hit_count: int = 0
    custom_regex_hit_count: int = 0
    scanners: list[str] = Field(default_factory=list)
    enabled_scanners: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    scanner_timings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    degraded_scanners: list[str] = Field(default_factory=list)
    scan_duration_ms: float = 0.0
    business_sensitive_result: BusinessSensitiveResult = BusinessSensitiveResult()
