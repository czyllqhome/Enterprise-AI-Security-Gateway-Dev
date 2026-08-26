from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.chat_message import ChatMessage
from ..models.uploaded_file import UploadedFile
from ..models.user import User
from ..core.config import get_settings
from ..core.scan_proof import (
    ScanProofError,
    canonical_json_digest,
    create_scan_proof,
    decode_scan_proof,
)
from ..schemas.guardrail import GuardrailEntity
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


class ScanConfirmationError(GuardrailViolationError):
    pass


class ChatService:
    MAX_ATTACHMENT_TEXT_CHARS = 12000
    SYSTEM_PLACEHOLDER_INSTRUCTION = (
        "You are assisting with a privacy-preserving chat. "
        "If the conversation contains placeholders like [REDACTED_EMAIL_ADDRESS_1], "
        "you must preserve them exactly when referring to those values. "
        "Do not translate, paraphrase, summarize, or replace those placeholders with labels like [hidden] or [MASKED]."
    )

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
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
        session_id = session.id
        session_provider = session.provider
        session_model = session.model
        enabled_scanners = self.setting_service.get_enabled_scanners()
        strict_mode = self.setting_service.get_scanner_strict_mode()
        message = self._build_message_with_attachment_context(
            payload.message,
            attachment_file_id=payload.attachment_file_id,
            username=username,
        )
        business_runtime = None
        business_runtime_unavailable = False
        if "business_sensitive" in enabled_scanners:
            try:
                business_runtime = self.guardrail_service.resolve_business_sensitive_runtime(self.db)
            except Exception:
                business_runtime_unavailable = True
        scanner_config_hash = self.guardrail_service.get_config_fingerprint(
            enabled_scanners,
            business_runtime=business_runtime,
            business_runtime_unavailable=business_runtime_unavailable,
            strict_mode=strict_mode,
        )
        # Release the PostgreSQL connection while CPU/GPU/network scanners run.
        self.db.commit()
        scan = self.guardrail_service.scan_text(
            message,
            enabled_scanners=enabled_scanners,
            business_runtime=business_runtime,
            business_runtime_unavailable=business_runtime_unavailable,
            strict_mode=strict_mode,
        )
        status = (
            "blocked"
            if self._should_block_scan(scan)
            else "needs_confirmation"
            if scan.has_sensitive_data
            or scan.business_sensitive_result.contains_business_sensitive
            else "clean"
        )
        event = self.scan_event_service.create_preview_event(
            session_id=session_id,
            username=username,
            provider=session_provider,
            model=session_model,
            status=status,
            blocked_reason=scan.blocked_reason,
            scan=scan,
        )
        input_digest = self._scan_payload_digest(
            original_message=scan.original_text,
            sanitized_message=scan.sanitized_text,
            detected_entities=scan.entities,
            attachment_file_id=payload.attachment_file_id,
            enabled_scanners=scan.enabled_scanners,
        )
        event.input_digest = input_digest
        event.scanner_config_hash = scanner_config_hash
        scan_proof, proof_expires_at = create_scan_proof(
            event_id=event.id,
            session_id=session_id,
            username=username,
            payload_digest=input_digest,
            scanner_config_hash=scanner_config_hash,
            attachment_file_id=payload.attachment_file_id,
        )
        event.proof_expires_at = datetime.fromtimestamp(proof_expires_at, UTC)
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
                session_id=session_id,
                message_id=None,
                username=username,
                sanitized_content=scan.sanitized_text,
                detected_entity_types=detected_types,
            )
        self.db.commit()
        return ChatPreviewResponse(
            scan_event_id=event.id,
            session_id=session_id,
            attachment_file_id=payload.attachment_file_id,
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
            scan_proof=scan_proof if status != "blocked" else None,
            proof_expires_at=event.proof_expires_at if status != "blocked" else None,
            degraded_scanners=scan.degraded_scanners,
            scan_duration_ms=scan.scan_duration_ms,
        )

    def confirm_message(self, payload: ChatConfirmRequest, username: str) -> AssistantReplyResponse:
        prepared = self._prepare_confirmation(payload, username=username)
        try:
            assistant_reply = prepared["llm_client"].chat(
                prepared["llm_messages"],
                prepared["session_model"],
            )
        except Exception as exc:
            self._mark_confirmation_failed(prepared["event_id"], exc)
            raise
        return self._complete_confirmation(prepared, assistant_reply=assistant_reply, username=username)

    def confirm_message_stream(self, payload: ChatConfirmRequest, username: str):
        prepared = self._prepare_confirmation(payload, username=username)

        def generate():
            yield {"event": "accepted", "scan_event_id": prepared["event_id"]}
            chunks: list[str] = []
            try:
                for delta in prepared["llm_client"].stream_chat(
                    prepared["llm_messages"],
                    prepared["session_model"],
                ):
                    if not delta:
                        continue
                    chunks.append(delta)
                    yield {"event": "delta", "text": delta}
                assistant_reply = "".join(chunks).strip()
                if not assistant_reply:
                    raise LLMProviderError("Model stream did not contain text output.")
                response = self._complete_confirmation(
                    prepared,
                    assistant_reply=assistant_reply,
                    username=username,
                )
                yield {"event": "completed", "response": response.model_dump(mode="json")}
            except GeneratorExit:
                self._mark_confirmation_failed(prepared["event_id"], RuntimeError("Client cancelled stream."))
                raise
            except Exception as exc:
                self._mark_confirmation_failed(prepared["event_id"], exc)
                yield {"event": "error", "detail": str(exc), "retryable": True}

        return generate()

    def _prepare_confirmation(self, payload: ChatConfirmRequest, *, username: str) -> dict[str, Any]:
        session = self.session_service.get_session(payload.session_id, username=username)
        session_id = session.id
        session_title = session.title
        session_provider = session.provider
        session_model = session.model
        enabled_scanners = self.setting_service.get_enabled_scanners()
        strict_mode = self.setting_service.get_scanner_strict_mode()
        original_message = self._build_message_with_attachment_context(
            payload.original_message,
            attachment_file_id=payload.attachment_file_id,
            username=username,
        )
        event = self._validate_confirmation(
            payload,
            username=username,
            original_message=original_message,
            enabled_scanners=enabled_scanners,
            strict_mode=strict_mode,
        )
        detected_entities = payload.detected_entities
        has_sensitive_data = event.has_sensitive_data
        sanitized_message = event.sanitized_input

        llm_messages, session_entities = self._build_llm_context(session_id)
        llm_messages.append({"role": "user", "content": sanitized_message})
        session_entities.extend(entity.model_dump() for entity in detected_entities)
        llm_client = get_llm_client(session_provider, db=self.db)

        self.scan_event_service.claim_for_confirmation(event)
        self.db.commit()
        return {
            "event_id": event.id,
            "session_id": session_id,
            "session_title": session_title,
            "session_model": session_model,
            "original_message": original_message,
            "sanitized_message": sanitized_message,
            "detected_entities": detected_entities,
            "has_sensitive_data": has_sensitive_data,
            "llm_messages": llm_messages,
            "session_entities": session_entities,
            "llm_client": llm_client,
        }

    def _mark_confirmation_failed(self, event_id: int, exc: Exception) -> None:
        failed_event = self.scan_event_service.get_event(event_id)
        if failed_event is not None:
            self.scan_event_service.mark_send_failed(failed_event, str(exc))
            self.db.commit()

    def _complete_confirmation(
        self,
        prepared: dict[str, Any],
        *,
        assistant_reply: str,
        username: str,
    ) -> AssistantReplyResponse:
        session_id = prepared["session_id"]
        original_message = prepared["original_message"]
        sanitized_message = prepared["sanitized_message"]
        detected_entities = prepared["detected_entities"]
        has_sensitive_data = prepared["has_sensitive_data"]
        deanonymized_reply = self.guardrail_service.deanonymize_text(
            assistant_reply,
            prepared["session_entities"],
        )

        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            original_content=original_message,
            sanitized_content=sanitized_message,
            used_content=sanitized_message,
            has_sensitive_data=has_sensitive_data,
            sensitive_entities_json=[entity.model_dump() for entity in detected_entities] or None,
        )
        self.db.add(user_message)
        self.db.flush()

        if has_sensitive_data:
            self.log_service.create_log(
                session_id=session_id,
                message_id=user_message.id,
                username=username,
                sanitized_content=sanitized_message,
                detected_entity_types=[entity.type for entity in detected_entities],
            )

        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            original_content=assistant_reply,
            sanitized_content=deanonymized_reply,
            used_content=assistant_reply,
            has_sensitive_data=False,
            sensitive_entities_json=None,
        )
        self.db.add(assistant_message)
        event = self.scan_event_service.get_event(prepared["event_id"])
        if event is None:
            raise ScanConfirmationError("Scan event disappeared before confirmation completed.")
        self.scan_event_service.mark_confirmed(
            event,
            assistant_raw_output=assistant_reply,
            assistant_display_output=deanonymized_reply,
        )
        event.username = username
        session = self.session_service.get_session(session_id, username=username)
        session.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        self.db.refresh(session)

        return AssistantReplyResponse(
            session_id=session_id,
            session_title=prepared["session_title"],
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def _validate_confirmation(
        self,
        payload: ChatConfirmRequest,
        *,
        username: str,
        original_message: str,
        enabled_scanners: list[str],
        strict_mode: bool,
    ):
        if payload.scan_event_id is None or not payload.scan_proof:
            raise ScanConfirmationError("A valid scan proof is required. Please scan the message again.")
        event = self.scan_event_service.get_event_for_confirmation(
            payload.scan_event_id,
            session_id=payload.session_id,
            username=username,
            lock=True,
        )
        if event is None:
            raise ScanConfirmationError("Scan event was not found for this user and session.")
        if event.status not in {"clean", "needs_confirmation"} or event.consumed_at is not None:
            raise ScanConfirmationError("Scan event has already been consumed or cannot be confirmed.")

        scanner_config_hash = self.guardrail_service.get_config_fingerprint(
            enabled_scanners,
            db=self.db,
            strict_mode=strict_mode,
        )
        input_digest = self._scan_payload_digest(
            original_message=original_message,
            sanitized_message=payload.sanitized_message,
            detected_entities=payload.detected_entities,
            attachment_file_id=payload.attachment_file_id,
            enabled_scanners=enabled_scanners,
        )
        try:
            claims = decode_scan_proof(payload.scan_proof)
        except ScanProofError as exc:
            raise ScanConfirmationError(str(exc)) from exc

        expected_claims = {
            "event_id": payload.scan_event_id,
            "session_id": payload.session_id,
            "username": username,
            "payload_digest": input_digest,
            "scanner_config_hash": scanner_config_hash,
            "attachment_file_id": payload.attachment_file_id,
        }
        if any(claims.get(key) != value for key, value in expected_claims.items()):
            raise ScanConfirmationError("Scan proof does not match the approved message. Please scan again.")
        if event.input_digest != input_digest or event.scanner_config_hash != scanner_config_hash:
            raise ScanConfirmationError("Scanner configuration or message content changed. Please scan again.")
        if payload.sanitized_message != event.sanitized_input:
            raise ScanConfirmationError("Sanitized message does not match the approved guardrail output.")
        if event.has_sensitive_data != bool(payload.detected_entities):
            raise ScanConfirmationError("Detected entity mapping does not match the approved scan.")
        if not event.has_sensitive_data and payload.sanitized_message != original_message:
            raise ScanConfirmationError("A clean message must be sent without modification.")
        return event

    def _scan_payload_digest(
        self,
        *,
        original_message: str,
        sanitized_message: str,
        detected_entities: list[GuardrailEntity],
        attachment_file_id: int | None,
        enabled_scanners: list[str],
    ) -> str:
        return canonical_json_digest(
            {
                "original_message": original_message,
                "sanitized_message": sanitized_message,
                "detected_entities": [entity.model_dump(mode="json") for entity in detected_entities],
                "attachment_file_id": attachment_file_id,
                "enabled_scanners": enabled_scanners,
            },
        )

    def _build_message_with_attachment_context(
        self,
        message: str,
        *,
        attachment_file_id: int | None,
        username: str,
    ) -> str:
        prompt = (message or "").strip()
        if attachment_file_id is None:
            return prompt

        attachment = self._get_accessible_attachment(attachment_file_id, username=username)
        if attachment.status != "completed":
            raise GuardrailViolationError("Attachment review is not complete yet.")

        review_payload = self._load_json_payload(attachment.review_result_json)
        if (
            isinstance(review_payload, dict)
            and review_payload.get("contains_business_sensitive")
            and review_payload.get("risk_level") == "high"
        ):
            raise GuardrailViolationError("High-risk attachment content cannot be sent to the model.")

        extracted_text = (attachment.extracted_text or "").strip()
        if not extracted_text:
            raise GuardrailViolationError("No readable text was extracted from the attachment.")

        marker = f"[Attachment: {attachment.original_filename}]"
        if marker in prompt and "Extracted content:" in prompt:
            return prompt

        summary = (attachment.extraction_summary or "").strip()
        review_summary = str(review_payload.get("summary") or "").strip() if isinstance(review_payload, dict) else ""
        parts = [
            prompt or "Please summarize the attached file.",
            "",
            marker,
            summary and f"Extraction summary: {summary}",
            review_summary and f"Security review: {review_summary}",
            f"Extracted content:\n{extracted_text[:self.MAX_ATTACHMENT_TEXT_CHARS]}",
        ]
        return "\n".join(str(part) for part in parts if part)

    def _get_accessible_attachment(self, file_id: int, *, username: str) -> UploadedFile:
        user = self.db.scalar(select(User).where(User.username == username))
        record = self.db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
        if record is None or (record.uploaded_by != username and (user is None or user.role != "admin")):
            raise GuardrailViolationError(f"Attachment {file_id} was not found.")
        return record

    def _load_json_payload(self, payload: Any) -> Any:
        if not isinstance(payload, str):
            return payload
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def _build_llm_messages(self, session_id: int) -> list[dict[str, str]]:
        messages, _ = self._build_llm_context(session_id)
        return messages

    def _build_llm_context(self, session_id: int) -> tuple[list[dict[str, str]], list[dict]]:
        settings = getattr(self, "settings", get_settings())
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(max(settings.chat_context_max_messages, 1))
        )
        newest_first = list(self.db.scalars(stmt).all())
        remaining_tokens = max(
            settings.chat_context_token_budget - self._estimate_tokens(self.SYSTEM_PLACEHOLDER_INSTRUCTION),
            1,
        )
        selected_newest_first: list[ChatMessage] = []
        for message in newest_first:
            cost = self._estimate_tokens(message.used_content or "")
            if selected_newest_first and cost > remaining_tokens:
                break
            selected_newest_first.append(message)
            remaining_tokens = max(remaining_tokens - cost, 0)
        messages = list(reversed(selected_newest_first))
        llm_messages = [
            {"role": "system", "content": self.SYSTEM_PLACEHOLDER_INSTRUCTION},
        ]
        entities: list[dict] = []
        seen_placeholders: set[str] = set()
        for message in messages:
            if message.used_content:
                llm_messages.append({"role": message.role, "content": message.used_content})
            if message.role != "user":
                continue
            for entity in message.sensitive_entities_json or []:
                replacement = entity.get("replacement")
                if not replacement or replacement in seen_placeholders:
                    continue
                seen_placeholders.add(replacement)
                entities.append(entity)
        return llm_messages, entities

    def _estimate_tokens(self, text: str) -> int:
        # Deliberately local and allocation-light: this is a conservative context
        # bound, not billing. UTF-8 bytes/3 tracks Chinese and mixed prompts better
        # than a character-only estimate without triggering tokenizer downloads.
        return max((len((text or "").encode("utf-8")) + 2) // 3, 1)

    def _deanonymize_assistant_reply(self, session_id: int, assistant_reply: str) -> str:
        session_entities = self._collect_session_entities(session_id)
        return self.guardrail_service.deanonymize_text(assistant_reply, session_entities)

    def _collect_session_entities(self, session_id: int) -> list[dict]:
        _, entities = self._build_llm_context(session_id)
        return entities
