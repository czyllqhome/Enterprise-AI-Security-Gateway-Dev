from sqlalchemy.orm import Session

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from urllib.parse import unquote

from ..core.auth import get_current_user, require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.file_review import (
    FileStorageSettingsResponse,
    FileStorageSettingsUpdateRequest,
    UploadedFileListResponse,
    UploadedFileResponse,
)
from ..services.file_review_service import (
    FileReviewService,
    FileReviewValidationError,
    UploadedFilePayload,
    UploadedFileNotFoundError,
)


router = APIRouter(prefix="/api/file-review", tags=["file-review"])


@router.get("/settings", response_model=FileStorageSettingsResponse)
def get_file_review_settings(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileStorageSettingsResponse:
    return FileReviewService(db).get_storage_settings()


@router.put("/settings", response_model=FileStorageSettingsResponse)
def update_file_review_settings(
    payload: FileStorageSettingsUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileStorageSettingsResponse:
    try:
        return FileReviewService(db).update_storage_settings(payload)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/files", response_model=UploadedFileListResponse)
def list_uploaded_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadedFileListResponse:
    return FileReviewService(db).list_files(current_user=current_user)


@router.get("/files/{file_id}", response_model=UploadedFileResponse)
def get_uploaded_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadedFileResponse:
    try:
        return FileReviewService(db).get_file(file_id, current_user=current_user)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/files/upload", response_model=UploadedFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file_for_review(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadedFileResponse:
    try:
        form = await _parse_multipart_request(request)
        file = form.get("file")
        if not isinstance(file, UploadedFilePayload):
            raise FileReviewValidationError("No file was provided.")
        service = FileReviewService(db)
        created = service.create_uploaded_file(file, username=current_user.username)
        background_tasks.add_task(service.process_uploaded_file, created.id)
        return created
    except FileReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _parse_multipart_request(request: Request) -> dict[str, str | UploadedFilePayload]:
    content_type = request.headers.get("content-type", "")
    boundary = _extract_boundary(content_type)
    if not boundary:
        raise FileReviewValidationError("Expected multipart/form-data upload.")

    body = await request.body()
    delimiter = f"--{boundary}".encode("utf-8")
    result: dict[str, str | UploadedFilePayload] = {}

    for part in body.split(delimiter):
        chunk = part.strip()
        if not chunk or chunk == b"--":
            continue
        if b"\r\n\r\n" not in chunk:
            continue
        header_block, content = chunk.split(b"\r\n\r\n", 1)
        content = content.rstrip(b"\r\n")
        headers = _parse_part_headers(header_block.decode("utf-8", errors="ignore"))
        disposition = headers.get("content-disposition", "")
        name = _extract_disposition_value(disposition, "name")
        filename = _extract_disposition_value(disposition, "filename")
        if not name:
            continue
        if filename is not None:
            result[name] = UploadedFilePayload(
                filename=filename,
                content=content,
                content_type=headers.get("content-type", "application/octet-stream"),
            )
        else:
            result[name] = content.decode("utf-8", errors="ignore")

    return result


def _extract_boundary(content_type: str) -> str | None:
    for item in content_type.split(";"):
        item = item.strip()
        if item.startswith("boundary="):
            return item.split("=", 1)[1].strip('"')
    return None


def _parse_part_headers(header_block: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_block.split("\r\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _extract_disposition_value(disposition: str, key: str) -> str | None:
    encoded_value: str | None = None
    for item in disposition.split(";"):
        item = item.strip()
        encoded_prefix = f"{key}*="
        if item.startswith(encoded_prefix):
            encoded_value = item.split("=", 1)[1].strip()
            continue
        prefix = f"{key}="
        if item.startswith(prefix):
            return item.split("=", 1)[1].strip('"')
    if encoded_value is None:
        return None
    candidate = encoded_value.strip('"')
    if "''" in candidate:
        _, candidate = candidate.split("''", 1)
    return unquote(candidate)
