from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models.chat_log import ChatLog
from ..models.provider_credential import ProviderCredential
from ..models.scan_event import ScanEvent
from ..models.uploaded_file import UploadedFile
from ..schemas.console import (
    ConsoleScannersResponse,
    ConsoleSummaryResponse,
    DashboardGovernanceSnapshot,
    DashboardInterventionTrendSeries,
    DashboardInterventionType,
    DashboardIncidentItem,
    DashboardRequestWindow,
    DashboardRiskUser,
    DashboardTrendPoint,
    DashboardUseCaseSummary,
    LastScanResponse,
    ManagementDashboardResponse,
    ScannerStatus,
)
from ..schemas.guardrail import GuardrailEntity
from .guardrails.business_sensitive_scanner import BusinessSensitiveResult
from .guardrails.llm_guard_service import get_guardrail_service
from .system_setting_service import INPUT_SCANNER_IDS, SystemSettingService


class ConsoleService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.guardrail_service = get_guardrail_service()
        self.setting_service = SystemSettingService(db)

    def get_summary(self, username: str | None = None) -> ConsoleSummaryResponse:
        total_scans = self.db.scalar(select(func.count(ScanEvent.id))) or 0
        passed_count = self.db.scalar(
            select(func.count(ScanEvent.id)).where(ScanEvent.status.in_(["clean", "confirmed_sent"]))
        ) or 0
        blocked_count = self.db.scalar(
            select(func.count(ScanEvent.id)).where(ScanEvent.status.in_(["blocked", "rejected"]))
        ) or 0
        pii_redaction_count = self.db.scalar(
            select(func.count(ScanEvent.id)).where(ScanEvent.has_sensitive_data.is_(True))
        ) or 0

        scanners = self.get_scanners().scanners
        active_scanner_count = sum(
            1
            for scanner in scanners
            if scanner.id in INPUT_SCANNER_IDS and scanner.active
        )
        normalized_username = (username or "").strip() or None
        consecutive_trigger_count = self._get_consecutive_trigger_count(normalized_username)
        total_trigger_count = self._get_total_trigger_count(normalized_username)
        alert_active = consecutive_trigger_count >= 5
        alert_message = None
        if alert_active and normalized_username:
            alert_message = (
                f"User {normalized_username} has triggered security scanners "
                f"{total_trigger_count} times in total. Current consecutive streak: "
                f"{consecutive_trigger_count}. Review recent activity now."
            )
        return ConsoleSummaryResponse(
            provider=self.settings.default_provider,
            model=self.settings.default_model,
            ready=True,
            active_scanner_count=active_scanner_count,
            total_scans=int(total_scans),
            passed_count=int(passed_count),
            blocked_count=int(blocked_count),
            pii_redaction_count=int(pii_redaction_count),
            monitored_username=normalized_username,
            consecutive_trigger_count=consecutive_trigger_count,
            total_trigger_count=total_trigger_count,
            alert_active=alert_active,
            alert_message=alert_message,
        )

    def get_scanners(self) -> ConsoleScannersResponse:
        availability = self.guardrail_service.get_scanner_availability()
        runtime_details = self.guardrail_service.get_scanner_runtime_details()
        enabled_scanners = self.setting_service.get_enabled_scanners()
        enabled_set = set(enabled_scanners)
        scanners = [
            ScannerStatus(
                id="bancode",
                name="BanCode",
                enabled="bancode" in enabled_set,
                available=availability["bancode"],
                active="bancode" in enabled_set and availability["bancode"],
                detail=runtime_details["BanCode"],
            ),
            ScannerStatus(
                id="prompt_injection",
                name="PromptInjection",
                enabled="prompt_injection" in enabled_set,
                available=availability["prompt_injection"],
                active="prompt_injection" in enabled_set and availability["prompt_injection"],
                detail=runtime_details["PromptInjection"],
            ),
            ScannerStatus(
                id="ban_topics",
                name="BanTopics",
                enabled="ban_topics" in enabled_set,
                available=availability["ban_topics"],
                active="ban_topics" in enabled_set and availability["ban_topics"],
                detail=runtime_details["BanTopics"],
            ),
            ScannerStatus(
                id="privacy_filter",
                name="Privacy Filter",
                enabled="privacy_filter" in enabled_set,
                available=availability["privacy_filter"],
                active="privacy_filter" in enabled_set and availability["privacy_filter"],
                detail=runtime_details["Privacy Filter"],
            ),
            ScannerStatus(
                id="business_sensitive",
                name="Business Sensitive",
                enabled="business_sensitive" in enabled_set,
                available=availability["business_sensitive"],
                active="business_sensitive" in enabled_set and availability["business_sensitive"],
                detail=runtime_details["Business Sensitive"],
            ),
            ScannerStatus(
                id="custom_regex",
                name="Custom Regex",
                enabled="custom_regex" in enabled_set,
                available=True,
                active="custom_regex" in enabled_set,
                detail=runtime_details["Custom Regex"],
            ),
            ScannerStatus(
                id="deanonymize",
                name="Deanonymize",
                enabled=availability["deanonymize"],
                available=availability["deanonymize"],
                active=availability["deanonymize"],
                detail=runtime_details["Deanonymize"],
            ),
        ]
        return ConsoleScannersResponse(scanners=scanners, enabled_scanners=enabled_scanners)

    def update_scanners(self, enabled_scanners: list[str]) -> ConsoleScannersResponse:
        self.setting_service.set_enabled_scanners(enabled_scanners)
        return self.get_scanners()

    def get_last_scan(self) -> LastScanResponse:
        event = self.db.scalar(select(ScanEvent).order_by(ScanEvent.updated_at.desc(), ScanEvent.id.desc()))
        if event is None:
            return LastScanResponse(
                id=None,
                session_id=None,
                username=None,
                provider=self.settings.default_provider,
                model=self.settings.default_model,
                status="idle",
                blocked_reason=None,
                has_sensitive_data=False,
                llm_guard_hit_count=0,
                privacy_filter_hit_count=0,
                custom_regex_hit_count=0,
                scanners=[],
                entity_types=[],
                original_input="",
                sanitized_input="",
                detected_entities=[],
                business_sensitive_result=BusinessSensitiveResult(),
                assistant_raw_output=None,
                assistant_display_output=None,
                created_at=None,
                updated_at=None,
            )

        return LastScanResponse(
            id=event.id,
            session_id=event.session_id,
            username=event.username,
            provider=event.provider,
            model=event.model,
            status=event.status,
            blocked_reason=event.blocked_reason,
            has_sensitive_data=event.has_sensitive_data,
            llm_guard_hit_count=event.llm_guard_hit_count,
            privacy_filter_hit_count=event.privacy_filter_hit_count,
            custom_regex_hit_count=event.custom_regex_hit_count,
            scanners=event.scanners_json or [],
            entity_types=event.entity_types_json or [],
            original_input=event.original_input,
            sanitized_input=event.sanitized_input,
            detected_entities=[GuardrailEntity.model_validate(entity) for entity in (event.detected_entities_json or [])],
            business_sensitive_result=BusinessSensitiveResult.model_validate(event.business_sensitive_result_json or {}),
            assistant_raw_output=event.assistant_raw_output,
            assistant_display_output=event.assistant_display_output,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def get_management_dashboard(self) -> ManagementDashboardResponse:
        scan_events = list(self.db.scalars(select(ScanEvent).order_by(ScanEvent.created_at.desc(), ScanEvent.id.desc())).all())
        uploaded_files = list(
            self.db.scalars(select(UploadedFile).order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())).all()
        )
        logs = list(self.db.scalars(select(ChatLog).order_by(ChatLog.created_at.desc(), ChatLog.id.desc())).all())

        total_requests = len(scan_events)
        blocked_requests = sum(1 for event in scan_events if event.status in {"blocked", "rejected"})
        review_required_requests = sum(1 for event in scan_events if event.status == "needs_confirmation")
        pii_requests = sum(1 for event in scan_events if event.has_sensitive_data)
        business_sensitive_requests = sum(1 for event in scan_events if self._is_business_sensitive(event))
        confirmed_sensitive_sends = sum(1 for event in scan_events if event.status == "confirmed_sent")
        active_users = len(
            {
                username.strip().lower()
                for username in [*(event.username for event in scan_events), *(file.uploaded_by for file in uploaded_files)]
                if (username or "").strip()
            }
        )

        return ManagementDashboardResponse(
            total_requests=total_requests,
            blocked_requests=blocked_requests,
            review_required_requests=review_required_requests,
            pii_requests=pii_requests,
            business_sensitive_requests=business_sensitive_requests,
            confirmed_sensitive_sends=confirmed_sensitive_sends,
            active_users=active_users,
            trend=self._build_trend(scan_events),
            request_windows=self._build_request_windows(scan_events),
            use_cases=self._build_use_case_summary(scan_events, uploaded_files),
            top_risk_users=self._build_top_risk_users(scan_events, uploaded_files),
            incidents=self._build_incidents(scan_events, uploaded_files, logs),
            governance=self._build_governance_snapshot(uploaded_files, logs),
            intervention_types=self._build_intervention_types(scan_events, uploaded_files),
            intervention_trend=self._build_intervention_trend(scan_events),
        )

    def _get_consecutive_trigger_count(self, username: str | None) -> int:
        if not username:
            return 0

        normalized_username = username.strip().lower()
        stmt = (
            select(ScanEvent)
            .where(func.lower(ScanEvent.username) == normalized_username)
            .order_by(ScanEvent.updated_at.desc(), ScanEvent.id.desc())
        )
        events = list(self.db.scalars(stmt).all())
        streak = 0
        for event in events:
            if event.scanners_json:
                streak += 1
                continue
            break
        return streak

    def _get_total_trigger_count(self, username: str | None) -> int:
        if not username:
            return 0
        normalized_username = username.strip().lower()
        stmt = select(func.count(ScanEvent.id)).where(
            func.lower(ScanEvent.username) == normalized_username,
            ScanEvent.scanners_json.is_not(None),
        )
        return int(self.db.scalar(stmt) or 0)

    def _has_recent_scanner_hit(self, scanner_name: str) -> bool:
        stmt = select(ScanEvent).order_by(ScanEvent.updated_at.desc(), ScanEvent.id.desc()).limit(20)
        events = list(self.db.scalars(stmt).all())
        return any(scanner_name in (event.scanners_json or []) for event in events)

    def _build_trend(self, scan_events: list[ScanEvent]) -> list[DashboardTrendPoint]:
        today = datetime.now().date()
        buckets = []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            day_events = [event for event in scan_events if event.created_at and event.created_at.date() == day]
            buckets.append(
                DashboardTrendPoint(
                    label=day.strftime("%m-%d"),
                    total=len(day_events),
                    blocked=sum(1 for event in day_events if event.status in {"blocked", "rejected"}),
                    needs_review=sum(1 for event in day_events if event.status in {"needs_confirmation", "confirmed_sent"}),
                )
            )
        return buckets

    def _build_request_windows(self, scan_events: list[ScanEvent]) -> list[DashboardRequestWindow]:
        now = datetime.now()
        specs = [
            ("1h", "1H", timedelta(hours=1)),
            ("6h", "6H", timedelta(hours=6)),
            ("24h", "24H", timedelta(hours=24)),
            ("7d", "7D", timedelta(days=7)),
            ("1m", "1M", timedelta(days=30)),
            ("3m", "3M", timedelta(days=90)),
            ("6m", "6M", timedelta(days=180)),
            ("1y", "1Y", timedelta(days=365)),
        ]
        windows = []
        for key, label, duration in specs:
            start = now - duration
            window_events = [
                event
                for event in scan_events
                if event.created_at and self._normalize_datetime(event.created_at) >= start
            ]
            blocked = sum(1 for event in window_events if event.status in {"blocked", "rejected"})
            needs_review = sum(1 for event in window_events if event.status in {"needs_confirmation", "confirmed_sent"})
            risk_count = sum(1 for event in window_events if self._is_risk_event(event))
            minutes = max(duration.total_seconds() / 60, 1)
            windows.append(
                DashboardRequestWindow(
                    key=key,
                    label=label,
                    total=len(window_events),
                    blocked=blocked,
                    needs_review=needs_review,
                    risk_count=risk_count,
                    requests_per_minute=round(len(window_events) / minutes, 2),
                    sparkline=self._build_window_sparkline(window_events, start, duration),
                )
            )
        return windows

    def _build_window_sparkline(
        self,
        window_events: list[ScanEvent],
        start: datetime,
        duration: timedelta,
        bucket_count: int = 24,
    ) -> list[int]:
        buckets = [0 for _ in range(bucket_count)]
        bucket_seconds = max(duration.total_seconds() / bucket_count, 1)
        for event in window_events:
            created_at = self._normalize_datetime(event.created_at)
            index = int((created_at - start).total_seconds() / bucket_seconds)
            index = min(max(index, 0), bucket_count - 1)
            buckets[index] += 1
        return buckets

    def _build_intervention_types(
        self,
        scan_events: list[ScanEvent],
        uploaded_files: list[UploadedFile],
    ) -> list[DashboardInterventionType]:
        counts = Counter()
        descriptions = {
            "prompt_injection": "Prompt injection, jailbreak, or system-policy bypass attempts.",
            "source_code": "Source code, code-like content, or proprietary implementation details.",
            "restricted_topic": "Disallowed HR, safety, harassment, or restricted-topic content.",
            "pii_or_secret": "Personal data, credentials, API keys, tokens, or other secrets.",
            "business_sensitive": "Contracts, pricing, bids, product specifications, or customer intelligence.",
            "document_risk": "Uploaded documents flagged as medium or high risk.",
            "manual_rejection": "Requests rejected after the guardrail review flow.",
            "other": "Other guardrail interventions that do not map cleanly to a known category.",
        }
        labels = {
            "prompt_injection": "Prompt Injection",
            "source_code": "Source Code",
            "restricted_topic": "Restricted Topic",
            "pii_or_secret": "PII / Secrets",
            "business_sensitive": "Business Sensitive",
            "document_risk": "Document Risk",
            "manual_rejection": "Manual Rejection",
            "other": "Other",
        }

        for event in scan_events:
            has_intervention = event.status in {"blocked", "rejected", "needs_confirmation", "confirmed_sent"}
            if not has_intervention:
                continue

            matched = False
            scanners = {str(scanner).lower() for scanner in (event.scanners_json or [])}
            entity_types = {str(entity_type).lower() for entity_type in (event.entity_types_json or [])}
            blocked_reason = (event.blocked_reason or "").lower()

            if any("prompt" in scanner and "injection" in scanner for scanner in scanners) or "injection" in blocked_reason:
                counts["prompt_injection"] += 1
                matched = True
            if any("bancode" in scanner or "code" == scanner for scanner in scanners) or "source code" in blocked_reason:
                counts["source_code"] += 1
                matched = True
            if any("bantopics" in scanner or "topic" in scanner for scanner in scanners) or "topic" in blocked_reason:
                counts["restricted_topic"] += 1
                matched = True
            if event.has_sensitive_data or any(
                token in " ".join(entity_types)
                for token in ["phone", "email", "credit", "id", "secret", "api", "token", "password"]
            ):
                counts["pii_or_secret"] += 1
                matched = True
            if self._is_business_sensitive(event):
                counts["business_sensitive"] += 1
                matched = True
            if event.status == "rejected":
                counts["manual_rejection"] += 1
                matched = True
            if not matched:
                counts["other"] += 1

        for record in uploaded_files:
            risk_level = str((record.review_result_json or {}).get("risk_level", "low")).lower()
            if risk_level in {"medium", "high"} or record.status == "failed":
                counts["document_risk"] += 1

        items = [
            DashboardInterventionType(
                key=key,
                label=labels[key],
                count=int(count),
                description=descriptions[key],
            )
            for key, count in counts.items()
            if count > 0
        ]
        items.sort(key=lambda item: item.count, reverse=True)
        return items

    def _build_intervention_trend(self, scan_events: list[ScanEvent]) -> list[DashboardInterventionTrendSeries]:
        labels = {
            "prompt_injection": "Prompt Injection",
            "pii_or_secret": "PII Detection",
            "business_sensitive": "Business-Sensitive",
            "source_code": "Source Code",
            "restricted_topic": "Restricted Topic",
            "other": "Other",
        }
        now = datetime.now()
        start = now - timedelta(hours=24)
        bucket_count = 12
        bucket_seconds = 24 * 60 * 60 / bucket_count
        series: dict[str, list[int]] = {key: [0 for _ in range(bucket_count)] for key in labels}

        for event in scan_events:
            if not event.created_at:
                continue
            created_at = self._normalize_datetime(event.created_at)
            if created_at < start:
                continue
            index = int((created_at - start).total_seconds() / bucket_seconds)
            index = min(max(index, 0), bucket_count - 1)
            for key in self._event_intervention_keys(event):
                if key in series:
                    series[key][index] += 1

        result = [
            DashboardInterventionTrendSeries(key=key, label=labels[key], points=points)
            for key, points in series.items()
            if sum(points) > 0
        ]
        result.sort(key=lambda item: sum(item.points), reverse=True)
        return result[:4]

    def _build_use_case_summary(
        self,
        scan_events: list[ScanEvent],
        uploaded_files: list[UploadedFile],
    ) -> list[DashboardUseCaseSummary]:
        use_case_meta = {
            "sales_ops": ("Sales And Contracts", "报价、合同、招投标、客户方案外发"),
            "hr_ops": ("HR And Recruiting", "简历筛选、招聘文案、候选人资料处理"),
            "engineering": ("Engineering And Code", "源码、密钥、内部系统提示词与研发资料"),
            "privacy_ops": ("Privacy And Customer Data", "客户资料、证件号、电话、邮箱等个人信息"),
            "document_review": ("Document Review", "上传文件的商业敏感审查与外发前复核"),
        }
        counts: dict[str, Counter] = {key: Counter() for key in use_case_meta}

        for event in scan_events:
            matched = self._classify_use_cases(event.original_input or "")
            if event.has_sensitive_data and "privacy_ops" not in matched:
                matched.append("privacy_ops")
            if self._is_business_sensitive(event) and "sales_ops" not in matched:
                matched.append("sales_ops")
            for key in set(matched):
                counts[key]["total"] += 1
                if event.status in {"blocked", "rejected"}:
                    counts[key]["blocked"] += 1
                if event.status in {"needs_confirmation", "confirmed_sent"}:
                    counts[key]["review_needed"] += 1

        for record in uploaded_files:
            matched = self._classify_use_cases(
                " ".join(filter(None, [record.original_filename, record.extraction_summary, record.extracted_text]))
            )
            matched.append("document_review")
            risk_level = str((record.review_result_json or {}).get("risk_level", "low")).lower()
            for key in set(matched):
                counts[key]["total"] += 1
                if risk_level == "high" or record.status == "failed":
                    counts[key]["blocked"] += 1
                if risk_level in {"medium", "high"}:
                    counts[key]["review_needed"] += 1

        result = []
        for key, (title, description) in use_case_meta.items():
            result.append(
                DashboardUseCaseSummary(
                    key=key,
                    title=title,
                    description=description,
                    total=counts[key]["total"],
                    blocked=counts[key]["blocked"],
                    review_needed=counts[key]["review_needed"],
                )
            )
        result.sort(key=lambda item: (item.total, item.review_needed, item.blocked), reverse=True)
        return result

    def _build_top_risk_users(
        self,
        scan_events: list[ScanEvent],
        uploaded_files: list[UploadedFile],
    ) -> list[DashboardRiskUser]:
        per_user: dict[str, dict[str, int | datetime | None]] = {}

        def ensure_user(username: str) -> dict[str, int | datetime | None]:
            key = username or "Guest"
            if key not in per_user:
                per_user[key] = {
                    "total_events": 0,
                    "blocked_events": 0,
                    "review_events": 0,
                    "file_uploads": 0,
                    "latest_activity": None,
                }
            return per_user[key]

        for event in scan_events:
            bucket = ensure_user(event.username)
            bucket["total_events"] += 1
            if event.status in {"blocked", "rejected"}:
                bucket["blocked_events"] += 1
            if event.status in {"needs_confirmation", "confirmed_sent"}:
                bucket["review_events"] += 1
            if self._is_newer(event.created_at, bucket["latest_activity"]):
                bucket["latest_activity"] = event.created_at

        for record in uploaded_files:
            bucket = ensure_user(record.uploaded_by)
            bucket["file_uploads"] += 1
            if self._is_newer(record.created_at, bucket["latest_activity"]):
                bucket["latest_activity"] = record.created_at

        users = [
            DashboardRiskUser(username=username, **values)
            for username, values in per_user.items()
            if values["total_events"] or values["file_uploads"]
        ]
        users.sort(
            key=lambda item: (item.blocked_events, item.review_events, item.total_events, item.file_uploads),
            reverse=True,
        )
        return users[:10]

    def _build_incidents(
        self,
        scan_events: list[ScanEvent],
        uploaded_files: list[UploadedFile],
        logs: list[ChatLog],
    ) -> list[DashboardIncidentItem]:
        incidents: list[DashboardIncidentItem] = []

        for event in scan_events[:10]:
            if event.status not in {"blocked", "confirmed_sent", "needs_confirmation", "rejected"}:
                continue
            severity = "medium"
            if event.status in {"blocked", "rejected"}:
                severity = "high"
            elif self._is_business_sensitive(event) or event.has_sensitive_data:
                severity = "medium"
            incidents.append(
                DashboardIncidentItem(
                    channel="chat",
                    severity=severity,
                    title=self._build_incident_title(event),
                    summary=(event.blocked_reason or event.original_input or "")[:160] or "Prompt entered review flow.",
                    actor=event.username or "Guest",
                    status=event.status,
                    created_at=event.created_at,
                )
            )

        for record in uploaded_files[:8]:
            risk_level = str((record.review_result_json or {}).get("risk_level", "low")).lower()
            if risk_level == "low" and record.status != "failed":
                continue
            incidents.append(
                DashboardIncidentItem(
                    channel="file",
                    severity="high" if risk_level == "high" or record.status == "failed" else "medium",
                    title=f"File review: {record.original_filename}",
                    summary=((record.review_result_json or {}).get("summary") or record.error_message or "File queued for review.")[
                        :160
                    ],
                    actor=record.uploaded_by or "Guest",
                    status=record.status,
                    created_at=record.created_at,
                )
            )

        for log in logs[:5]:
            incidents.append(
                DashboardIncidentItem(
                    channel="audit",
                    severity="medium",
                    title="Sensitive content was sent after confirmation",
                    summary=(log.original_sensitive_content or "")[:160],
                    actor=log.username or "Guest",
                    status="logged",
                    created_at=log.created_at,
                )
            )

        incidents.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
        return incidents[:8]

    def _build_governance_snapshot(
        self,
        uploaded_files: list[UploadedFile],
        logs: list[ChatLog],
    ) -> DashboardGovernanceSnapshot:
        scanners = self.get_scanners().scanners
        bancode = next((scanner for scanner in scanners if scanner.id == "bancode"), None)
        configured_providers = int(self.db.scalar(select(func.count(ProviderCredential.id))) or 0)
        high_risk_files = sum(
            1 for record in uploaded_files if str((record.review_result_json or {}).get("risk_level", "low")).lower() == "high"
        )
        return DashboardGovernanceSnapshot(
            active_scanners=sum(1 for scanner in scanners if scanner.active),
            total_scanners=len(scanners),
            bancode_enabled=bool(bancode and bancode.enabled),
            bancode_available=bool(bancode and bancode.available),
            bancode_active=bool(bancode and bancode.active),
            configured_providers=configured_providers,
            audit_logs=len(logs),
            uploaded_files=len(uploaded_files),
            high_risk_files=high_risk_files,
        )

    def _build_incident_title(self, event: ScanEvent) -> str:
        if event.status in {"blocked", "rejected"}:
            return "Prompt blocked by policy"
        if self._is_business_sensitive(event):
            return "Business-sensitive prompt entered review"
        if event.has_sensitive_data:
            return "PII or secrets detected before send"
        return "Prompt entered guardrail review"

    def _is_business_sensitive(self, event: ScanEvent) -> bool:
        payload = event.business_sensitive_result_json or {}
        return bool(payload.get("contains_business_sensitive"))

    def _is_risk_event(self, event: ScanEvent) -> bool:
        return bool(
            event.status in {"blocked", "rejected", "needs_confirmation", "confirmed_sent"}
            or event.has_sensitive_data
            or self._is_business_sensitive(event)
        )

    def _event_intervention_keys(self, event: ScanEvent) -> list[str]:
        keys: list[str] = []
        scanners = {str(scanner).lower() for scanner in (event.scanners_json or [])}
        entity_types = {str(entity_type).lower() for entity_type in (event.entity_types_json or [])}
        blocked_reason = (event.blocked_reason or "").lower()

        if any("prompt" in scanner and "injection" in scanner for scanner in scanners) or "injection" in blocked_reason:
            keys.append("prompt_injection")
        if any("bancode" in scanner or "code" == scanner for scanner in scanners) or "source code" in blocked_reason:
            keys.append("source_code")
        if any("bantopics" in scanner or "topic" in scanner for scanner in scanners) or "topic" in blocked_reason:
            keys.append("restricted_topic")
        if event.has_sensitive_data or any(
            token in " ".join(entity_types)
            for token in ["phone", "email", "credit", "id", "secret", "api", "token", "password"]
        ):
            keys.append("pii_or_secret")
        if self._is_business_sensitive(event):
            keys.append("business_sensitive")
        if event.status == "rejected":
            keys.append("manual_rejection")
        if event.status in {"blocked", "rejected", "needs_confirmation", "confirmed_sent"} and not keys:
            keys.append("other")
        return keys

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.replace(tzinfo=None)

    def _classify_use_cases(self, text: str) -> list[str]:
        lowered = (text or "").lower()
        matched: list[str] = []
        keyword_map = {
            "sales_ops": [
                "合同", "报价", "招标", "投标", "客户", "pricing", "quote", "contract", "tender", "procurement",
            ],
            "hr_ops": [
                "招聘", "候选", "简历", "岗位", "面试", "candidate", "resume", "recruit", "hiring", "cv",
            ],
            "engineering": [
                "代码", "源码", "api_key", "token", "password", "repo", "github", "prompt injection", "system prompt", "code",
            ],
            "privacy_ops": [
                "身份证", "电话", "邮箱", "信用卡", "患者", "病历", "customer", "email", "phone", "passport", "ssn",
            ],
            "document_review": [
                ".pdf", ".docx", ".xlsx", ".pptx", "附件", "文件", "upload", "document",
            ],
        }
        for key, keywords in keyword_map.items():
            if any(keyword in lowered for keyword in keywords):
                matched.append(key)
        return matched

    def _is_newer(self, candidate: datetime | None, current: datetime | None) -> bool:
        if candidate is None:
            return False
        if current is None:
            return True
        return candidate > current
