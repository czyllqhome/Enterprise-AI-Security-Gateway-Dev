from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.schemas.file_review import FileStorageSettingsUpdateRequest
from app.services.chat_service import ChatService, GuardrailViolationError
from app.services.file_review_service import FileReviewService, UploadedFilePayload


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autoflush=False, autocommit=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def create_user(db_session, username: str, *, role: str = "user") -> User:
    user = User(
        username=username,
        password_hash=hash_password("password"),
        display_name=username.title(),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_uploaded_file(db_session, *, uploaded_by: str, filename: str) -> UploadedFile:
    record = UploadedFile(
        original_filename=filename,
        stored_filename=f"stored-{filename}",
        file_type="pdf",
        content_type="application/pdf",
        extension=".pdf",
        size_bytes=123,
        storage_path=f"/tmp/{filename}",
        uploaded_by=uploaded_by,
        status="completed",
        extraction_summary="1 extracted page",
        extracted_text="reviewed text",
        extracted_segments_json=[],
        review_result_json=None,
        error_message=None,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def create_completed_uploaded_file(
    db_session,
    *,
    uploaded_by: str,
    filename: str,
    text: str,
    review_result: dict | None = None,
) -> UploadedFile:
    record = create_uploaded_file(db_session, uploaded_by=uploaded_by, filename=filename)
    record.extracted_text = text
    record.extracted_segments_json = [{"location": "Image", "text": text, "source_kind": "image_ocr"}]
    record.review_result_json = review_result or {
        "review_decision": "allow",
        "contains_business_sensitive": False,
        "risk_level": "low",
        "summary": "Attachment is allowed.",
    }
    db_session.commit()
    db_session.refresh(record)
    return record


def auth_headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(username)}"}


def test_file_review_settings_require_admin(client, db_session, tmp_path: Path):
    create_user(db_session, "alice")
    create_user(db_session, "admin", role="admin")

    response = client.get("/api/file-review/settings")
    assert response.status_code == 401

    response = client.put(
        "/api/file-review/settings",
        json={"default_storage_path": str(tmp_path / "anonymous")},
    )
    assert response.status_code == 401

    response = client.get("/api/file-review/settings", headers=auth_headers("alice"))
    assert response.status_code == 403

    response = client.put(
        "/api/file-review/settings",
        headers=auth_headers("alice"),
        json={"default_storage_path": str(tmp_path / "user")},
    )
    assert response.status_code == 403

    response = client.get("/api/file-review/settings", headers=auth_headers("admin"))
    assert response.status_code == 200

    admin_storage_path = tmp_path / "admin"
    response = client.put(
        "/api/file-review/settings",
        headers=auth_headers("admin"),
        json={"default_storage_path": str(admin_storage_path)},
    )
    assert response.status_code == 200
    payload = response.json()
    active_path_key = f"{payload['active_storage_profile']}_storage_path"
    assert payload["default_storage_path"] == str(admin_storage_path.resolve())
    assert payload[active_path_key] == str(admin_storage_path.resolve())
    assert payload["per_user_subdirectories"] is True


def test_uploaded_file_is_stored_under_username_directory(client, db_session, tmp_path: Path):
    create_user(db_session, "alice")
    service = FileReviewService(db_session)
    service.update_storage_settings(
        FileStorageSettingsUpdateRequest(default_storage_path=str(tmp_path))
    )

    created = service.create_uploaded_file(
        UploadedFilePayload(
            filename="Quarter Plan.pdf",
            content=pdf_bytes(),
            content_type="application/pdf",
        ),
        username="alice",
    )

    stored_path = Path(created.storage_path)
    assert stored_path.parent == tmp_path.resolve() / "alice"
    assert stored_path.exists()
    assert created.status == "queued"


def test_legacy_attachment_cannot_be_forwarded_without_identity(db_session):
    create_user(db_session, "alice")
    record = create_completed_uploaded_file(
        db_session,
        uploaded_by="alice",
        filename="purchase-order.png",
        text="Purchase order total is 880000 CNY for semiconductor equipment.",
    )
    service = ChatService.__new__(ChatService)
    service.db = db_session

    with pytest.raises(GuardrailViolationError):
        service._read_attachments(record.id, username="alice")


def test_chat_attachment_context_blocks_high_risk_file(db_session):
    create_user(db_session, "alice")
    record = create_completed_uploaded_file(
        db_session,
        uploaded_by="alice",
        filename="high-risk.png",
        text="confidential pricing",
        review_result={
            "contains_business_sensitive": True,
            "risk_level": "high",
            "summary": "High risk business data.",
        },
    )
    service = ChatService.__new__(ChatService)
    service.db = db_session

    with pytest.raises(GuardrailViolationError):
        service._read_attachments(record.id, username="alice")


def test_file_list_requires_auth_and_scopes_regular_users(client, db_session):
    create_user(db_session, "alice")
    create_user(db_session, "admin", role="admin")
    alice_file = create_uploaded_file(db_session, uploaded_by="alice", filename="alice.pdf")
    bob_file = create_uploaded_file(db_session, uploaded_by="bob", filename="bob.pdf")

    response = client.get("/api/file-review/files")
    assert response.status_code == 401

    response = client.get("/api/file-review/files", headers=auth_headers("alice"))
    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.json()["files"]}
    assert returned_ids == {alice_file.id}

    response = client.get("/api/file-review/files", headers=auth_headers("admin"))
    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.json()["files"]}
    assert returned_ids == {alice_file.id, bob_file.id}


