import threading
from collections import OrderedDict

from sqlalchemy.orm import Session

from ...core.provider_catalog import get_provider_catalog
from ...core.config import get_settings
from ..provider_credential_service import ProviderCredentialNotFoundError, ProviderCredentialService
from .bedrock_client import BedrockClient
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient


_CLIENT_CACHE: "OrderedDict[tuple, object]" = OrderedDict()
_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_CACHE_MAX_SIZE = 32


def _cached_client(key: tuple, factory):
    with _CLIENT_CACHE_LOCK:
        cached = _CLIENT_CACHE.get(key)
        if cached is not None:
            _CLIENT_CACHE.move_to_end(key)
            return cached
        client = factory()
        _CLIENT_CACHE[key] = client
        while len(_CLIENT_CACHE) > _CLIENT_CACHE_MAX_SIZE:
            _CLIENT_CACHE.popitem(last=False)
        return client


def get_llm_client(provider: str, db: Session | None = None):
    normalized = provider.lower()
    if normalized in {"openai", "qwen", "openrouter"}:
        if db is None:
            raise ProviderCredentialNotFoundError(f"No database session was provided for provider '{provider}'.")
        credential = ProviderCredentialService(db).require_credential(normalized)
        default_headers = None
        if normalized == "openrouter":
            default_headers = {
                "HTTP-Referer": "http://127.0.0.1:5173",
                "X-OpenRouter-Title": "Enterprise AI Security Gateway",
            }
        key = (
            normalized,
            credential.base_url,
            credential.api_key,
            credential.display_name,
            tuple(sorted((default_headers or {}).items())),
        )
        return _cached_client(
            key,
            lambda: OpenAIClient(
                api_key=credential.api_key,
                base_url=credential.base_url,
                provider_label=credential.display_name,
                default_headers=default_headers,
            ),
        )
    if normalized == "bedrock":
        definition = get_provider_catalog()["bedrock"]
        region = get_settings().bedrock_region
        return _cached_client(
            ("bedrock", region, definition.display_name),
            lambda: BedrockClient(
                region_name=region,
                provider_label=definition.display_name,
            ),
        )
    if normalized == "ollama":
        if db is None:
            definition = get_provider_catalog()["ollama"]
            return _cached_client(
                ("ollama", definition.default_base_url, definition.display_name),
                lambda: OllamaClient(
                    base_url=definition.default_base_url,
                    provider_label=definition.display_name,
                ),
            )
        credential = ProviderCredentialService(db).require_credential(normalized)
        return _cached_client(
            ("ollama", credential.base_url, credential.display_name),
            lambda: OllamaClient(
                base_url=credential.base_url,
                provider_label=credential.display_name,
            ),
        )
    raise ValueError(f"Unsupported provider: {provider}")


def clear_llm_client_cache() -> None:
    with _CLIENT_CACHE_LOCK:
        clients = list(_CLIENT_CACHE.values())
        _CLIENT_CACHE.clear()
    for client in clients:
        close = getattr(getattr(client, "client", client), "close", None)
        if callable(close):
            close()
