from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import get_current_user
from ..core.db import get_db
from ..models.user import User
from ..schemas.sessions import SessionCreateRequest, SessionDetail, SessionSettingsUpdateRequest, SessionSummary
from ..services.provider_credential_service import UnsupportedProviderError
from ..services.session_service import SessionNotFoundError, SessionService


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionSummary:
    try:
        return SessionService(db).create_session(
            title=payload.title,
            username=current_user.username,
            provider=payload.provider,
            model=payload.model,
        )
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    return SessionService(db).list_sessions(username=current_user.username)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    try:
        return SessionService(db).get_session_detail(session_id, username=current_user.username)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        SessionService(db).delete_session(session_id, username=current_user.username)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{session_id}/settings", response_model=SessionSummary)
def update_session_settings(
    session_id: int,
    payload: SessionSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionSummary:
    try:
        return SessionService(db).update_session_settings(
            session_id=session_id,
            provider=payload.provider,
            model=payload.model,
            username=current_user.username,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
