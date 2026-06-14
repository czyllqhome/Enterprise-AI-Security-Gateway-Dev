from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import get_current_user
from ..core.db import get_db
from ..models.user import User
from ..schemas.messages import AssistantReplyResponse, ChatConfirmRequest, ChatPreviewRequest, ChatPreviewResponse
from ..services.chat_service import ChatService, GuardrailViolationError
from ..services.llm.openai_client import LLMProviderError
from ..services.provider_credential_service import ProviderCredentialNotFoundError
from ..services.session_service import SessionNotFoundError


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/preview", response_model=ChatPreviewResponse)
def preview_message(
    payload: ChatPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatPreviewResponse:
    try:
        return ChatService(db).preview_message(payload, username=current_user.username)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/confirm", response_model=AssistantReplyResponse, status_code=status.HTTP_201_CREATED)
def confirm_message(
    payload: ChatConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantReplyResponse:
    try:
        return ChatService(db).confirm_message(payload, username=current_user.username)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GuardrailViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (LLMProviderError, ProviderCredentialNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
