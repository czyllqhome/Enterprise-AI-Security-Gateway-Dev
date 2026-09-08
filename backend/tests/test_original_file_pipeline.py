import json
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy.orm import sessionmaker

from test_file_review_permissions import db_session, create_user, pdf_bytes
from app.models.attachment import AttachmentIdentity
from app.models.uploaded_file import UploadedFile
from app.schemas.guardrail import GuardrailScanResult
from app.schemas.file_review import FileStorageSettingsUpdateRequest
from app.services.file_review_service import FileReviewService, UploadedFilePayload
from app.services.file_review_scanner import FileReviewScanner
from app.services.file_extraction_service import FileExtractionService
from app.services.attachment_access_service import AttachmentAccessService
from app.services.attachment_integrity import sha256


def test_review_proof_is_bound_to_original_bytes(db_session, tmp_path, monkeypatch):
    create_user(db_session, "alice")
    scanner = FileReviewScanner.__new__(FileReviewScanner)
    scanner.enabled = True
    scanner.model = "test"
    scanner.client = SimpleNamespace(generate=lambda _: SimpleNamespace(raw_text=json.dumps({
        "contains_business_sensitive": False, "risk_level": "low", "summary": "Public text",
        "confidence": 0.9, "categories": [],
    })))
    guard = SimpleNamespace(scan_text=lambda text, **kwargs: GuardrailScanResult(
        original_text=text, sanitized_text=text, has_sensitive_data=False, entities=[],
    ))
    monkeypatch.setattr("app.services.file_review_service.FileReviewScanner", lambda: scanner)
    monkeypatch.setattr("app.services.guardrails.llm_guard_service.get_guardrail_service", lambda: guard)
    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.file_review_service.SessionLocal", factory)
    service = FileReviewService(db_session)
    service.update_storage_settings(FileStorageSettingsUpdateRequest(default_storage_path=str(tmp_path)))
    original = pdf_bytes()
    file = service.create_uploaded_file(UploadedFilePayload(filename="public.pdf", content=original), username="alice")
    from app.workers.document_worker import run_one
    from app.models.review_job import ReviewJob
    from app.models.review_checkpoint import ReviewCheckpoint
    assert run_one(factory)
    db_session.expire_all()
    identity = db_session.get(AttachmentIdentity, file.id)
    assert identity.decision == "allow"
    assert identity.reviewed_sha256 == sha256(original)
    assert AttachmentAccessService(db_session).read_approved(file.id, "alice").content == original
    assert db_session.get(UploadedFile, file.id).status == "completed"
    assert db_session.get(ReviewJob, file.id).state == "completed"
    assert db_session.query(ReviewCheckpoint).filter_by(file_id=file.id, state="completed").count() >= 2


def test_mixed_pdf_is_not_certified_by_native_text_alone(tmp_path):
    import fitz
    path = tmp_path / "mixed.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), "Public heading")
        page.draw_rect((40, 60, 100, 100))
        document.save(path)
    ocr = SimpleNamespace(image_to_text=Mock(return_value="More text"))
    extracted = FileExtractionService(ocr).extract(path)
    assert len(extracted.visual_units) == 1
    assert extracted.visual_units[0].location == "Page 1"
    ocr.image_to_text.assert_called_once()
    assert "Public heading" in extracted.plain_text and "More text" in extracted.plain_text
