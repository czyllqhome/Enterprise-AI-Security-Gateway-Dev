from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.scan_event import ScanEvent
from ..schemas.guardrail import GuardrailEntity, GuardrailScanResult


class ScanEventService:
    def __init__(self, db: Session):
        self.db = db

    def create_preview_event(
        self,
        *,
        session_id: int,
        username: str,
        provider: str,
        model: str,
        status: str,
        blocked_reason: str | None,
        scan: GuardrailScanResult,
    ) -> ScanEvent:
        event = ScanEvent(
            session_id=session_id,
            username=username,
            provider=provider,
            model=model,
            status=status,
            blocked_reason=blocked_reason,
            has_sensitive_data=scan.has_sensitive_data,
            llm_guard_hit_count=scan.llm_guard_hit_count,
            privacy_filter_hit_count=scan.privacy_filter_hit_count,
            custom_regex_hit_count=scan.custom_regex_hit_count,
            original_input="",
            sanitized_input=scan.sanitized_text,
            scanners_json=scan.scanners,
            entity_types_json=scan.entity_types,
            detected_entities_json=[self._safe_entity_dump(entity) for entity in scan.entities],
            business_sensitive_result_json=scan.business_sensitive_result.model_dump(),
            scan_duration_ms=scan.scan_duration_ms,
            scanner_timings_json=scan.scanner_timings,
            degraded_scanners_json=scan.degraded_scanners or None,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _safe_entity_dump(self, entity: GuardrailEntity) -> dict:
        data = entity.model_dump()
        data["original"] = ""
        return data

    def get_event(self, event_id: int) -> ScanEvent | None:
        return self.db.scalar(select(ScanEvent).where(ScanEvent.id == event_id))

    def get_event_for_confirmation(
        self,
        event_id: int,
        *,
        session_id: int,
        username: str,
        lock: bool = False,
    ) -> ScanEvent | None:
        stmt = select(ScanEvent).where(
            ScanEvent.id == event_id,
            ScanEvent.session_id == session_id,
            ScanEvent.username == username,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def claim_for_confirmation(self, event: ScanEvent) -> ScanEvent:
        if event.consumed_at is not None or event.status not in {"clean", "needs_confirmation"}:
            raise ValueError("Scan event has already been consumed or is not confirmable.")
        event.consumed_at = datetime.now(UTC)
        event.status = "sending"
        self.db.flush()
        return event

    def mark_confirmed(self, event: ScanEvent, *, assistant_raw_output: str, assistant_display_output: str) -> ScanEvent:
        event.status = "confirmed_sent"
        event.blocked_reason = None
        event.assistant_raw_output = assistant_raw_output
        event.assistant_display_output = assistant_display_output
        self.db.flush()
        return event

    def mark_rejected(self, event: ScanEvent, reason: str) -> ScanEvent:
        event.status = "rejected"
        event.blocked_reason = reason
        self.db.flush()
        return event

    def mark_send_failed(self, event: ScanEvent, reason: str) -> ScanEvent:
        event.status = "send_failed"
        event.blocked_reason = reason
        self.db.flush()
        return event
