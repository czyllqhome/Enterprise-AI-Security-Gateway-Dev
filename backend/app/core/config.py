import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DATABASE_URL = "postgresql+psycopg://ai_guard_user:change-me-strong-password@127.0.0.1:5432/ai_guard"


class Settings(BaseSettings):
    app_name: str = "LLM Guard Demo"
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8002, alias="APP_PORT")
    jwt_secret_key: str = Field(default="replace-me", alias="JWT_SECRET_KEY")
    jwt_expires_minutes: int = Field(default=480, alias="JWT_EXPIRES_MINUTES")
    cors_origins: str = Field(default="http://127.0.0.1:5173", alias="CORS_ORIGINS")
    default_admin_username: str = Field(default="admin", alias="DEFAULT_ADMIN_USERNAME")
    default_admin_password: str = Field(default="", alias="DEFAULT_ADMIN_PASSWORD")
    default_admin_display_name: str = Field(default="Administrator", alias="DEFAULT_ADMIN_DISPLAY_NAME")
    api_key_encryption_secret: str = Field(default="replace-me", alias="API_KEY_ENCRYPTION_SECRET")
    default_provider: str = Field(default="openai", alias="DEFAULT_PROVIDER")
    default_model: str = Field(default="gpt-4.1-mini", alias="DEFAULT_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="OPENAI_BASE_URL",
    )
    bedrock_region: str = Field(default="us-east-1", alias="BEDROCK_REGION")
    bedrock_default_model: str = Field(
        default="anthropic.claude-3-5-haiku-20241022-v1:0",
        alias="BEDROCK_DEFAULT_MODEL",
    )
    bedrock_profile_name: str = Field(default="", alias="BEDROCK_PROFILE_NAME")
    bedrock_timeout_seconds: float = Field(default=60.0, alias="BEDROCK_TIMEOUT_SECONDS")
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
    )
    local_model_cache_dir: str = Field(
        default=str(PROJECT_ROOT / ".model-cache"),
        alias="LOCAL_MODEL_CACHE_DIR",
    )
    privacy_filter_enabled: bool = Field(default=True, alias="PRIVACY_FILTER_ENABLED")
    privacy_filter_model_path: str = Field(
        default=str(BASE_DIR / ".model-cache" / "openai-privacy-filter"),
        alias="PRIVACY_FILTER_MODEL_PATH",
    )
    privacy_filter_auto_download: bool = Field(default=False, alias="PRIVACY_FILTER_AUTO_DOWNLOAD")
    privacy_filter_device: str = Field(default="auto", alias="PRIVACY_FILTER_DEVICE")
    privacy_filter_decode_mode: str = Field(default="viterbi", alias="PRIVACY_FILTER_DECODE_MODE")
    privacy_filter_output_mode: str = Field(default="typed", alias="PRIVACY_FILTER_OUTPUT_MODE")
    privacy_filter_context_window_length: int = Field(default=0, alias="PRIVACY_FILTER_CONTEXT_WINDOW_LENGTH")
    business_sensitive_enabled: bool = Field(default=True, alias="BUSINESS_SENSITIVE_ENABLED")
    business_sensitive_provider: str = Field(default="ollama", alias="BUSINESS_SENSITIVE_PROVIDER")
    business_sensitive_model: str = Field(default="qwen3.5:4b", alias="BUSINESS_SENSITIVE_MODEL")
    business_sensitive_ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        alias="BUSINESS_SENSITIVE_OLLAMA_URL",
    )
    business_sensitive_qwen_model: str = Field(default="deepseek-v4-flash", alias="BUSINESS_SENSITIVE_QWEN_MODEL")
    business_sensitive_qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="BUSINESS_SENSITIVE_QWEN_BASE_URL",
    )
    business_sensitive_qwen_api_key: str = Field(default="", alias="BUSINESS_SENSITIVE_QWEN_API_KEY")
    business_sensitive_bedrock_model: str = Field(
        default="anthropic.claude-3-5-haiku-20241022-v1:0",
        alias="BUSINESS_SENSITIVE_BEDROCK_MODEL",
    )
    business_sensitive_timeout_seconds: float = Field(
        default=20.0,
        alias="BUSINESS_SENSITIVE_TIMEOUT_SECONDS",
    )
    file_review_enabled: bool = Field(default=True, alias="FILE_REVIEW_ENABLED")
    file_review_provider: str = Field(default="ollama", alias="FILE_REVIEW_PROVIDER")
    file_review_model: str = Field(default="qwen3.5:4b", alias="FILE_REVIEW_MODEL")
    file_review_bedrock_model: str = Field(
        default="anthropic.claude-3-5-haiku-20241022-v1:0",
        alias="FILE_REVIEW_BEDROCK_MODEL",
    )
    file_review_ollama_url: str = Field(default="http://127.0.0.1:11434", alias="FILE_REVIEW_OLLAMA_URL")
    file_review_timeout_seconds: float = Field(default=45.0, alias="FILE_REVIEW_TIMEOUT_SECONDS")
    file_review_max_upload_mb: int = Field(default=20, alias="FILE_REVIEW_MAX_UPLOAD_MB")
    file_review_default_storage_path: str = Field(
        default=str(BASE_DIR / "uploaded-documents"),
        alias="FILE_REVIEW_DEFAULT_STORAGE_PATH",
    )
    file_review_active_storage_profile: str = Field(
        default_factory=lambda: "windows" if os.name == "nt" else "linux",
        alias="FILE_REVIEW_ACTIVE_STORAGE_PROFILE",
    )
    file_review_windows_storage_path: str = Field(
        default="",
        alias="FILE_REVIEW_WINDOWS_STORAGE_PATH",
    )
    file_review_linux_storage_path: str = Field(
        default="/var/lib/ai-security-gateway/uploaded-documents",
        alias="FILE_REVIEW_LINUX_STORAGE_PATH",
    )
    file_review_per_user_storage_dirs: bool = Field(
        default=True,
        alias="FILE_REVIEW_PER_USER_STORAGE_DIRS",
    )
    file_ocr_det_model_dir: str = Field(
        default=str(BASE_DIR / ".model-cache" / "ch_PP-OCRv4_det_infer"),
        alias="FILE_OCR_DET_MODEL_DIR",
    )
    file_ocr_rec_model_dir: str = Field(default="", alias="FILE_OCR_REC_MODEL_DIR")
    file_ocr_cls_model_dir: str = Field(default="", alias="FILE_OCR_CLS_MODEL_DIR")
    qwen3guard_enabled: bool = Field(default=True, alias="QWEN3GUARD_ENABLED")
    qwen3guard_model: str = Field(default="Qwen/Qwen3Guard-Gen-0.6B", alias="QWEN3GUARD_MODEL")
    qwen3guard_model_path: str = Field(default="", alias="QWEN3GUARD_MODEL_PATH")
    qwen3guard_max_new_tokens: int = Field(default=96, alias="QWEN3GUARD_MAX_NEW_TOKENS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
