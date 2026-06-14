from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import hash_password
from ..models.user import User
from ..schemas.users import UserCreateRequest, UserUpdateRequest


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class InvalidUserRoleError(Exception):
    pass


class UserService:
    VALID_ROLES = {"admin", "user"}

    def __init__(self, db: Session):
        self.db = db

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.username)).all())

    def get_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found.")
        return user

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username.strip()))

    def create_user(self, payload: UserCreateRequest) -> User:
        username = payload.username.strip()
        self._validate_role(payload.role)
        if self.get_by_username(username) is not None:
            raise UserAlreadyExistsError(f"User '{username}' already exists.")
        user = User(
            username=username,
            password_hash=hash_password(payload.password),
            display_name=(payload.display_name or username).strip(),
            role=payload.role,
            is_active=payload.is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: int, payload: UserUpdateRequest) -> User:
        user = self.get_user(user_id)
        if payload.role is not None:
            self._validate_role(payload.role)
            user.role = payload.role
        if payload.display_name is not None:
            user.display_name = payload.display_name.strip() or user.username
        if payload.is_active is not None:
            user.is_active = payload.is_active
        self.db.commit()
        self.db.refresh(user)
        return user

    def reset_password(self, user_id: int, new_password: str) -> User:
        user = self.get_user(user_id)
        user.password_hash = hash_password(new_password)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user_id: int) -> None:
        user = self.get_user(user_id)
        self.db.delete(user)
        self.db.commit()

    def mark_login(self, user: User) -> None:
        user.last_login_at = datetime.utcnow()
        self.db.commit()

    def _validate_role(self, role: str) -> None:
        if role not in self.VALID_ROLES:
            raise InvalidUserRoleError(f"Unsupported user role: {role}")
