from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models.uploaded_file import UploadedFile
from ..schemas.file_review import (
    ExtractedSegment,
    FileReviewResult,
    FileStorageSettingsResponse,
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
        return FileStorageSettingsResponse(
            default_storage_path=self.setting_service.get_file_review_storage_path(),
            max_upload_mb=self.settings.file_review_max_upload_mb,
        )

    def update_storage_settings(self, default_storage_path: str) -> FileStorageSettingsResponse:
        path = Path(default_storage_path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        self.setting_service.set_file_review_storage_path(str(path))
        return self.get_storage_settings()

    def list_files(self) -> UploadedFileListResponse:
        records = self.db.scalars(select(UploadedFile).order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())).all()
        return UploadedFileListResponse(files=[self._to_response(item) for item in records])

    def get_file(self, file_id: int) -> UploadedFileResponse:
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
        if record is None:
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

        storage_root = self.setting_service.get_file_review_storage_path()
        storage = FileStorageService(storage_root)
        target_path = storage.build_target_path(original_filename)
        target_path.write_bytes(content)

        record = UploadedFile(
            original_filename=original_filename,
            stored_filename=target_path.name,
            file_type=self._detect_file_type(extension),
            content_type=file.content_type or "application/octet-stream",
            extension=extension,
            size_bytes=len(content),
            storage_path=str(target_path),
            uploaded_by=(username or "").strip() or "Guest",
            status="processing",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_response(record)

    def process_uploaded_file(self, file_id: int) -> None:
        db = SessionLocal()
        record = None
        try:
            record = db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
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
        except UnsupportedFileTypeError as exc:
            if record is not None:
                record.status = "failed"
                record.error_message = str(exc)
        except Exception as exc:
            if record is not None:
                record.status = "failed"
                record.error_message = str(exc)
        finally:
            db.commit()
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
