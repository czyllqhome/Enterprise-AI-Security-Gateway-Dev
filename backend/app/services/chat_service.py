from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.chat_message import ChatMessage
from ..schemas.messages import AssistantReplyResponse, ChatConfirmRequest, ChatPreviewRequest, ChatPreviewResponse
from .guardrails.llm_guard_service import get_guardrail_service
from .llm.openai_client import LLMProviderError
from .llm.provider_factory import get_llm_client
from .log_service import LogService
from .scan_event_service import ScanEventService
from .session_service import SessionService
from .system_setting_service import SystemSettingService


class GuardrailViolationError(Exception):
    pass


class ChatService:
    SYSTEM_PLACEHOLDER_INSTRUCTION = (
        "You are assisting with a privacy-preserving chat. "
        "If the conversation contains placeholders like [REDACTED_EMAIL_ADDRESS_1], "
        "you must preserve them exactly when referring to those values. "
        "Do not translate, paraphrase, summarize, or replace those placeholders with labels like [hidden] or [MASKED]."
    )

    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionService(db)
        self.guardrail_service = get_guardrail_service()
        self.log_service = LogService(db)
        self.scan_event_service = ScanEventService(db)
        self.setting_service = SystemSettingService(db)

    def _should_block_scan(self, scan) -> bool:
        return bool(
            scan.bancode_triggered
            or scan.prompt_injection_triggered
            or scan.ban_topics_triggered
            or (
                scan.business_sensitive_result.contains_business_sensitive
                and scan.business_sensitive_result.risk_level == "high"
            )
        )

    def preview_message(self, payload: ChatPreviewRequest, username: str) -> ChatPreviewResponse:
        session = self.session_service.get_session(payload.session_id, username=username)
        enabled_scanners = self.setting_service.get_enabled_scanners()
        scan = self.guardrail_service.scan_text(payload.message, enabled_scanners=enabled_scanners)
        status = (
            "blocked"
            if self._should_block_scan(scan)
            else "needs_confirmation"
            if scan.has_sensitive_data
            or scan.business_sensitive_result.contains_business_sensitive
            else "clean"
        )
        event = self.scan_event_service.create_preview_event(
            session_id=session.id,
            username=username,
            provider=session.provider,
            model=session.model,
            status=status,
            blocked_reason=scan.blocked_reason,
            scan=scan,
        )
        if self._should_block_scan(scan):
            detected_types: list[str] = []
            if scan.bancode_triggered:
                detected_types.append("SOURCE_CODE_ATTEMPT")
            if scan.prompt_injection_triggered:
                detected_types.append("PROMPT_INJECTION_ATTEMPT")
            if scan.ban_topics_triggered:
                detected_types.extend(
                    [f"BAN_TOPIC:{topic}" for topic in (scan.banned_topics or ["restricted-topic"])],
                )
            if scan.business_sensitive_result.contains_business_sensitive:
                detected_types.extend(
                    [
                        f"BUSINESS_SENSITIVE:{category.name}"
                        for category in scan.business_sensitive_result.categories
                    ]
                    or ["BUSINESS_SENSITIVE"]
                )
            self.log_service.create_log(
                session_id=session.id,
                message_id=None,
                username=username,
                sanitized_content=scan.sanitized_text,
                detected_entity_types=detected_types,
            )
        self.db.commit()
        return ChatPreviewResponse(
            scan_event_id=event.id,
            session_id=session.id,
            status=status,
            blocked_reason=scan.blocked_reason,
            original_message=scan.original_text,
            sanitized_message=scan.sanitized_text,
            detected_entities=scan.entities,
            has_sensitive_data=scan.has_sensitive_data,
            llm_guard_hit_count=scan.llm_guard_hit_count,
            secrets_hit_count=scan.secrets_hit_count,
            privacy_filter_hit_count=scan.privacy_filter_hit_count,
            custom_regex_hit_count=scan.custom_regex_hit_count,
            scanners=scan.scanners,
            enabled_scanners=scan.enabled_scanners,
            entity_types=scan.entity_types,
            business_sensitive_result=scan.business_sensitive_result,
        )

    def confirm_message(self, payload: ChatConfirmRequest, username: str) -> AssistantReplyResponse:
        session = self.session_service.get_session(payload.session_id, username=username)
        enabled_scanners = (
            self.setting_service.validate_enabled_scanners(payload.enabled_scanners)
            if payload.enabled_scanners is not None
            else self.setting_service.get_enabled_scanners()
        )
        scan = self.guardrail_service.scan_text(payload.original_message, enabled_scanners=enabled_scanners)
        event = self.scan_event_service.get_event(payload.scan_event_id) if payload.scan_event_id else None

        if self._should_block_scan(scan):
            reason = scan.blocked_reason or "Guardrail blocked this prompt."
            if event is not None:
                event.status = "blocked"
                event.blocked_reason = reason
                self.db.commit()
            raise GuardrailViolationError(reason)

        if scan.has_sensitive_data and payload.sanitized_message != scan.sanitized_text:
            if event is not None:
                self.scan_event_service.mark_rejected(event, "Sanitized message mismatch.")
                self.db.commit()
            raise GuardrailViolationError("Sanitized message does not match the approved guardrail output.")
        if not scan.has_sensitive_data and payload.sanitized_message != payload.original_message:
            if event is not None:
                self.scan_event_service.mark_rejected(event, "Unexpected sanitized payload for clean message.")
                self.db.commit()
            raise GuardrailViolationError("Sanitized message must match the original message when no sensitive data is found.")

        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            original_content=scan.original_text,
            sanitized_content=scan.sanitized_text,
            used_content=scan.sanitized_text,
            has_sensitive_data=scan.has_sensitive_data,
            sensitive_entities_json=[entity.model_dump() for entity in scan.entities] or None,
        )
        self.db.add(user_message)
        self.db.flush()

        if scan.has_sensitive_data:
            self.log_service.create_log(
                session_id=session.id,
                message_id=user_message.id,
                username=username,
                sanitized_content=scan.sanitized_text,
                detected_entity_types=[entity.type for entity in scan.entities],
            )

        llm_messages = self._build_llm_messages(session.id)
        assistant_reply = get_llm_client(session.provider, db=self.db).chat(llm_messages, session.model)
        deanonymized_reply = self._deanonymize_assistant_reply(session.id, assistant_reply)

        if event is None:
            event = self.scan_event_service.create_preview_event(
                session_id=session.id,
                username=username,
                provider=session.provider,
                model=session.model,
                status="clean" if not scan.has_sensitive_data else "needs_confirmation",
                blocked_reason=None,
                scan=scan,
            )

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            original_content=assistant_reply,
            sanitized_content=deanonymized_reply,
            used_content=assistant_reply,
            has_sensitive_data=False,
            sensitive_entities_json=None,
        )
        self.db.add(assistant_message)
        self.scan_event_service.mark_confirmed(
            event,
            assistant_raw_output=assistant_reply,
            assistant_display_output=deanonymized_reply,
        )
        event.username = username
        session.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        self.db.refresh(session)

        return AssistantReplyResponse(
            session_id=session.id,
            session_title=session.title,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def _build_llm_messages(self, session_id: int) -> list[dict[str, str]]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
        messages = self.db.scalars(stmt).all()
        llm_messages = [
            {"role": "system", "content": self.SYSTEM_PLACEHOLDER_INSTRUCTION},
        ]
        llm_messages.extend(
            [
                {"role": message.role, "content": message.used_content or ""}
                for message in messages
                if message.used_content
            ]
        )
        return llm_messages

    def _deanonymize_assistant_reply(self, session_id: int, assistant_reply: str) -> str:
        session_entities = self._collect_session_entities(session_id)
        return self.guardrail_service.deanonymize_text(assistant_reply, session_entities)

    def _collect_session_entities(self, session_id: int) -> list[dict]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
        messages = self.db.scalars(stmt).all()
        entities: list[dict] = []
        seen_placeholders: set[str] = set()

        for message in messages:
            for entity in message.sensitive_entities_json or []:
                replacement = entity.get("replacement")
                if not replacement or replacement in seen_placeholders:
                    continue
                seen_placeholders.add(replacement)
                entities.append(entity)

        return entities
