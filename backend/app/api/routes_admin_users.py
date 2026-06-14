from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.auth import require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.users import PasswordResetRequest, UserCreateRequest, UserResponse, UserUpdateRequest
from ..services.user_service import (
    InvalidUserRoleError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserService,
)


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    return UserService(db).list_users()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    try:
        return UserService(db).create_user(payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidUserRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    try:
        return UserService(db).update_user(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidUserRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    try:
        return UserService(db).reset_password(user_id, payload.new_password)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own user.")
    try:
        UserService(db).delete_user(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
