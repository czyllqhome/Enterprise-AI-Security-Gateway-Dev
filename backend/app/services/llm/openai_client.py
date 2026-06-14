from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, BadRequestError, OpenAI

from .base import BaseLLMClient


class LLMProviderError(Exception):
    pass


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider_label: str = "OpenAI",
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider_label = provider_label
        self.client = OpenAI(
            api_key=api_key or None,
            base_url=base_url,
            default_headers=default_headers,
        )

    def chat(self, messages: list[dict], model: str) -> str:
        try:
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
