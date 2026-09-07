from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_file_review_permissions import db_session, create_user, create_completed_uploaded_file
from app.models.attachment import AttachmentIdentity
from app.models.chat_session import ChatSession
from app.schemas.guardrail import GuardrailScanResult
from app.schemas.messages import ChatPreviewRequest, ChatConfirmRequest
from app.services.attachment_integrity import sha256, review_policy_hash
from app.services.chat_service import ChatService, GuardrailViolationError
from app.services.system_setting_service import SystemSettingService


@pytest.fixture()
def chat(db_session, tmp_path, monkeypatch):
    user = create_user(db_session, "alice")
    session = ChatSession(title="Files", created_by="alice", provider="openai", model="verified")
    db_session.add(session)
    db_session.commit()
    content = b"original binary bytes"
    path = tmp_path / "file.pdf"
    path.write_bytes(content)
    record = create_completed_uploaded_file(db_session, uploaded_by="alice", filename="file.pdf",
                                           text="OCR_ONLY_MARKER")
    record.storage_path = str(path)
    identity = AttachmentIdentity(file_id=record.id, owner_user_id=user.id, sha256=sha256(content),
        verified_mime="application/pdf", reviewed_sha256=sha256(content), decision="allow",
        review_policy=review_policy_hash(SystemSettingService(db_session).get_enabled_scanners()))
    db_session.add(identity)
    db_session.commit()
    scans = []

    def scan(text, **kwargs):
        scans.append(text)
        return GuardrailScanResult(
            original_text=text,
            sanitized_text=text,
            has_sensitive_data=False,
            entities=[],
            enabled_scanners=kwargs.get("enabled_scanners") or [],
        )

    guard = SimpleNamespace(
        scan_text=scan,
        deanonymize_text=lambda text, _: text,
        resolve_business_sensitive_runtime=lambda _db: object(),
        get_config_fingerprint=lambda *args, **kwargs: "f" * 64,
    )
    model = SimpleNamespace(validate_attachments=Mock(), chat=Mock(return_value="Model answer"))
    monkeypatch.setattr("app.services.chat_service.get_guardrail_service", lambda: guard)
    monkeypatch.setattr("app.services.chat_service.get_llm_client", lambda *a, **kw: model)
    return SimpleNamespace(service=ChatService(db_session), session=session, record=record, identity=identity,
                           path=path, bytes=content, model=model, scans=scans, db=db_session)


def preview(chat, message="Summarize this file", file=True):
    return chat.service.preview_message(ChatPreviewRequest(session_id=chat.session.id, message=message,
        attachment_file_id=chat.record.id if file else None), "alice")


def confirmation(result):
    return ChatConfirmRequest(session_id=result.session_id, snapshot_id=result.snapshot_id,
        original_message=result.original_message, sanitized_message=result.sanitized_message,
        attachment_file_id=result.attachment_file_id, scan_event_id=result.scan_event_id,
        scan_proof=result.scan_proof, detected_entities=result.detected_entities)


def test_preview_confirm_transmits_file_and_keeps_user_text_separate(chat):
    result = preview(chat)
    assert result.original_message == "Summarize this file"
    answer = chat.service.confirm_message(confirmation(result), "alice")
    messages, _ = chat.model.chat.call_args.args
    assert messages[-1]["content"] == "Summarize this file"
    assert messages[-1]["attachments"][0].content == chat.bytes
    assert all("OCR_ONLY_MARKER" not in text for text in chat.scans)
    assert answer.user_message.used_content == "Summarize this file"
    assert answer.user_message.attachments[0].file_id == chat.record.id


def test_changed_original_never_reaches_model(chat):
    result = preview(chat)
    chat.path.write_bytes(b"changed")
    with pytest.raises(GuardrailViolationError, match="differs"):
        chat.service.confirm_message(confirmation(result), "alice")
    chat.model.chat.assert_not_called()


def test_confirm_cannot_substitute_prompt_or_attachment(chat):
    result = preview(chat)
    request = confirmation(result)
    request.original_message = "Different prompt"
    with pytest.raises(GuardrailViolationError, match="differs"):
        chat.service.confirm_message(request, "alice")
    request = confirmation(result)
    request.attachment_file_id = None
    with pytest.raises(GuardrailViolationError, match="differs"):
        chat.service.confirm_message(request, "alice")
    chat.model.chat.assert_not_called()


def test_repeated_confirm_returns_same_answer_without_calling_model_again(chat):
    request = confirmation(preview(chat))
    first = chat.service.confirm_message(request, "alice")
    second = chat.service.confirm_message(request, "alice")
    assert first.assistant_message.id == second.assistant_message.id
    assert chat.model.chat.call_count == 1


def test_followup_uses_original_history_reference(chat):
    chat.service.confirm_message(confirmation(preview(chat)), "alice")
    chat.service.confirm_message(confirmation(preview(chat, "Explain the last page", file=False)), "alice")
    messages, _ = chat.model.chat.call_args.args
    assert messages[1]["attachments"][0].content == chat.bytes
    assert messages[-1]["content"] == "Explain the last page"
    assert "attachments" not in messages[-1]


def test_review_revocation_between_preview_and_confirm_blocks_send(chat):
    request = confirmation(preview(chat))
    chat.identity.decision = "unknown"
    chat.db.commit()
    with pytest.raises(GuardrailViolationError, match="review policy"):
        chat.service.confirm_message(request, "alice")
    chat.model.chat.assert_not_called()


def test_model_failure_consumes_snapshot_and_does_not_retry(chat):
    request = confirmation(preview(chat))
    chat.model.chat.side_effect = TimeoutError("ambiguous response")
    with pytest.raises(TimeoutError):
        chat.service.confirm_message(request, "alice")
    with pytest.raises(GuardrailViolationError, match="uncertain"):
        chat.service.confirm_message(request, "alice")
    assert chat.model.chat.call_count == 1
