from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, BadRequestError, OpenAI

from .base import BaseLLMClient
from .attachments import responses_messages


class LLMProviderError(Exception):
    pass


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider_label: str = "OpenAI",
        default_headers: dict[str, str] | None = None,
        attachment_capabilities: dict[str, list[str]] | None = None,
    ) -> None:
        self.provider_label = provider_label
        self.attachment_capabilities = attachment_capabilities or {}
        self.client = OpenAI(
            api_key=api_key or None,
            base_url=base_url,
            default_headers=default_headers,
        )

    def chat(self, messages: list[dict], model: str) -> str:
        try:
            if any(message.get("attachments") for message in messages):
                self.validate_attachments(messages, model)
                response = self.client.responses.create(
                    model=model,
                    input=responses_messages(messages),
                    store=False,
                )
                if response.status != "completed" or not response.output_text:
                    raise LLMProviderError(f"{self.provider_label} file response is incomplete or empty.")
                return response.output_text.strip()
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )
        except AuthenticationError as exc:
            raise LLMProviderError(f"{self.provider_label} authentication failed. Check the saved API key.") from exc
        except BadRequestError as exc:
            raise LLMProviderError(f"{self.provider_label} rejected the request: {exc}") from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check network access and the saved base URL."
            ) from exc
        except APIError as exc:
            raise LLMProviderError(f"{self.provider_label} request failed: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()

        raise LLMProviderError(f"{self.provider_label} response did not contain text output.")

    def validate_attachments(self, messages: list[dict], model: str) -> None:
        allowed = self.attachment_capabilities.get(model, [])
        total = 0
        for message in messages:
            for attachment in message.get("attachments") or []:
                if attachment.mime_type not in allowed:
                    raise LLMProviderError(
                        f"Original {attachment.mime_type} input is not enabled for {self.provider_label}/{model}.",
                    )
                total += len(attachment.content)
        if total > 20 * 1024 * 1024:
            raise LLMProviderError("Original attachments exceed the 20 MB request budget.")

    def stream_chat(self, messages: list[dict], model: str):
        # Responses file streaming has different event semantics. Preserve the
        # original bytes by using the validated non-streaming path until an
        # endpoint-specific Responses stream adapter is enabled.
        if any(message.get("attachments") for message in messages):
            yield self.chat(messages, model)
            return
        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except AuthenticationError as exc:
            raise LLMProviderError(f"{self.provider_label} authentication failed. Check the saved API key.") from exc
        except BadRequestError as exc:
            raise LLMProviderError(f"{self.provider_label} rejected the request: {exc}") from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check network access and the saved base URL."
            ) from exc
        except APIError as exc:
            raise LLMProviderError(f"{self.provider_label} request failed: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc
