from __future__ import annotations

from ...core.config import get_settings
from .base import BaseLLMClient
from .openai_client import LLMProviderError


class BedrockClient(BaseLLMClient):
    def __init__(self, *, region_name: str, provider_label: str = "AWS Bedrock") -> None:
        self.provider_label = provider_label
        settings = get_settings()
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import BotoCoreError, ClientError

            session_kwargs = {}
            if settings.bedrock_profile_name.strip():
                session_kwargs["profile_name"] = settings.bedrock_profile_name.strip()
            self._boto_core_error = BotoCoreError
            self._client_error = ClientError
            session = boto3.Session(**session_kwargs)
            self.client = session.client(
                "bedrock-runtime",
                region_name=region_name,
                config=Config(
                    connect_timeout=settings.bedrock_timeout_seconds,
                    read_timeout=settings.bedrock_timeout_seconds,
                    retries={"max_attempts": 2},
                ),
            )
        except Exception as exc:
            raise LLMProviderError(
                "AWS Bedrock client could not be initialized. Check boto3 installation and AWS credentials."
            ) from exc

    def chat(self, messages: list[dict], model: str) -> str:
        self.validate_attachments(messages, model)
        system, converse_messages = self._to_converse_messages(messages)
        kwargs = {
            "modelId": model,
            "messages": converse_messages,
            "inferenceConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxTokens": 1024,
            },
        }
        if system:
            kwargs["system"] = system

        try:
            response = self.client.converse(**kwargs)
        except self._client_error as exc:
            detail = exc.response.get("Error", {}).get("Message") or str(exc)
            raise LLMProviderError(f"{self.provider_label} rejected the request: {detail}") from exc
        except self._boto_core_error as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check AWS region, credentials, and Bedrock model access."
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc

        text = self._extract_text(response)
        if text:
            return text.strip()
        raise LLMProviderError(f"{self.provider_label} response did not contain text output.")

    def stream_chat(self, messages: list[dict], model: str):
        system, converse_messages = self._to_converse_messages(messages)
        kwargs = {
            "modelId": model,
            "messages": converse_messages,
            "inferenceConfig": {"temperature": 0.2, "topP": 0.9, "maxTokens": 1024},
        }
        if system:
            kwargs["system"] = system
        try:
            response = self.client.converse_stream(**kwargs)
            for event in response.get("stream") or []:
                delta = ((event.get("contentBlockDelta") or {}).get("delta") or {})
                text = str(delta.get("text") or "")
                if text:
                    yield text
        except self._client_error as exc:
            detail = exc.response.get("Error", {}).get("Message") or str(exc)
            raise LLMProviderError(f"{self.provider_label} rejected the request: {detail}") from exc
        except self._boto_core_error as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check AWS region, credentials, and Bedrock model access."
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc

    def _to_converse_messages(self, messages: list[dict]) -> tuple[list[dict], list[dict]]:
        system: list[dict] = []
        converse_messages: list[dict] = []
        for message in messages:
            role = str(message.get("role") or "user").strip().lower()
            content = str(message.get("content") or "")
            if role == "system":
                if content:
                    system.append({"text": content})
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            converse_messages.append(
                {
                    "role": role,
                    "content": [{"text": content}],
                }
            )
        if not converse_messages:
            converse_messages.append({"role": "user", "content": [{"text": ""}]})
        return system, converse_messages

    def _extract_text(self, response: dict) -> str:
        message = ((response.get("output") or {}).get("message") or {})
        blocks = message.get("content") or []
        texts = [str(block.get("text") or "") for block in blocks if isinstance(block, dict) and block.get("text")]
        return "\n".join(texts).strip()