def test_file_detail_requires_owner_or_admin(client, db_session):
    create_user(db_session, "alice")
    create_user(db_session, "admin", role="admin")
    alice_file = create_uploaded_file(db_session, uploaded_by="alice", filename="alice.pdf")
    bob_file = create_uploaded_file(db_session, uploaded_by="bob", filename="bob.pdf")

    response = client.get(f"/api/file-review/files/{alice_file.id}")
    assert response.status_code == 401

    response = client.get(f"/api/file-review/files/{alice_file.id}", headers=auth_headers("alice"))
    assert response.status_code == 200
    assert response.json()["id"] == alice_file.id

    response = client.get(f"/api/file-review/files/{bob_file.id}", headers=auth_headers("alice"))
    assert response.status_code == 404

    response = client.get(f"/api/file-review/files/{bob_file.id}", headers=auth_headers("admin"))
    assert response.status_code == 200
    assert response.json()["id"] == bob_file.id


def pdf_bytes():
    import fitz
    with fitz.open() as document:
        document.new_page().insert_text((40, 40), "Public document")
        return document.tobytes()


def test_status_and_retry_require_file_permission(client, db_session):
    from app.models.attachment import AttachmentIdentity
    from app.models.review_job import ReviewJob
    user = create_user(db_session, "alice")
    create_user(db_session, "bob")
    record = create_uploaded_file(db_session, uploaded_by="alice", filename="private.pdf")
    db_session.add(AttachmentIdentity(file_id=record.id, owner_user_id=user.id,
        sha256="a" * 64, verified_mime="application/pdf", decision="unknown"))
    db_session.commit()
    for method, suffix in [("GET", "status"), ("POST", "retry")]:
        url = f"/api/file-review/files/{record.id}/{suffix}"
        assert client.request(method, url).status_code == 401
        assert client.request(method, url, headers=auth_headers("bob")).status_code == 404
    status_response = client.get(f"/api/file-review/files/{record.id}/status", headers=auth_headers("alice"))
    assert status_response.status_code == 200
    assert "extracted_text" not in status_response.json()
    assert "storage_path" not in status_response.json()
    assert status_response.json()["completed_checkpoints"] == 0
    retry = client.post(f"/api/file-review/files/{record.id}/retry", headers=auth_headers("alice"))
    assert retry.status_code == 200
    assert retry.json()["status"] == "processing"
    assert db_session.get(ReviewJob, record.id).state == "queued"


def test_owner_can_revoke_original_file_and_stale_worker_lease(tmp_path, client, db_session):
    from datetime import datetime, timedelta, timezone
    from app.models.attachment import AttachmentIdentity
    from app.models.review_job import ReviewJob

    alice = create_user(db_session, "alice")
    create_user(db_session, "bob")
    path = tmp_path / "private.pdf"
    content = pdf_bytes()
    path.write_bytes(content)
    record = create_uploaded_file(db_session, uploaded_by="alice", filename="private.pdf")
    record.storage_path = str(path)
    db_session.add(AttachmentIdentity(
        file_id=record.id,
        owner_user_id=alice.id,
        sha256=hashlib.sha256(content).hexdigest(),
        verified_mime="application/pdf",
        reviewed_sha256=hashlib.sha256(content).hexdigest(),
        review_policy="old-policy",
        decision="allow",
    ))
    db_session.add(ReviewJob(
        file_id=record.id,
        state="running",
        phase="scanning",
        lease_token="stale-worker",
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
        next_attempt_at=datetime.now(timezone.utc),
        attempts=1,
    ))
    db_session.commit()

    assert client.delete(
        f"/api/file-review/files/{record.id}", headers=auth_headers("bob"),
    ).status_code == 404
    response = client.delete(
        f"/api/file-review/files/{record.id}", headers=auth_headers("alice"),
    )

    assert response.status_code == 204
    assert not path.exists()
    db_session.expire_all()
    assert db_session.get(UploadedFile, record.id).status == "deleted"
    assert db_session.get(AttachmentIdentity, record.id).decision == "unknown"
    job = db_session.get(ReviewJob, record.id)
    assert job.phase == "revoked"
    assert job.lease_token is None
    service = ChatService.__new__(ChatService)
    service.db = db_session
    with pytest.raises(GuardrailViolationError):
        service._read_attachments(record.id, username="alice")
