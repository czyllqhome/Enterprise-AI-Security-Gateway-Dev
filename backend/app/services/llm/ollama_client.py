import json
import re
from urllib import error, request

from .base import BaseLLMClient
from .openai_client import LLMProviderError


class OllamaClient(BaseLLMClient):
    def __init__(self, base_url: str, provider_label: str = "Ollama") -> None:
        self.base_url = base_url.rstrip("/")
        self.provider_label = provider_label

    def chat(self, messages: list[dict], model: str) -> str:
        payload = json.dumps(
            {
                "model": model,
                "messages": self._without_thinking_mode(messages),
                "stream": False,
                "think": False,
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise LLMProviderError(f"{self.provider_label} rejected the request: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check whether Ollama is running and the saved base URL is correct."
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"{self.provider_label} returned invalid JSON.") from exc

        message = data.get("message") or {}
        content = self._strip_thinking_blocks(message.get("content") or "")
        if content:
            return content
        raise LLMProviderError(f"{self.provider_label} response did not contain text output.")

    def stream_chat(self, messages: list[dict], model: str):
        payload = json.dumps(
            {
                "model": model,
                "messages": self._without_thinking_mode(messages),
                "stream": True,
                "think": False,
            },
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    data = json.loads(raw_line.decode("utf-8"))
                    content = str((data.get("message") or {}).get("content") or "")
                    if content:
                        yield content
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise LLMProviderError(f"{self.provider_label} rejected the request: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise LLMProviderError(
                f"{self.provider_label} connection failed. Check whether Ollama is running and the saved base URL is correct."
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected {self.provider_label} client failure: {exc}") from exc

    def _without_thinking_mode(self, messages: list[dict]) -> list[dict]:
        instruction = (
            "/no_think\n"
            "Do not use thinking mode. Do not output internal reasoning, hidden chain-of-thought, "
            "or <think> blocks. Answer directly."
        )
        prepared = [dict(message) for message in messages]
        if prepared and prepared[0].get("role") == "system":
            prepared[0]["content"] = f"{instruction}\n\n{prepared[0].get('content', '')}"
            return prepared
        return [{"role": "system", "content": instruction}, *prepared]

    def _strip_thinking_blocks(self, content: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", content or "", flags=re.IGNORECASE | re.DOTALL)
        return cleaned.strip()
