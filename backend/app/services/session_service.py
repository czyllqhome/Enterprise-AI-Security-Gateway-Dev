from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..core.config import get_settings
from ..models.chat_session import ChatSession
from .provider_credential_service import ProviderCredentialService


class SessionNotFoundError(Exception):
    pass


class SessionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.provider_service = ProviderCredentialService(db)

    def create_session(
        self,
        title: str | None = None,
        username: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> ChatSession:
        provider_name = (provider or "").strip().lower() or self.settings.default_provider
        provider_details = self.provider_service.get_provider(provider_name)
        normalized_username = (username or "").strip() or "Guest"
        normalized_title = (title or "").strip() or self._generate_default_title(normalized_username)
        session = ChatSession(
            title=normalized_title,
            created_by=normalized_username,
            provider=provider_name,
            model=(model or "").strip() or provider_details.default_model,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def list_sessions(self) -> list[ChatSession]:
        stmt = select(ChatSession).order_by(desc(ChatSession.updated_at), desc(ChatSession.id))
        return list(self.db.scalars(stmt).all())

    def get_session(self, session_id: int) -> ChatSession:
        session = self.db.scalar(select(ChatSession).where(ChatSession.id == session_id))
        if session is None:
            raise SessionNotFoundError(f"Session {session_id} was not found.")
        return session

    def get_session_detail(self, session_id: int) -> ChatSession:
        stmt = select(ChatSession).options(selectinload(ChatSession.messages)).where(ChatSession.id == session_id)
        session = self.db.scalar(stmt)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id} was not found.")
        return session

    def delete_session(self, session_id: int) -> None:
        session = self.get_session_detail(session_id)
        self.db.delete(session)
        self.db.commit()

    def update_session_settings(self, session_id: int, provider: str, model: str) -> ChatSession:
        session = self.get_session(session_id)
        provider_name = provider.strip().lower()
        provider_details = self.provider_service.get_provider(provider_name)
        allowed_models = provider_details.models or [provider_details.default_model]
        normalized_model = model.strip()
        if normalized_model not in allowed_models:
            normalized_model = provider_details.default_model

        session.provider = provider_name
        session.model = normalized_model
        self.db.commit()
        self.db.refresh(session)
        return session

    def _generate_default_title(self, username: str) -> str:
        normalized_username = username.strip() or "Guest"
        session_count = self.db.scalar(
            select(func.count(ChatSession.id)).where(ChatSession.created_by == normalized_username),
        ) or 0
        return f"{normalized_username} · Chat {int(session_count) + 1}"
