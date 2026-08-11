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
            display_name="\u963f\u91cc\u4e91\u767e\u70bc",
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_models=(
                "deepseek-v4-flash",
                "deepseek-v4-pro",
                "qwen-plus",
                "qwen3.6-plus",
            ),
        ),
        "openrouter": ProviderDefinition(
            provider="openrouter",
            display_name="OpenRouter",
            default_base_url="https://openrouter.ai/api/v1",
            default_models=(
                "minimax/minimax-m3",
                "openai/gpt-5.5",
                "anthropic/claude-fable-5",
            ),
        ),
        "bedrock": ProviderDefinition(
            provider="bedrock",
            display_name="AWS Bedrock",
            default_base_url=f"bedrock-runtime.{settings.bedrock_region}.amazonaws.com",
            default_models=(
                settings.bedrock_default_model,
                "amazon.nova-lite-v1:0",
                "anthropic.claude-3-5-haiku-20241022-v1:0",
            ),
            requires_api_key=False,
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
