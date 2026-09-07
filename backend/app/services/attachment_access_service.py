from pathlib import Path

from sqlalchemy import select

from ..models.attachment import AttachmentIdentity
from ..models.uploaded_file import UploadedFile
from ..models.user import User
from .attachment_integrity import review_policy_hash
from .llm.attachments import OriginalAttachment
from .system_setting_service import SystemSettingService


class AttachmentAccessError(ValueError):
    pass


class AttachmentAccessService:
    def __init__(self, db):
        self.db = db

    def read_approved(self, file_id: int, username: str, expected_hash: str | None = None) -> OriginalAttachment:
        user = self.db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
        identity = self.db.get(AttachmentIdentity, file_id)
        record = self.db.get(UploadedFile, file_id)
        if user is None or identity is None or record is None:
            raise AttachmentAccessError("Attachment needs a new review or is not accessible.")
        if identity.owner_user_id != user.id and user.role != "admin":
            raise AttachmentAccessError("Attachment is not accessible.")
        policy = review_policy_hash(SystemSettingService(self.db).get_enabled_scanners())
        if (record.status != "completed" or identity.decision != "allow"
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
