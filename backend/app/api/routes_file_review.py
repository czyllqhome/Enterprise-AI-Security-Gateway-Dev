from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..core.auth import get_current_user, require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.file_review import (
    FileStorageSettingsResponse,
    FileStorageSettingsUpdateRequest,
    UploadedFileListResponse,
    UploadedFileResponse,
    FileReviewStatusResponse,
)
from ..services.file_review_service import (
    FileReviewService,
    FileReviewValidationError,
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
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadedFileListResponse:
    return FileReviewService(db).list_files(current_user=current_user, limit=limit, offset=offset)


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
def upload_file_for_review(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadedFileResponse:
    try:
        service = FileReviewService(db)
        return service.create_uploaded_file_from_stream(
            filename=file.filename or "upload",
            stream=file.file,
            content_type=file.content_type or "application/octet-stream",
            username=current_user.username,
        )
    except FileReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/files/{file_id}/status", response_model=FileReviewStatusResponse)
def file_status(file_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return FileReviewService(db).get_status(file_id, current_user=current_user)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/files/{file_id}/retry", response_model=UploadedFileResponse)
def retry_file(file_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return FileReviewService(db).retry_review(file_id, current_user=current_user)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileReviewValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_file(file_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    try:
        FileReviewService(db).revoke_file(file_id, current_user=current_user)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
