from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FileStorageSettingsResponse(BaseModel):
    default_storage_path: str
    active_storage_profile: Literal["windows", "linux"]
    windows_storage_path: str
    linux_storage_path: str
    per_user_subdirectories: bool
    max_upload_mb: int


class FileStorageSettingsUpdateRequest(BaseModel):
    default_storage_path: str | None = Field(default=None, min_length=1, max_length=1024)
    active_storage_profile: Literal["windows", "linux"] | None = None
    windows_storage_path: str | None = Field(default=None, min_length=1, max_length=1024)
    linux_storage_path: str | None = Field(default=None, min_length=1, max_length=1024)
    per_user_subdirectories: bool | None = None


class ExtractedSegment(BaseModel):
    location: str
    text: str
    page_number: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    source_kind: str = "text"


class FileReviewHit(BaseModel):
    category: str
    risk_level: str
    reason: str = ""
    matched_text: str = ""
    location: str = ""


class FileReviewResult(BaseModel):
    contains_business_sensitive: bool = False
    risk_level: str = "low"
    summary: str = ""
    confidence: float = 0.0
    categories: list[str] = Field(default_factory=list)
    hits: list[FileReviewHit] = Field(default_factory=list)
    model: str = ""
    evaluated_at: datetime | None = None


class UploadedFileResponse(BaseModel):
    id: int
    original_filename: str
    stored_filename: str
    file_type: str
    content_type: str
    extension: str
    size_bytes: int
    storage_path: str
    uploaded_by: str
    status: str
    extraction_summary: str | None
    extracted_text: str | None
    extracted_segments: list[ExtractedSegment]
    review_result: FileReviewResult | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class UploadedFileListResponse(BaseModel):
    files: list[UploadedFileResponse]
