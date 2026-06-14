from sqlalchemy.orm import Session

from ...core.provider_catalog import get_provider_catalog
from ..provider_credential_service import ProviderCredentialNotFoundError, ProviderCredentialService
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient


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
        return OpenAIClient(
            api_key=credential.api_key,
            base_url=credential.base_url,
            provider_label=credential.display_name,
            default_headers=default_headers,
        )
    if normalized == "ollama":
        if db is None:
            definition = get_provider_catalog()["ollama"]
            return OllamaClient(
                base_url=definition.default_base_url,
                provider_label=definition.display_name,
            )
        credential = ProviderCredentialService(db).require_credential(normalized)
        return OllamaClient(
            base_url=credential.base_url,
            provider_label=credential.display_name,
        )
    raise ValueError(f"Unsupported provider: {provider}")
