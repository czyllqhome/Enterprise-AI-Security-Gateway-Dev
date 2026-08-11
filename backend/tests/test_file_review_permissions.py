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
            content=b"%PDF-1.4 demo",
            content_type="application/pdf",
        ),
        username="alice",
    )

    stored_path = Path(created.storage_path)
    assert stored_path.parent == tmp_path.resolve() / "alice"
    assert stored_path.exists()


def test_chat_attachment_context_uses_extracted_file_text(db_session):
    create_user(db_session, "alice")
    record = create_completed_uploaded_file(
        db_session,
        uploaded_by="alice",
        filename="purchase-order.png",
        text="Purchase order total is 880000 CNY for semiconductor equipment.",
    )
    service = ChatService.__new__(ChatService)
    service.db = db_session

    message = service._build_message_with_attachment_context(
        "总结这个文件",
        attachment_file_id=record.id,
        username="alice",
    )

    assert "[Attachment: purchase-order.png]" in message
    assert "Purchase order total is 880000 CNY" in message


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
        service._build_message_with_attachment_context(
            "总结这个文件",
            attachment_file_id=record.id,
            username="alice",
        )


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
