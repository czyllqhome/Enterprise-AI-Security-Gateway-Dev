from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from sqlalchemy import and_, or_, select
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
    ALLOWED_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.setting_service = SystemSettingService(db)
        self.extraction_service = FileExtractionService()
        self.review_scanner = FileReviewScanner()

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
        stmt = stmt.offset(max(offset, 0)).limit(min(max(limit, 1), 500))
        records = self.db.scalars(stmt).all()
        return UploadedFileListResponse(files=[self._to_response(item) for item in records])

    def get_file(self, file_id: int, *, current_user: User) -> UploadedFileResponse:
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
        if record is None or not self._can_access_file(record, current_user):
            raise UploadedFileNotFoundError(f"Uploaded file {file_id} was not found.")
        return self._to_response(record)

    def create_uploaded_file(self, file: UploadedFilePayload, *, username: str | None = None) -> UploadedFileResponse:
        return self.create_uploaded_file_from_stream(
            filename=file.filename,
            stream=BytesIO(file.content),
            content_type=file.content_type,
            username=username,
        )

    def create_uploaded_file_from_stream(
        self,
        *,
        filename: str,
        stream: BinaryIO,
        content_type: str = "application/octet-stream",
        username: str | None = None,
    ) -> UploadedFileResponse:
        original_filename = filename or "upload"
        extension = Path(original_filename).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise FileReviewValidationError(f"Unsupported file type: {extension or 'unknown'}")

        max_bytes = self.settings.file_review_max_upload_mb * 1024 * 1024
        storage_root = self.setting_service.get_file_review_storage_path()
        storage = FileStorageService(storage_root)
        upload_username = (username or "").strip() or "Guest"
        target_path = storage.build_target_path(
            original_filename,
            username=upload_username,
            use_user_directory=self.setting_service.get_file_review_per_user_subdirectories(),
        )
        size_bytes = 0
        try:
            with target_path.open("wb") as target:
                while chunk := stream.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise FileReviewValidationError(
                            f"File exceeds the {self.settings.file_review_max_upload_mb}MB limit."
                        )
                    target.write(chunk)
        except Exception:
            target_path.unlink(missing_ok=True)
            raise

        record = UploadedFile(
            original_filename=original_filename,
            stored_filename=target_path.name,
            file_type=self._detect_file_type(extension),
            content_type=content_type or "application/octet-stream",
            extension=extension,
            size_bytes=size_bytes,
            storage_path=str(target_path),
            uploaded_by=upload_username,
            status="queued",
            next_attempt_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_response(record)

    @classmethod
    def claim_next_job(cls, worker_id: str | None = None) -> tuple[int, str] | None:
        resolved_worker_id = worker_id or f"file-review-{uuid4().hex[:12]}"
        db = SessionLocal()
        try:
            settings = get_settings()
            now = datetime.now(UTC)
            eligible = or_(
                and_(
                    UploadedFile.status == "queued",
                    or_(UploadedFile.next_attempt_at.is_(None), UploadedFile.next_attempt_at <= now),
                ),
                and_(
                    UploadedFile.status == "processing",
                    UploadedFile.lease_expires_at.is_not(None),
                    UploadedFile.lease_expires_at <= now,
                ),
            )
            stmt = (
                select(UploadedFile)
                .where(eligible)
                .order_by(UploadedFile.next_attempt_at.asc().nullsfirst(), UploadedFile.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            record = db.scalar(stmt)
            if record is None:
                db.rollback()
                return None
            record.status = "processing"
            record.attempt_count = (record.attempt_count or 0) + 1
            record.lease_owner = resolved_worker_id
            record.lease_expires_at = now + timedelta(seconds=max(settings.file_review_job_lease_seconds, 60))
            record.processing_started_at = now
            record.error_message = None
            file_id = record.id
            db.commit()
            return file_id, resolved_worker_id
        finally:
            db.close()

    @classmethod
    def process_claimed_job(cls, file_id: int, worker_id: str) -> None:
        db = SessionLocal()
        try:
            record = db.scalar(
                select(UploadedFile).where(
                    UploadedFile.id == file_id,
                    UploadedFile.status == "processing",
                    UploadedFile.lease_owner == worker_id,
                )
            )
            if record is None:
                return

            extraction_service = FileExtractionService()
            review_scanner = FileReviewScanner()
            extracted = extraction_service.extract(record.storage_path)
            review = review_scanner.review(extracted)
            record.status = "completed"
            record.extraction_summary = extracted.summary
            record.extracted_text = extracted.plain_text
            record.extracted_segments_json = [segment.model_dump() for segment in extracted.segments]
            record.review_result_json = review.model_dump(mode="json")
            record.error_message = None
            record.completed_at = datetime.now(UTC)
            record.lease_owner = None
            record.lease_expires_at = None
            db.commit()
        except Exception as exc:
            db.rollback()
            record = db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
            if record is not None and record.lease_owner == worker_id:
                settings = get_settings()
                record.error_message = str(exc)[:4000]
                record.lease_owner = None
                record.lease_expires_at = None
                if isinstance(exc, UnsupportedFileTypeError) or record.attempt_count >= settings.file_review_job_max_attempts:
                    record.status = "failed"
                    record.completed_at = datetime.now(UTC)
                else:
                    delay_seconds = min(60 * (2 ** max(record.attempt_count - 1, 0)), 600)
                    record.status = "queued"
                    record.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
                db.commit()
        finally:
            db.close()

    def _to_response(self, record: UploadedFile) -> UploadedFileResponse:
        segments = [
            ExtractedSegment.model_validate(item)
            for item in self._normalize_extracted_segments(record.extracted_segments_json)
        ]
        review_payload = self._load_json_payload(record.review_result_json)
        review = FileReviewResult.model_validate(review_payload) if review_payload else None
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
        return self._is_admin(current_user) or record.uploaded_by == current_user.username

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
