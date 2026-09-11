from pathlib import Path
import json

from sqlalchemy import select

from ..models.attachment import AttachmentIdentity
from ..models.uploaded_file import UploadedFile
from ..models.user import User
from .attachment_integrity import review_policy_hash, sha256
from .llm.attachments import OriginalAttachment
from .system_setting_service import SystemSettingService


class AttachmentAccessError(ValueError):
    pass


class AttachmentAccessService:
    def __init__(self, db):
        self.db = db

    def read_approved(self, file_id: int, username: str, expected_hash: str | None = None) -> OriginalAttachment:
        return self._read_with_decisions(file_id, username, {"allow"}, expected_hash)

    def read_reviewable(self, file_id: int, username: str, expected_hash: str | None = None) -> OriginalAttachment:
        return self._read_with_decisions(file_id, username, {"allow", "needs_confirmation"}, expected_hash)

    def read_confirmed(self, file_id: int, username: str, expected_hash: str) -> OriginalAttachment:
        # Only persisted MessageAttachment rows call this method, proving that the
        # reviewable original was explicitly confirmed in an earlier send.
        return self._read_with_decisions(file_id, username, {"allow", "needs_confirmation"}, expected_hash)

    def review_binding(self, file_id: int, username: str) -> dict:
        self.read_reviewable(file_id, username)
        identity = self.db.get(AttachmentIdentity, file_id)
        record = self.db.get(UploadedFile, file_id)
        if not record.review_result_json:
            raise AttachmentAccessError("Attachment review result is missing.")
        try:
            review = (record.review_result_json if isinstance(record.review_result_json, dict)
                      else json.loads(record.review_result_json))
        except (TypeError, json.JSONDecodeError) as exc:
            raise AttachmentAccessError("Attachment review result is invalid.") from exc
        review_hash = sha256(json.dumps(review, sort_keys=True, default=str).encode())
        return {
            "file_id": file_id,
            "sha256": identity.sha256,
            "review_decision": identity.decision,
            "review_result_hash": review_hash,
            "requires_confirmation": identity.decision == "needs_confirmation",
        }

    def _read_with_decisions(
        self, file_id: int, username: str, allowed_decisions: set[str], expected_hash: str | None,
    ) -> OriginalAttachment:
        user = self.db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
        identity = self.db.get(AttachmentIdentity, file_id)
        record = self.db.get(UploadedFile, file_id)
        if user is None or identity is None or record is None:
            raise AttachmentAccessError("Attachment needs a new review or is not accessible.")
        if identity.owner_user_id != user.id and user.role != "admin":
            raise AttachmentAccessError("Attachment is not accessible.")
        settings_service = SystemSettingService(self.db)
        policy = review_policy_hash(
            settings_service.get_enabled_scanners(), settings_service.get_business_sensitive_config(),
        )
        if (record.status != "completed" or identity.decision not in allowed_decisions
                or identity.reviewed_sha256 != identity.sha256 or identity.review_policy != policy):
            raise AttachmentAccessError("Attachment has not passed the current original-file review policy.")
        if expected_hash is not None and identity.sha256 != expected_hash:
            raise AttachmentAccessError("Attachment version changed; preview again.")
        try:
            # The same immutable bytes that pass the constructor hash check are transmitted.
            content = Path(record.storage_path).read_bytes()
            return OriginalAttachment(file_id, record.original_filename, identity.verified_mime, content, identity.sha256)
        except (OSError, ValueError) as exc:
            raise AttachmentAccessError("Original file is missing or differs from the reviewed file.") from exc
