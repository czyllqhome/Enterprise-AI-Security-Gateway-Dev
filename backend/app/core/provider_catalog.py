from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True)
class ProviderDefinition:
    provider: str
    display_name: str
    default_base_url: str
    default_models: tuple[str, ...]
    requires_api_key: bool = True


def get_provider_catalog() -> dict[str, ProviderDefinition]:
    settings = get_settings()
    return {
        "openai": ProviderDefinition(
            provider="openai",
            display_name="OpenAI",
            default_base_url=settings.openai_base_url,
            default_models=(
                "gpt-4.1-mini",
                "gpt-5.4-mini",
                "gpt-5.5-pro",
            ),
        ),
        "qwen": ProviderDefinition(
            provider="qwen",
            display_name="阿里云百炼",
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_models=(
                "deepseek-v4-pro",
                "qwen-plus",
                "qwen3.6-plus",
            ),
        ),
        "ollama": ProviderDefinition(
            provider="ollama",
            display_name="Ollama",
            default_base_url="http://localhost:11434",
            default_models=(
                "qwen3.5:4b",
            ),
            requires_api_key=False,
        ),
    }
