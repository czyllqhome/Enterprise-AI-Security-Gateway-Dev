import io

import pytest

from app.services.attachment_integrity import verify_mime, sha256
from app.models.attachment import AttachmentIdentity
from app.services.attachment_access_service import AttachmentAccessService, AttachmentAccessError
from test_file_review_permissions import db_session, create_user, create_completed_uploaded_file, pdf_bytes


def test_pdf_type_is_verified_without_changing_bytes():
    content = pdf_bytes()
    original_hash = sha256(content)
    assert verify_mime("file.pdf", content) == "application/pdf"
    assert sha256(content) == original_hash


@pytest.mark.parametrize("filename,content", [
    ("file.pdf", b"%PDF-1.4 invalid"), ("file.docx", b"not zip"),
    ("file.png", b"not an image"), ("file.exe", b"MZ"),
])
def test_invalid_or_mismatched_content_is_rejected(filename, content):
    with pytest.raises(ValueError):
        verify_mime(filename, content)


def test_image_mime_cannot_be_disguised():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="PNG")
    assert verify_mime("file.png", buffer.getvalue()) == "image/png"
    with pytest.raises(ValueError):
        verify_mime("file.jpg", buffer.getvalue())


def test_legacy_word_magic_is_verified_without_conversion():
    content = bytes.fromhex("D0CF11E0A1B11AE1") + b"original legacy content"
    assert verify_mime("file.doc", content) == "application/msword"
    with pytest.raises(ValueError):
        verify_mime("file.doc", b"not an OLE document")


def test_identity_owner_is_authoritative(db_session):
    alice = create_user(db_session, "alice")
    bob = create_user(db_session, "bob")
    file = create_completed_uploaded_file(db_session, uploaded_by="alice", filename="file.pdf", text="text")
    db_session.add(AttachmentIdentity(file_id=file.id, owner_user_id=bob.id,
        sha256=sha256(b"file"), verified_mime="application/pdf", decision="unknown"))
    db_session.commit()
    with pytest.raises(AttachmentAccessError, match="not accessible"):
        AttachmentAccessService(db_session).read_approved(file.id, alice.username)
