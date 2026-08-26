from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.config import Settings
from app.models.chat_session import ChatSession
from app.models.scan_event import ScanEvent
from app.models.user import User
from app.schemas.guardrail import GuardrailEntity, GuardrailScanResult
from app.schemas.messages import ChatConfirmRequest, ChatPreviewRequest
from app.services.chat_service import ChatService, ScanConfirmationError
from app.services.guardrails.business_sensitive_scanner import BusinessSensitiveResult
from app.services.guardrails.llm_guard_service import (
    GuardrailService,
    GuardrailUnavailableError,
    Qwen3GuardModerationResult,
)
from app.services.log_service import LogService
from app.services.scan_event_service import ScanEventService
from app.services.session_service import SessionService
from app.services.system_setting_service import SystemSettingService


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(autoflush=False, autocommit=False, bind=engine)
    session = local_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


class FakeGuardrailService:
    def __init__(self, result: GuardrailScanResult) -> None:
        self.result = result
        self.scan_calls = 0
        self.last_scan_kwargs = {}

    def scan_text(self, *_args, **kwargs) -> GuardrailScanResult:
        self.scan_calls += 1
        self.last_scan_kwargs = kwargs
        return self.result

    def get_config_fingerprint(self, *_args, **_kwargs) -> str:
        return "f" * 64

    def resolve_business_sensitive_runtime(self, _db):
        return object()

    def deanonymize_text(self, text: str, _entities: list[dict]) -> str:
        return text


class FakeLLMClient:
    def chat(self, _messages, _model: str) -> str:
        return "assistant reply"

    def stream_chat(self, _messages, _model: str):
        yield "assistant "
        yield "reply"


def build_chat_service(db_session, guardrail_service) -> ChatService:
    service = ChatService.__new__(ChatService)
    service.db = db_session
    service.session_service = SessionService(db_session)
    service.guardrail_service = guardrail_service
    service.log_service = LogService(db_session)
    service.scan_event_service = ScanEventService(db_session)
    service.setting_service = SystemSettingService(db_session)
    return service


def create_chat_session(db_session) -> ChatSession:
    db_session.add(
        User(
            username="alice",
            password_hash="unused",
            display_name="Alice",
            role="user",
            is_active=True,
        ),
    )
    session = ChatSession(title="Performance", created_by="alice", provider="ollama", model="demo")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def test_preview_and_confirm_execute_scanners_only_once(db_session, monkeypatch):
    session = create_chat_session(db_session)
    scan = GuardrailScanResult(
        original_text="hello",
        sanitized_text="hello",
        has_sensitive_data=False,
        entities=[],
        enabled_scanners=SystemSettingService(db_session).get_enabled_scanners(),
        scanner_timings={"qwen3guard": {"status": "ok", "total_ms": 10.0}},
        scan_duration_ms=12.0,
        business_sensitive_result=BusinessSensitiveResult(),
    )
    guardrail = FakeGuardrailService(scan)
    service = build_chat_service(db_session, guardrail)
    service.setting_service.set_scanner_strict_mode(False)
    monkeypatch.setattr("app.services.chat_service.get_llm_client", lambda *_args, **_kwargs: FakeLLMClient())

    preview = service.preview_message(
        ChatPreviewRequest(session_id=session.id, message="hello"),
        username="alice",
    )
    response = service.confirm_message(
        ChatConfirmRequest(
            session_id=session.id,
            original_message=preview.original_message,
            sanitized_message=preview.sanitized_message,
            scan_event_id=preview.scan_event_id,
            scan_proof=preview.scan_proof,
            detected_entities=preview.detected_entities,
        ),
        username="alice",
    )

    assert response.assistant_message.used_content == "assistant reply"
    assert guardrail.scan_calls == 1
    assert guardrail.last_scan_kwargs["strict_mode"] is False
    event = db_session.scalar(select(ScanEvent).where(ScanEvent.id == preview.scan_event_id))
    assert event is not None
    assert event.status == "confirmed_sent"
    assert event.consumed_at is not None
    assert event.scan_duration_ms == 12.0


def test_tampered_confirmation_is_rejected_without_rescan(db_session):
    session = create_chat_session(db_session)
    entity = GuardrailEntity(
        type="EMAIL_ADDRESS",
        original="alice@example.com",
        masked="a***@example.com",
        replacement="[REDACTED_EMAIL_ADDRESS_1]",
        start=0,
        end=17,
        source="custom_regex",
    )
    scan = GuardrailScanResult(
        original_text="alice@example.com",
        sanitized_text="[REDACTED_EMAIL_ADDRESS_1]",
        has_sensitive_data=True,
        entities=[entity],
        enabled_scanners=SystemSettingService(db_session).get_enabled_scanners(),
        business_sensitive_result=BusinessSensitiveResult(),
    )
    guardrail = FakeGuardrailService(scan)
    service = build_chat_service(db_session, guardrail)
    preview = service.preview_message(
        ChatPreviewRequest(session_id=session.id, message=scan.original_text),
        username="alice",
    )

    with pytest.raises(ScanConfirmationError):
        service.confirm_message(
            ChatConfirmRequest(
                session_id=session.id,
                original_message=preview.original_message,
                sanitized_message="tampered",
                scan_event_id=preview.scan_event_id,
                scan_proof=preview.scan_proof,
                detected_entities=preview.detected_entities,
            ),
            username="alice",
        )

    assert guardrail.scan_calls == 1
    event = db_session.scalar(select(ScanEvent).where(ScanEvent.id == preview.scan_event_id))
    assert event is not None and event.consumed_at is None


