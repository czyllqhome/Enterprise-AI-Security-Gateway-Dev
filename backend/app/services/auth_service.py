from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import create_access_token, hash_password, verify_password
from ..models.user import User
from ..schemas.auth import TokenResponse
from .user_service import UserService


class AuthenticationError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_service = UserService(db)

    def login(self, username: str, password: str) -> TokenResponse:
        user = self.user_service.get_by_username(username.strip())
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password.")

        self.user_service.mark_login(user)
        return TokenResponse(
            access_token=create_access_token(
                user.username,
                claims={"role": user.role, "uid": user.id},
            ),
        )


def ensure_default_admin(db: Session) -> None:
    settings = get_settings()
    if not settings.default_admin_password:
        return

    service = UserService(db)
    username = settings.default_admin_username.strip()
    if service.get_by_username(username) is not None:
        return

    admin = User(
        username=username,
        password_hash=hash_password(settings.default_admin_password),
        display_name=settings.default_admin_display_name.strip() or username,
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
