import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DATABASE_URL = "postgresql+psycopg://ai_guard_user:change-me-strong-password@127.0.0.1:5432/ai_guard"
DEFAULT_QWEN3GUARD_MODEL = "Qwen/Qwen3Guard-Gen-4B"


class Settings(BaseSettings):
    office_converter_path: str = Field(default="", alias="OFFICE_CONVERTER_PATH")
    office_converter_timeout: int = Field(default=120, ge=1, le=600, alias="OFFICE_CONVERTER_TIMEOUT")
    file_review_policy_version: str = Field(default="1", alias="FILE_REVIEW_POLICY_VERSION")
    file_review_vision_model: str = Field(default="qwen3.5:4b", alias="FILE_REVIEW_VISION_MODEL")
    file_review_vision_base_url: str = Field(default="http://127.0.0.1:11434", alias="FILE_REVIEW_VISION_BASE_URL")
    file_review_vision_timeout: int = Field(default=120, ge=1, le=600, alias="FILE_REVIEW_VISION_TIMEOUT")
    # provider -> exact model -> accepted MIME types, enabled only after endpoint verification.
    attachment_capabilities: dict[str, dict[str, list[str]]] = Field(default_factory=dict, alias="ATTACHMENT_CAPABILITIES")
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
    scan_proof_secret: str = Field(default="replace-me-scan-proof", alias="SCAN_PROOF_SECRET")
    scan_proof_ttl_seconds: int = Field(default=300, alias="SCAN_PROOF_TTL_SECONDS")
    require_scan_proof: bool = Field(default=True, alias="REQUIRE_SCAN_PROOF")
    scanner_strict_mode: bool = Field(default=True, alias="SCANNER_STRICT_MODE")
    scanner_total_deadline_ms: int = Field(default=15000, alias="SCANNER_TOTAL_DEADLINE_MS")
    scanner_executor_workers: int = Field(default=8, alias="SCANNER_EXECUTOR_WORKERS")
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
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout_seconds: float = Field(default=30.0, alias="DB_POOL_TIMEOUT_SECONDS")
    db_pool_recycle_seconds: int = Field(default=1800, alias="DB_POOL_RECYCLE_SECONDS")
    chat_context_token_budget: int = Field(default=8192, alias="CHAT_CONTEXT_TOKEN_BUDGET")
    chat_context_max_messages: int = Field(default=100, alias="CHAT_CONTEXT_MAX_MESSAGES")
    session_list_limit: int = Field(default=100, alias="SESSION_LIST_LIMIT")
    session_detail_message_limit: int = Field(default=200, alias="SESSION_DETAIL_MESSAGE_LIMIT")
    admin_query_lookback_days: int = Field(default=90, alias="ADMIN_QUERY_LOOKBACK_DAYS")
    admin_query_max_rows: int = Field(default=10000, alias="ADMIN_QUERY_MAX_ROWS")
    local_model_cache_dir: str = Field(
        default=str(PROJECT_ROOT / ".model-cache"),
        alias="LOCAL_MODEL_CACHE_DIR",
    )
    # Deployment-wide device policy for local model scanners. Individual scanner
    # settings can use "inherit" or override this with auto/cpu/cuda.
    local_model_device: str = Field(default="auto", alias="LOCAL_MODEL_DEVICE")
    privacy_filter_enabled: bool = Field(default=True, alias="PRIVACY_FILTER_ENABLED")
    privacy_filter_model_path: str = Field(
        default=str(BASE_DIR / ".model-cache" / "openai-privacy-filter"),
        alias="PRIVACY_FILTER_MODEL_PATH",
    )
    privacy_filter_auto_download: bool = Field(default=False, alias="PRIVACY_FILTER_AUTO_DOWNLOAD")
    privacy_filter_device: str = Field(default="inherit", alias="PRIVACY_FILTER_DEVICE")
    privacy_filter_decode_mode: str = Field(default="viterbi", alias="PRIVACY_FILTER_DECODE_MODE")
    privacy_filter_output_mode: str = Field(default="typed", alias="PRIVACY_FILTER_OUTPUT_MODE")
    privacy_filter_context_window_length: int = Field(default=0, alias="PRIVACY_FILTER_CONTEXT_WINDOW_LENGTH")
    privacy_filter_timeout_ms: int = Field(default=1500, alias="PRIVACY_FILTER_TIMEOUT_MS")
    privacy_filter_workers: int = Field(default=2, alias="PRIVACY_FILTER_WORKERS")
    business_sensitive_enabled: bool = Field(default=True, alias="BUSINESS_SENSITIVE_ENABLED")
    business_sensitive_provider: str = Field(default="ollama", alias="BUSINESS_SENSITIVE_PROVIDER")
    business_sensitive_model: str = Field(default="qwen3.5:4b", alias="BUSINESS_SENSITIVE_MODEL")
    business_sensitive_ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        alias="BUSINESS_SENSITIVE_OLLAMA_URL",
    )
    business_sensitive_qwen_model: str = Field(default="qwen3.8-flash", alias="BUSINESS_SENSITIVE_QWEN_MODEL")
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
    business_sensitive_timeout_ms: int = Field(default=12000, alias="BUSINESS_SENSITIVE_TIMEOUT_MS")
    business_sensitive_max_tokens: int = Field(default=1024, alias="BUSINESS_SENSITIVE_MAX_TOKENS")
    business_sensitive_workers: int = Field(default=20, alias="BUSINESS_SENSITIVE_WORKERS")
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
    file_review_worker_mode: str = Field(default="embedded", alias="FILE_REVIEW_WORKER_MODE")
    file_review_worker_poll_seconds: float = Field(default=1.0, alias="FILE_REVIEW_WORKER_POLL_SECONDS")
    file_review_job_lease_seconds: int = Field(default=1800, alias="FILE_REVIEW_JOB_LEASE_SECONDS")
    file_review_job_max_attempts: int = Field(default=3, alias="FILE_REVIEW_JOB_MAX_ATTEMPTS")
    file_review_chunk_workers: int = Field(default=4, alias="FILE_REVIEW_CHUNK_WORKERS")
    file_review_max_chunks: int = Field(default=40, alias="FILE_REVIEW_MAX_CHUNKS")
    file_review_chunk_char_limit: int = Field(default=12000, alias="FILE_REVIEW_CHUNK_CHAR_LIMIT")
    file_review_chunk_overlap_chars: int = Field(default=500, alias="FILE_REVIEW_CHUNK_OVERLAP_CHARS")
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
    file_ocr_device: str = Field(default="inherit", alias="FILE_OCR_DEVICE")
    qwen3guard_enabled: bool = Field(default=True, alias="QWEN3GUARD_ENABLED")
    qwen3guard_model: str = Field(default=DEFAULT_QWEN3GUARD_MODEL, alias="QWEN3GUARD_MODEL")
    qwen3guard_model_path: str = Field(default="", alias="QWEN3GUARD_MODEL_PATH")
    qwen3guard_device: str = Field(default="inherit", alias="QWEN3GUARD_DEVICE")
    qwen3guard_max_new_tokens: int = Field(default=48, alias="QWEN3GUARD_MAX_NEW_TOKENS")
    qwen3guard_timeout_ms: int = Field(default=1200, alias="QWEN3GUARD_TIMEOUT_MS")
    qwen3guard_workers: int = Field(default=1, alias="QWEN3GUARD_WORKERS")

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
