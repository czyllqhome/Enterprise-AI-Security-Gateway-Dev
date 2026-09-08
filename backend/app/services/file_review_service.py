from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models.uploaded_file import UploadedFile
from ..models.user import User
from ..schemas.file_review import (
    ExtractedSegment,
    FileReviewResult,
    FileStorageSettingsResponse,
    FileStorageSettingsUpdateRequest,
    UploadedFileListResponse,
    UploadedFileResponse,
)
from .file_extraction_service import FileExtractionService, UnsupportedFileTypeError
from .file_review_scanner import FileReviewScanner
from .file_storage_service import FileStorageService
from .system_setting_service import SystemSettingService
from .attachment_integrity import sha256, verify_mime, review_policy_hash
from ..models.attachment import AttachmentIdentity
from .original_file_review import review_original_document
from ..schemas.file_review_runtime import ExtractedSegmentPayload
from ..models.review_job import ReviewJob
from ..models.review_checkpoint import ReviewCheckpoint
from .review_job_service import require_lease, ReviewLeaseLost, utc
from .review_checkpoint_service import ReviewCheckpointStore
from datetime import datetime, timezone


class FileReviewValidationError(Exception):
    pass


class UploadedFileNotFoundError(Exception):
    pass


@dataclass(slots=True)
class UploadedFilePayload:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class FileReviewService:
    ALLOWED_EXTENSIONS = {".doc", ".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.setting_service = SystemSettingService(db)

    def get_storage_settings(self) -> FileStorageSettingsResponse:
        active_profile = self.setting_service.get_file_review_active_storage_profile()
        windows_path = self.setting_service.get_file_review_storage_path_for_profile("windows")
        linux_path = self.setting_service.get_file_review_storage_path_for_profile("linux")
        return FileStorageSettingsResponse(
            default_storage_path=self.setting_service.get_file_review_storage_path_for_profile(active_profile),
            active_storage_profile=active_profile,
            windows_storage_path=windows_path,
            linux_storage_path=linux_path,
            per_user_subdirectories=self.setting_service.get_file_review_per_user_subdirectories(),
            max_upload_mb=self.settings.file_review_max_upload_mb,
        )

    def update_storage_settings(self, payload: FileStorageSettingsUpdateRequest) -> FileStorageSettingsResponse:
        current = self.get_storage_settings()
        active_profile = payload.active_storage_profile or current.active_storage_profile
        windows_path = payload.windows_storage_path or current.windows_storage_path
        linux_path = payload.linux_storage_path or current.linux_storage_path
        per_user_subdirectories = (
            payload.per_user_subdirectories
            if payload.per_user_subdirectories is not None
            else current.per_user_subdirectories
        )

        if payload.default_storage_path:
            if active_profile == "windows":
                windows_path = payload.default_storage_path
            else:
                linux_path = payload.default_storage_path

        resolved_windows_path = self._normalize_storage_path("windows", windows_path)
        resolved_linux_path = self._normalize_storage_path("linux", linux_path)
        active_path = resolved_windows_path if active_profile == "windows" else resolved_linux_path
        if self._profile_matches_runtime(active_profile):
            Path(active_path).mkdir(parents=True, exist_ok=True)
        self.setting_service.set_file_review_storage_settings(
            active_storage_profile=active_profile,
            windows_storage_path=resolved_windows_path,
            linux_storage_path=resolved_linux_path,
            per_user_subdirectories=per_user_subdirectories,
        )
        return self.get_storage_settings()

    def list_files(self, *, current_user: User, limit: int = 100, offset: int = 0) -> UploadedFileListResponse:
        stmt = select(UploadedFile).order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())
        if not self._is_admin(current_user):
            stmt = stmt.where(UploadedFile.uploaded_by == current_user.username)
        stmt = stmt.offset(offset).limit(limit)
        records = self.db.scalars(stmt).all()
        return UploadedFileListResponse(files=[self._to_response(item) for item in records])

    def get_file(self, file_id: int, *, current_user: User) -> UploadedFileResponse:
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
        if record is None or not self._can_access_file(record, current_user):
            raise UploadedFileNotFoundError(f"Uploaded file {file_id} was not found.")
        return self._to_response(record)

    def create_uploaded_file(self, file: UploadedFilePayload, *, username: str | None = None) -> UploadedFileResponse:
        original_filename = file.filename or "upload"
        extension = Path(original_filename).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise FileReviewValidationError(f"Unsupported file type: {extension or 'unknown'}")

        content = file.content
        max_bytes = self.settings.file_review_max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise FileReviewValidationError(
                f"File exceeds the {self.settings.file_review_max_upload_mb}MB limit."
            )

        try:
            verified_mime = verify_mime(original_filename, content)
        except ValueError as exc:
            raise FileReviewValidationError(str(exc)) from exc
        owner = self.db.scalar(select(User).where(User.username == username))
        if owner is None:
            raise FileReviewValidationError("An authenticated file owner is required.")

        storage_root = self.setting_service.get_file_review_storage_path()
        storage = FileStorageService(storage_root)
        upload_username = (username or "").strip() or "Guest"
        target_path = storage.build_target_path(
            original_filename,
            username=upload_username,
            use_user_directory=self.setting_service.get_file_review_per_user_subdirectories(),
        )
        try:
            with target_path.open("xb") as handle:
                handle.write(content)

            record = UploadedFile(
                original_filename=original_filename,
                stored_filename=target_path.name,
                file_type=self._detect_file_type(extension),
                content_type=verified_mime,
                extension=extension,
                size_bytes=len(content),
                storage_path=str(target_path),
                uploaded_by=upload_username,
                status="queued",
            )
            self.db.add(record)
            self.db.flush()
            self.db.add(AttachmentIdentity(
                file_id=record.id, owner_user_id=owner.id, sha256=sha256(content),
                verified_mime=verified_mime, decision="unknown",
            ))
            self.db.add(ReviewJob(file_id=record.id, state="queued", phase="queued", attempts=0))
            self.db.commit()
        except Exception:
            self.db.rollback()
            target_path.unlink(missing_ok=True)
            raise
        self.db.refresh(record)
        return self._to_response(record)

    def create_uploaded_file_from_stream(
        self,
        *,
        filename: str,
        stream: BinaryIO,
        content_type: str = "application/octet-stream",
        username: str | None = None,
    ) -> UploadedFileResponse:
        max_bytes = self.settings.file_review_max_upload_mb * 1024 * 1024
        content = bytearray()
        while chunk := stream.read(1024 * 1024):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise FileReviewValidationError(
                    f"File exceeds the {self.settings.file_review_max_upload_mb}MB limit.",
                )
        return self.create_uploaded_file(
            UploadedFilePayload(filename=filename, content=bytes(content), content_type=content_type),
            username=username,
        )

    def revoke_file(self, file_id: int, *, current_user: User) -> None:
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id).with_for_update())
        if record is None or not self._can_access_file(record, current_user):
            raise UploadedFileNotFoundError("File was not found.")
        identity = self.db.get(AttachmentIdentity, file_id)
        job = self.db.get(ReviewJob, file_id)
        if identity is not None:
            identity.decision = "unknown"
            identity.reviewed_sha256 = None
            identity.review_policy = None
        if job is not None:
            job.state = "failed"
            job.phase = "revoked"
            job.lease_token = None
            job.lease_until = None
            job.last_error = "Attachment was revoked by its owner."
        record.status = "deleted"
        record.error_message = "Attachment was revoked by its owner."
        record.lease_owner = None
        record.lease_expires_at = None
        storage_path = Path(record.storage_path)
        # Commit the access revocation before attempting irreversible byte cleanup.
        self.db.commit()
        try:
            storage_path.unlink(missing_ok=True)
        except OSError:
            # The tombstone remains fail-closed; an operator can retry physical cleanup.
            return

    def process_uploaded_file(self, file_id: int, lease_token: str | None = None) -> None:
        db = SessionLocal()
        record = None
        identity = None
        try:
            if lease_token:
                job = require_lease(db, file_id, lease_token)
                job.phase = "extracting"
            record = db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
            if record is None:
                return
            identity = db.get(AttachmentIdentity, file_id)
            if identity is None:
                raise ValueError("Legacy attachment needs to be uploaded again for original-file review.")
            identity.decision = "unknown"
            original_bytes = Path(record.storage_path).read_bytes()
            if sha256(original_bytes) != identity.sha256:
                raise ValueError("Original file differs from the uploaded content.")
            enabled = SystemSettingService(db).get_enabled_scanners()
            policy = review_policy_hash(enabled)
            original_hash = identity.sha256
            suffix = record.extension
            db.commit()

            extraction_service = FileExtractionService()
            review_scanner = FileReviewScanner()
            # Review a private byte-identical snapshot so filesystem edits cannot change the scan input.
            with tempfile.TemporaryDirectory(prefix="gateway-review-") as directory:
                review_path = Path(directory) / ("original" + suffix)
                review_path.write_bytes(original_bytes)
                extracted = extraction_service.extract(review_path)
            extracted.segments.append(ExtractedSegmentPayload(location="Original filename", text=record.original_filename))
            from .guardrails.llm_guard_service import get_guardrail_service
            if lease_token:
                job = require_lease(db, file_id, lease_token)
                job.phase = "scanning"
                db.commit()
            checkpoints = ReviewCheckpointStore(SessionLocal, file_id, original_hash, policy, lease_token) if lease_token else None
            review = review_original_document(extracted, review_scanner, get_guardrail_service(), enabled, db,
                                              checkpoints=checkpoints)
            if lease_token:
                require_lease(db, file_id, lease_token)
            db.refresh(record)
            db.refresh(identity)
            if (sha256(Path(record.storage_path).read_bytes()) != original_hash
                    or identity.sha256 != original_hash
                    or review_policy_hash(SystemSettingService(db).get_enabled_scanners()) != policy):
                raise ValueError("Original file or review policy changed during review.")
            identity.reviewed_sha256 = original_hash
            identity.review_policy = policy
            identity.decision = review.review_decision
            record.status = "completed"
            record.extraction_summary = extracted.summary
            record.extracted_text = extracted.plain_text
            record.extracted_segments_json = [segment.model_dump() for segment in extracted.segments]
            record.review_result_json = review.model_dump(mode="json")
            record.error_message = None
        except ReviewLeaseLost:
            db.rollback()
        except UnsupportedFileTypeError as exc:
            if lease_token:
                try:
                    require_lease(db, file_id, lease_token)
                except ReviewLeaseLost:
                    db.rollback()
                    return
            if identity is not None:
                identity.decision = "unknown"
            if record is not None:
                record.status = "failed"
                record.error_message = str(exc)
        except Exception as exc:
            if lease_token:
                try:
                    require_lease(db, file_id, lease_token)
                except ReviewLeaseLost:
                    db.rollback()
                    return
            if identity is not None:
                identity.decision = "unknown"
            if record is not None:
                record.status = "failed"
                record.error_message = str(exc)
        finally:
            db.commit()
            db.close()

    def retry_review(self, file_id: int, *, current_user: User):
        job = self.db.scalar(select(ReviewJob).where(ReviewJob.file_id == file_id).with_for_update())
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id).with_for_update())
        if record is None or not self._can_access_file(record, current_user):
            raise UploadedFileNotFoundError("File was not found.")
        identity = self.db.get(AttachmentIdentity, file_id)
        if identity is None:
            raise FileReviewValidationError("Please upload this legacy file again.")
        now = datetime.now(timezone.utc)
        if job and (job.state == "queued" or (job.state == "running" and job.lease_until and utc(job.lease_until) > now)):
            self.db.rollback()
            return self.get_file(file_id, current_user=current_user)
        if job is None:
            job = ReviewJob(file_id=file_id)
            self.db.add(job)
        job.state, job.phase, job.attempts = "queued", "queued", 0
        job.lease_token, job.lease_until, job.last_error = None, None, None
        job.next_attempt_at = now
        record.status, record.error_message = "processing", None
        record.attempt_count = 0
        record.next_attempt_at = now
        record.lease_owner = None
        record.lease_expires_at = None
        identity.decision = "unknown"
        self.db.commit()
        return self.get_file(file_id, current_user=current_user)

    def get_status(self, file_id: int, *, current_user: User):
        record = self.db.get(UploadedFile, file_id)
        if record is None or not self._can_access_file(record, current_user):
            raise UploadedFileNotFoundError("File was not found.")
        job = self.db.get(ReviewJob, file_id)
        identity = self.db.get(AttachmentIdentity, file_id)
        review = self._load_json_payload(record.review_result_json) or {}
        checkpoint_counts = dict(self.db.execute(select(ReviewCheckpoint.state, func.count()).where(
            ReviewCheckpoint.file_id == file_id).group_by(ReviewCheckpoint.state)).all())
        return {"id": file_id, "status": record.status, "phase": job.phase if job else record.status,
                "review_decision": identity.decision if identity and identity.review_policy == review_policy_hash(
                    self.setting_service.get_enabled_scanners()) else "unknown",
                "total_chunks": review.get("total_chunks", 0), "reviewed_chunks": review.get("reviewed_chunks", 0),
                "total_visual_units": review.get("total_visual_units", 0),
                "reviewed_visual_units": review.get("reviewed_visual_units", 0),
                "completed_checkpoints": checkpoint_counts.get("completed", 0),
                "failed_checkpoints": checkpoint_counts.get("failed", 0),
                "attempts": job.attempts if job else 0, "error_message": record.error_message}

    def _to_response(self, record: UploadedFile) -> UploadedFileResponse:
        segments = [
            ExtractedSegment.model_validate(item)
            for item in self._normalize_extracted_segments(record.extracted_segments_json)
        ]
        review_payload = self._load_json_payload(record.review_result_json)
        review = FileReviewResult.model_validate(review_payload) if review_payload else None
        identity = self.db.get(AttachmentIdentity, record.id)
        if review is not None and review.review_decision != "block" and (
            identity is None or identity.decision != "allow" or identity.reviewed_sha256 != identity.sha256
            or identity.review_policy != review_policy_hash(self.setting_service.get_enabled_scanners())
        ):
            review.review_decision = "unknown"
            review.summary = "Original-file safety and privacy review is not complete. " + review.summary
        return UploadedFileResponse(
            id=record.id,
            original_filename=record.original_filename,
            stored_filename=record.stored_filename,
            file_type=record.file_type,
            content_type=record.content_type,
            extension=record.extension,
            size_bytes=record.size_bytes,
            storage_path=record.storage_path,
            uploaded_by=record.uploaded_by,
            status=record.status,
            attempt_count=record.attempt_count,
            next_attempt_at=record.next_attempt_at,
            processing_started_at=record.processing_started_at,
            completed_at=record.completed_at,
            extraction_summary=record.extraction_summary,
            extracted_text=record.extracted_text,
            extracted_segments=segments,
            review_result=review,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _detect_file_type(self, extension: str) -> str:
        if extension in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            return "image"
        if extension == ".pdf":
            return "pdf"
        if extension == ".docx":
            return "word"
        if extension == ".doc":
            return "word"
        if extension == ".xlsx":
            return "excel"
        if extension == ".pptx":
            return "powerpoint"
        return "file"

    def _normalize_storage_path(self, profile: str, path: str) -> str:
        cleaned = path.strip()
        if self._profile_matches_runtime(profile):
            return str(Path(cleaned).expanduser().resolve())
        return cleaned

    def _profile_matches_runtime(self, profile: str) -> bool:
        return (profile == "windows" and os.name == "nt") or (profile == "linux" and os.name != "nt")

    def _can_access_file(self, record: UploadedFile, current_user: User) -> bool:
        identity = self.db.get(AttachmentIdentity, record.id)
        return self._is_admin(current_user) or (
            identity.owner_user_id == current_user.id if identity else record.uploaded_by == current_user.username
        )

    def _is_admin(self, current_user: User) -> bool:
        return current_user.role == "admin"

    def _normalize_extracted_segments(self, payload: Any) -> list[dict]:
        raw_segments = self._load_json_payload(payload)
        if not isinstance(raw_segments, list):
            return []

        normalized: list[dict] = []
        for index, item in enumerate(raw_segments, start=1):
            if not isinstance(item, dict):
                continue
            segment = dict(item)
            if not segment.get("location"):
                if segment.get("page") is not None:
                    segment["location"] = f"Page {segment['page']}"
                    segment.setdefault("page_number", segment.get("page"))
                else:
                    segment["location"] = f"Segment {index}"
            segment.setdefault("text", "")
            normalized.append(segment)
        return normalized

    def _load_json_payload(self, payload: Any) -> Any:
        if not isinstance(payload, str):
            return payload
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
