from datetime import datetime

from pydantic import BaseModel

from .guardrail import GuardrailEntity
from ..services.guardrails.business_sensitive_scanner import BusinessSensitiveResult


class ConsoleSummaryResponse(BaseModel):
    provider: str
    model: str
    ready: bool
    active_scanner_count: int
    total_scans: int
    passed_count: int
    blocked_count: int
    pii_redaction_count: int
    monitored_username: str | None = None
    consecutive_trigger_count: int = 0
    total_trigger_count: int = 0
    alert_active: bool = False
    alert_message: str | None = None


class ScannerStatus(BaseModel):
    id: str
    name: str
    enabled: bool
    available: bool
    active: bool
    detail: str


class ConsoleScannersResponse(BaseModel):
    scanners: list[ScannerStatus]
    enabled_scanners: list[str]


class ConsoleScannersUpdateRequest(BaseModel):
    enabled_scanners: list[str]


class LastScanResponse(BaseModel):
    id: int | None
    session_id: int | None
    username: str | None
    provider: str
    model: str
    status: str
    blocked_reason: str | None
    has_sensitive_data: bool
    llm_guard_hit_count: int
    privacy_filter_hit_count: int
    custom_regex_hit_count: int
    scanners: list[str]
    entity_types: list[str]
    original_input: str
    sanitized_input: str
    detected_entities: list[GuardrailEntity]
    business_sensitive_result: BusinessSensitiveResult
    assistant_raw_output: str | None
    assistant_display_output: str | None
    created_at: datetime | None
    updated_at: datetime | None


class DashboardTrendPoint(BaseModel):
    label: str
    total: int
    blocked: int
    needs_review: int


class DashboardUseCaseSummary(BaseModel):
    key: str
    title: str
    description: str
    total: int
    blocked: int
    review_needed: int


class DashboardRiskUser(BaseModel):
    username: str
    total_events: int
    blocked_events: int
    review_events: int
    file_uploads: int
    latest_activity: datetime | None


class DashboardIncidentItem(BaseModel):
    channel: str
    severity: str
    title: str
    summary: str
    actor: str
    status: str
    created_at: datetime | None


class DashboardGovernanceSnapshot(BaseModel):
    active_scanners: int
    total_scanners: int
    bancode_enabled: bool
    bancode_available: bool
    bancode_active: bool
    configured_providers: int
    audit_logs: int
    uploaded_files: int
    high_risk_files: int


class DashboardRequestWindow(BaseModel):
    key: str
    label: str
    total: int
    blocked: int
    needs_review: int
    risk_count: int
    requests_per_minute: float
    sparkline: list[int]


class DashboardInterventionType(BaseModel):
    key: str
    label: str
    count: int
    description: str


class DashboardInterventionTrendSeries(BaseModel):
    key: str
    label: str
    points: list[int]


class ManagementDashboardResponse(BaseModel):
    total_requests: int
    blocked_requests: int
    review_required_requests: int
    pii_requests: int
    business_sensitive_requests: int
    confirmed_sensitive_sends: int
    active_users: int
    trend: list[DashboardTrendPoint]
    request_windows: list[DashboardRequestWindow]
    use_cases: list[DashboardUseCaseSummary]
    top_risk_users: list[DashboardRiskUser]
    incidents: list[DashboardIncidentItem]
    governance: DashboardGovernanceSnapshot
    intervention_types: list[DashboardInterventionType]
    intervention_trend: list[DashboardInterventionTrendSeries]