def test_streaming_confirmation_persists_only_after_completion(db_session, monkeypatch):
    session = create_chat_session(db_session)
    scan = GuardrailScanResult(
        original_text="hello stream",
        sanitized_text="hello stream",
        has_sensitive_data=False,
        entities=[],
        enabled_scanners=SystemSettingService(db_session).get_enabled_scanners(),
        business_sensitive_result=BusinessSensitiveResult(),
    )
    guardrail = FakeGuardrailService(scan)
    service = build_chat_service(db_session, guardrail)
    monkeypatch.setattr("app.services.chat_service.get_llm_client", lambda *_args, **_kwargs: FakeLLMClient())
    preview = service.preview_message(
        ChatPreviewRequest(session_id=session.id, message="hello stream"),
        username="alice",
    )

    events = list(
        service.confirm_message_stream(
            ChatConfirmRequest(
                session_id=session.id,
                original_message=preview.original_message,
                sanitized_message=preview.sanitized_message,
                scan_event_id=preview.scan_event_id,
                scan_proof=preview.scan_proof,
                detected_entities=preview.detected_entities,
            ),
            username="alice",
        )
    )

    assert [event["event"] for event in events] == ["accepted", "delta", "delta", "completed"]
    assert events[1]["text"] + events[2]["text"] == "assistant reply"
    event = db_session.scalar(select(ScanEvent).where(ScanEvent.id == preview.scan_event_id))
    assert event is not None and event.status == "confirmed_sent"


def test_heavy_scanners_run_in_parallel():
    service = GuardrailService.__new__(GuardrailService)
    service.settings = SimpleNamespace(scanner_total_deadline_ms=1000, scanner_strict_mode=True)
    service._executors = {
        name: ThreadPoolExecutor(max_workers=1)
        for name in ("qwen3guard", "privacy_filter", "business_sensitive", "bancode")
    }

    def delayed(value):
        time.sleep(0.15)
        return value

    service._scan_qwen3guard_or_raise = lambda _text: delayed(Qwen3GuardModerationResult())
    service._scan_privacy_filter_or_raise = lambda _text: delayed([])
    service._resolve_business_sensitive_runtime = lambda _db: object()
    service._scan_business_sensitive_or_raise = lambda _text, _runtime: delayed(BusinessSensitiveResult())
    service._scan_with_bancode = lambda _text: delayed(False)

    started = time.perf_counter()
    result = service.scan_text(
        "ordinary message",
        enabled_scanners=["bancode", "prompt_injection", "privacy_filter", "business_sensitive"],
    )
    elapsed = time.perf_counter() - started
    service.close()

    assert elapsed < 0.4
    assert result.degraded_scanners == []
    assert set(result.scanner_timings) == {
        "bancode",
        "qwen3guard",
        "privacy_filter",
        "business_sensitive",
    }


def test_scanner_strict_mode_is_persisted(db_session):
    service = SystemSettingService(db_session)

    assert service.set_scanner_strict_mode(False) is False
    assert SystemSettingService(db_session).get_scanner_strict_mode() is False
    assert service.set_scanner_strict_mode(True) is True
    assert SystemSettingService(db_session).get_scanner_strict_mode() is True


def test_runtime_strict_mode_override_controls_fail_closed_behavior():
    service = GuardrailService.__new__(GuardrailService)
    service.settings = SimpleNamespace(scanner_total_deadline_ms=1000, scanner_strict_mode=True)
    service._executors = {"privacy_filter": ThreadPoolExecutor(max_workers=1)}
    service._scan_privacy_filter_or_raise = lambda _text: (_ for _ in ()).throw(RuntimeError("unavailable"))

    with pytest.raises(GuardrailUnavailableError):
        service.scan_text("ordinary message", enabled_scanners=["privacy_filter"], strict_mode=True)

    result = service.scan_text("ordinary message", enabled_scanners=["privacy_filter"], strict_mode=False)
    service.close()

    assert result.degraded_scanners == ["privacy_filter"]
    assert result.scanner_timings["privacy_filter"]["status"] == "error"


def test_default_scan_deadline_allows_business_sensitive_timeout_to_finish():
    settings = Settings(_env_file=None)

    assert settings.business_sensitive_timeout_ms == 12000
    assert settings.business_sensitive_max_tokens == 1024
    assert settings.scanner_total_deadline_ms == 15000
    assert settings.scanner_total_deadline_ms > settings.business_sensitive_timeout_ms


def test_long_blocked_reason_is_persisted_without_truncation(db_session):
    session = create_chat_session(db_session)
    blocked_reason = "Blocked by prompt injection and business-sensitive policies. " * 12
    scan = GuardrailScanResult(
        original_text="blocked prompt",
        sanitized_text="blocked prompt",
        has_sensitive_data=False,
        entities=[],
        blocked_reason=blocked_reason,
        enabled_scanners=["prompt_injection", "business_sensitive"],
        scanners=["PromptInjection", "Business Sensitive"],
        business_sensitive_result=BusinessSensitiveResult(
            contains_business_sensitive=True,
            risk_level="high",
            summary="Synthetic high-risk result.",
        ),
    )

    event = ScanEventService(db_session).create_preview_event(
        session_id=session.id,
        username="alice",
        provider="ollama",
        model="demo",
        status="blocked",
        blocked_reason=blocked_reason,
        scan=scan,
    )
    db_session.commit()
    db_session.refresh(event)

    assert len(blocked_reason) > 255
    assert event.blocked_reason == blocked_reason
