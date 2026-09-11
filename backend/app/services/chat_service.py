from datetime import UTC, datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models.chat_message import ChatMessage
from ..models.uploaded_file import UploadedFile
from ..models.user import User
from ..models.provider_credential import ProviderCredential
from ..models.attachment import ChatSendSnapshot, MessageAttachment
from ..core.config import get_settings
from ..core.scan_proof import ScanProofError, canonical_json_digest, create_scan_proof, decode_scan_proof
from ..schemas.guardrail import GuardrailEntity
from ..schemas.messages import (
    AssistantReplyResponse, BusinessSensitiveFinding, ChatConfirmRequest, ChatPreviewRequest, ChatPreviewResponse,
)
from .guardrails.business_sensitive_scanner import BusinessSensitiveCategory, BusinessSensitiveResult
from .guardrails.llm_guard_service import get_guardrail_service
from .llm.openai_client import LLMProviderError
from .llm.provider_factory import get_llm_client
from .log_service import LogService
from .scan_event_service import ScanEventService
from .session_service import SessionService
from .system_setting_service import SystemSettingService
from .attachment_access_service import AttachmentAccessService, AttachmentAccessError
from .attachment_integrity import sha256


class GuardrailViolationError(Exception):
    pass


class ScanConfirmationError(GuardrailViolationError):
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

    def _log_detected_types(self, scan, *, attachment_requires_confirmation: bool) -> list[str]:
        detected_types = list(scan.entity_types or [])
        if scan.bancode_triggered:
            detected_types.append("SOURCE_CODE_ATTEMPT")
        if scan.prompt_injection_triggered:
            detected_types.append("PROMPT_INJECTION_ATTEMPT")
        if scan.ban_topics_triggered:
            detected_types.extend(
                f"BAN_TOPIC:{topic}" for topic in (scan.banned_topics or ["restricted-topic"])
            )
        if scan.business_sensitive_result.contains_business_sensitive:
            detected_types.extend(
                [
                    f"BUSINESS_SENSITIVE:{category.name}"
                    for category in scan.business_sensitive_result.categories
                ]
                or ["BUSINESS_SENSITIVE"]
            )
        if attachment_requires_confirmation:
            detected_types.append("BUSINESS_SENSITIVE_ATTACHMENT")
        return list(dict.fromkeys(detected_types))

    def preview_message(self, payload: ChatPreviewRequest, username: str) -> ChatPreviewResponse:
        session = self.session_service.get_session(payload.session_id, username=username)
        session_id, session_provider, session_model = session.id, session.provider, session.model
        enabled_scanners = self.setting_service.get_enabled_scanners()
        strict_mode = self.setting_service.get_scanner_strict_mode()
        message = payload.message.strip()
        if not message:
            raise GuardrailViolationError("A user prompt is required.")
        attachments = self._read_attachments(payload.attachment_file_id, username, reviewable=True)
        attachment_bindings = self._attachment_bindings(payload.attachment_file_id, username)
        attachment_finding = self._attachment_business_finding(payload.attachment_file_id, username)
        llm_messages = self._build_llm_messages(session.id, username)
        llm_messages.append({"role": "user", "content": message, **({"attachments": attachments} if attachments else {})})
        get_llm_client(session.provider, db=self.db).validate_attachments(llm_messages, session.model)
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
        self.db.commit()
        scan = self.guardrail_service.scan_text(
            message,
            enabled_scanners=enabled_scanners,
            business_runtime=business_runtime,
            business_runtime_unavailable=business_runtime_unavailable,
            strict_mode=strict_mode,
        )
        findings = ([BusinessSensitiveFinding(source="prompt", result=scan.business_sensitive_result)]
                    if scan.business_sensitive_result.contains_business_sensitive else [])
        if attachment_finding is not None:
            findings.append(attachment_finding)
        attachment_requires_confirmation = any(
            finding.source == "attachment" and finding.result.contains_business_sensitive
            for finding in findings
        )
        status = (
            "blocked"
            if self._should_block_scan(scan)
            else "needs_confirmation"
            if scan.has_sensitive_data
            or scan.business_sensitive_result.contains_business_sensitive
            or attachment_requires_confirmation
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
        self.log_service.create_log(
            session_id=session.id,
            message_id=None,
            scan_event_id=event.id,
            username=username,
            decision={"clean": "allowed", "needs_confirmation": "review", "blocked": "blocked"}[status],
            sanitized_content=scan.sanitized_text,
            detected_entity_types=self._log_detected_types(
                scan,
                attachment_requires_confirmation=attachment_requires_confirmation,
            ),
        )
        input_digest = self._scan_payload_digest(
            original_message=scan.original_text,
            sanitized_message=scan.sanitized_text,
            detected_entities=scan.entities,
            attachment_file_id=payload.attachment_file_id,
            enabled_scanners=scan.enabled_scanners,
            attachment_bindings=attachment_bindings,
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
        snapshot = None
        if status != "blocked":
            user = self.db.scalar(select(User).where(User.username == username))
            snapshot = ChatSendSnapshot(
                id=str(uuid4()), user_id=user.id, session_id=session_id, scan_event_id=event.id,
                provider=session_provider, model=session_model, policy_hash=self._send_policy_hash(session_id),
                prompt_hash=sha256(message.encode()), sanitized_prompt=scan.sanitized_text,
                attachments_json=attachment_bindings,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15), state="ready",
            )
            self.db.add(snapshot)
        self.db.commit()
        return ChatPreviewResponse(
            snapshot_id=snapshot.id if snapshot else None,
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
            business_sensitive_findings=findings,
            scan_proof=scan_proof if status != "blocked" else None,
            proof_expires_at=event.proof_expires_at if status != "blocked" else None,
            degraded_scanners=scan.degraded_scanners,
            scan_duration_ms=scan.scan_duration_ms,
        )

    def confirm_message(self, payload: ChatConfirmRequest, username: str) -> AssistantReplyResponse:
        prepared = self._prepare_confirmation(payload, username=username)
        if prepared.get("completed_response") is not None:
            return prepared["completed_response"]
        try:
            assistant_reply = prepared["llm_client"].chat(prepared["llm_messages"], prepared["session_model"])
        except Exception as exc:
            self._mark_confirmation_failed(prepared["event_id"], prepared["snapshot_id"], exc)
            raise
        return self._complete_confirmation(prepared, assistant_reply=assistant_reply, username=username)

    def confirm_message_stream(self, payload: ChatConfirmRequest, username: str):
        prepared = self._prepare_confirmation(payload, username=username)

        def generate():
            if prepared.get("completed_response") is not None:
                yield {"event": "completed", "response": prepared["completed_response"].model_dump(mode="json")}
                return
            yield {"event": "accepted", "scan_event_id": prepared["event_id"]}
            chunks: list[str] = []
            try:
                for delta in prepared["llm_client"].stream_chat(prepared["llm_messages"], prepared["session_model"]):
                    if delta:
                        chunks.append(delta)
                        yield {"event": "delta", "text": delta}
                assistant_reply = "".join(chunks).strip()
                if not assistant_reply:
                    raise LLMProviderError("Model stream did not contain text output.")
                response = self._complete_confirmation(prepared, assistant_reply=assistant_reply, username=username)
                yield {"event": "completed", "response": response.model_dump(mode="json")}
            except GeneratorExit:
                self._mark_confirmation_failed(
                    prepared["event_id"], prepared["snapshot_id"], RuntimeError("Client cancelled stream."),
                )
                raise
            except Exception as exc:
                self._mark_confirmation_failed(prepared["event_id"], prepared["snapshot_id"], exc)
                yield {"event": "error", "detail": str(exc), "retryable": True}
        return generate()

    def _prepare_confirmation(self, payload: ChatConfirmRequest, *, username: str) -> dict[str, Any]:
        session = self.session_service.get_session(payload.session_id, username=username)
        self.db.refresh(session, with_for_update=True)
        user = self.db.scalar(select(User).where(User.username == username))
        snapshot = self.db.get(ChatSendSnapshot, payload.snapshot_id) if payload.snapshot_id else None
        if snapshot is None or snapshot.user_id != user.id or snapshot.session_id != session.id:
            raise ScanConfirmationError("A valid server preview is required before sending.")
        if snapshot.state == "completed":
            return {"completed_response": AssistantReplyResponse(
                session_id=session.id,
                session_title=session.title,
                user_message=self.db.get(ChatMessage, snapshot.user_message_id),
                assistant_message=self.db.get(ChatMessage, snapshot.assistant_message_id),
            )}
        if snapshot.state != "ready":
            raise ScanConfirmationError("This send is already running or has an uncertain result; do not resend.")
        expires = snapshot.expires_at.replace(tzinfo=UTC) if snapshot.expires_at.tzinfo is None else snapshot.expires_at
        if (expires <= datetime.now(UTC) or snapshot.provider != session.provider
                or snapshot.model != session.model or snapshot.policy_hash != self._send_policy_hash(session.id)):
            raise ScanConfirmationError("Preview expired or configuration/history changed; preview again.")
        original_message = payload.original_message.strip()
        if (sha256(original_message.encode()) != snapshot.prompt_hash
                or payload.sanitized_message != snapshot.sanitized_prompt):
            raise ScanConfirmationError("Message differs from the approved preview.")
        expected_ids = [entry["file_id"] for entry in snapshot.attachments_json]
        if expected_ids != ([payload.attachment_file_id] if payload.attachment_file_id is not None else []):
            raise ScanConfirmationError("Attachment differs from the approved preview.")
        attachments = self._read_attachments(payload.attachment_file_id, username, reviewable=True)
        attachment_bindings = self._attachment_bindings(payload.attachment_file_id, username)
        if attachment_bindings != snapshot.attachments_json:
            raise ScanConfirmationError("Original file changed; preview again.")

        enabled_scanners = self.setting_service.get_enabled_scanners()
        strict_mode = self.setting_service.get_scanner_strict_mode()
        event = self._validate_confirmation(
            payload,
            username=username,
            original_message=original_message,
            enabled_scanners=enabled_scanners,
            strict_mode=strict_mode,
            attachment_bindings=attachment_bindings,
        )
        sanitized_message = event.sanitized_input
        llm_messages, session_entities = self._build_llm_context(session.id, username)
        llm_messages.append({
            "role": "user",
            "content": sanitized_message,
            **({"attachments": attachments} if attachments else {}),
        })
        client = get_llm_client(session.provider, db=self.db)
        client.validate_attachments(llm_messages, session.model)
        claimed = self.db.execute(update(ChatSendSnapshot).where(
            ChatSendSnapshot.id == snapshot.id,
            ChatSendSnapshot.state == "ready",
        ).values(state="running")).rowcount
        if claimed != 1:
            self.db.rollback()
            raise ScanConfirmationError("This preview has already been consumed.")
        self.scan_event_service.claim_for_confirmation(event)
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            original_content=original_message,
            sanitized_content=sanitized_message,
            used_content=sanitized_message,
            has_sensitive_data=event.has_sensitive_data,
            sensitive_entities_json=[entity.model_dump() for entity in payload.detected_entities] or None,
        )
        self.db.add(user_message)
        self.db.flush()
        for attachment in attachments:
            self.db.add(MessageAttachment(
                message_id=user_message.id,
                file_id=attachment.file_id,
                sha256=attachment.sha256,
                filename=attachment.filename,
            ))
        snapshot.user_message_id = user_message.id
        self.log_service.attach_message(scan_event_id=event.id, message_id=user_message.id)
        session_entities.extend(entity.model_dump() for entity in payload.detected_entities)
        self.db.commit()
        return {
            "event_id": event.id,
            "snapshot_id": snapshot.id,
            "session_id": session.id,
            "session_title": session.title,
            "session_model": session.model,
            "user_message_id": user_message.id,
            "llm_messages": llm_messages,
            "session_entities": session_entities,
            "llm_client": client,
        }

    def _mark_confirmation_failed(self, event_id: int, snapshot_id: str, exc: Exception) -> None:
        event = self.scan_event_service.get_event(event_id)
        if event is not None:
            self.scan_event_service.mark_send_failed(event, str(exc))
        snapshot = self.db.get(ChatSendSnapshot, snapshot_id)
        if snapshot is not None and snapshot.state == "running":
            snapshot.state = "unknown"
        self.db.commit()

    def _complete_confirmation(self, prepared: dict[str, Any], *, assistant_reply: str, username: str) -> AssistantReplyResponse:
        deanonymized_reply = self.guardrail_service.deanonymize_text(
            assistant_reply,
            prepared["session_entities"],
        )
        assistant_message = ChatMessage(
            session_id=prepared["session_id"],
            role="assistant",
            original_content=assistant_reply,
            sanitized_content=deanonymized_reply,
            used_content=assistant_reply,
            has_sensitive_data=False,
            sensitive_entities_json=None,
        )
        self.db.add(assistant_message)
        self.db.flush()
        user_message = self.db.get(ChatMessage, prepared["user_message_id"])
        snapshot = self.db.get(ChatSendSnapshot, prepared["snapshot_id"])
        snapshot.assistant_message_id = assistant_message.id
        snapshot.state = "completed"
        event = self.scan_event_service.get_event(prepared["event_id"])
        if event is None:
            raise ScanConfirmationError("Scan event disappeared before confirmation completed.")
        self.scan_event_service.mark_confirmed(
            event,
            assistant_raw_output=assistant_reply,
            assistant_display_output=deanonymized_reply,
        )
        event.username = username
        session = self.session_service.get_session(prepared["session_id"], username=username)
        session.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        self.db.refresh(session)

        return AssistantReplyResponse(
            session_id=session.id,
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
        attachment_bindings: list[dict],
    ):
        if payload.scan_event_id is None or not payload.scan_proof:
            raise ScanConfirmationError("A valid scan proof is required. Please scan the message again.")
        event = self.scan_event_service.get_event_for_confirmation(
            payload.scan_event_id,
            session_id=payload.session_id,
            username=username,
            lock=True,
        )
        if event is None or event.id != self.db.get(ChatSendSnapshot, payload.snapshot_id).scan_event_id:
            raise ScanConfirmationError("Scan event was not found for this user, session, and snapshot.")
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
            attachment_bindings=attachment_bindings,
        )
        try:
            claims = decode_scan_proof(payload.scan_proof)
        except ScanProofError as exc:
            raise ScanConfirmationError(str(exc)) from exc
        expected = {
            "event_id": payload.scan_event_id,
            "session_id": payload.session_id,
            "username": username,
            "payload_digest": input_digest,
            "scanner_config_hash": scanner_config_hash,
            "attachment_file_id": payload.attachment_file_id,
        }
        if any(claims.get(key) != value for key, value in expected.items()):
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
        attachment_bindings: list[dict] | None = None,
    ) -> str:
        return canonical_json_digest({
            "original_message": original_message,
            "sanitized_message": sanitized_message,
            "detected_entities": [entity.model_dump(mode="json") for entity in detected_entities],
            "attachment_file_id": attachment_file_id,
            "enabled_scanners": enabled_scanners,
            "attachment_bindings": attachment_bindings or [],
        })

    def _read_attachments(self, file_id: int | None, username: str, *, reviewable: bool = False):
        if file_id is None:
            return []
        try:
            service = AttachmentAccessService(self.db)
            reader = service.read_reviewable if reviewable else service.read_approved
            return [reader(file_id, username)]
        except AttachmentAccessError as exc:
            raise GuardrailViolationError(str(exc)) from exc

    def _attachment_bindings(self, file_id: int | None, username: str) -> list[dict]:
        if file_id is None:
            return []
        try:
            return [AttachmentAccessService(self.db).review_binding(file_id, username)]
        except AttachmentAccessError as exc:
            raise GuardrailViolationError(str(exc)) from exc

    def _attachment_business_finding(self, file_id: int | None, username: str) -> BusinessSensitiveFinding | None:
        if file_id is None:
            return None
        record = self._get_accessible_attachment(file_id, username=username)
        payload = self._load_json_payload(record.review_result_json) or {}
        if not payload.get("contains_business_sensitive"):
            return None
        categories = []
        for hit in payload.get("hits") or []:
            try:
                categories.append(BusinessSensitiveCategory(
                    name=hit.get("category"), matched_text=hit.get("matched_text", ""), reason=hit.get("reason", ""),
                ))
            except Exception:
                continue
        result = BusinessSensitiveResult(
            contains_business_sensitive=True,
            risk_level=payload.get("risk_level", "medium"),
            categories=categories,
            summary=payload.get("summary", "检测到商务敏感内容。"),
            confidence=payload.get("confidence", 0.0),
        )
        return BusinessSensitiveFinding(
            source="attachment", file_id=record.id, filename=record.original_filename, result=result,
        )

    def _send_policy_hash(self, session_id: int) -> str:
        history = self.db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id)
                                  .order_by(ChatMessage.id)).all()
        data = {
            "settings": get_settings().model_dump(mode="json"),
            "scanners": self.setting_service.get_enabled_scanners(),
            "history": [(m.id, m.used_content) for m in history],
            "endpoints": [(p.provider, p.base_url, p.api_key, p.updated_at)
                          for p in self.db.scalars(select(ProviderCredential).order_by(ProviderCredential.id))],
        }
        return sha256(json.dumps(data, sort_keys=True, default=str).encode())

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

    def _build_llm_messages(self, session_id: int, username: str) -> list[dict]:
        messages, _ = self._build_llm_context(session_id, username)
        return messages

    def _build_llm_context(self, session_id: int, username: str | None = None) -> tuple[list[dict], list[dict]]:
        settings = getattr(self, "settings", get_settings())
        if username is None:
            username = self.session_service.get_session(session_id).created_by
        stmt = (select(ChatMessage).where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(max(settings.chat_context_max_messages, 1)))
        newest_first = list(self.db.scalars(stmt).all())
        remaining_tokens = max(
            settings.chat_context_token_budget - self._estimate_tokens(self.SYSTEM_PLACEHOLDER_INSTRUCTION),
            1,
        )
        selected_newest_first = []
        for message in newest_first:
            cost = self._estimate_tokens(message.used_content or "")
            if selected_newest_first and cost > remaining_tokens:
                break
            selected_newest_first.append(message)
            remaining_tokens = max(remaining_tokens - cost, 0)
        messages = list(reversed(selected_newest_first))
        prepared = [{"role": "system", "content": self.SYSTEM_PLACEHOLDER_INSTRUCTION}]
        entities: list[dict] = []
        seen_placeholders: set[str] = set()
        for message in messages:
            item = {"role": message.role, "content": message.used_content or ""}
            attachments = []
            for reference in message.attachments:
                try:
                    attachments.append(AttachmentAccessService(self.db).read_confirmed(
                        reference.file_id, username, reference.sha256,
                    ))
                except AttachmentAccessError as exc:
                    raise GuardrailViolationError(str(exc)) from exc
            if attachments:
                item["attachments"] = attachments
            if item["content"] or attachments:
                prepared.append(item)
            if message.role == "user":
                for entity in message.sensitive_entities_json or []:
                    replacement = entity.get("replacement")
                    if replacement and replacement not in seen_placeholders:
                        seen_placeholders.add(replacement)
                        entities.append(entity)
        return prepared, entities

    def _estimate_tokens(self, text: str) -> int:
        return max((len((text or "").encode("utf-8")) + 2) // 3, 1)

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
