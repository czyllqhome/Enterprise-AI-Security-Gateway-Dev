import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models.system_setting import SystemSetting

INPUT_SCANNER_IDS = (
    "bancode",
    "prompt_injection",
    "ban_topics",
    "privacy_filter",
    "business_sensitive",
    "custom_regex",
)

BUSINESS_SENSITIVE_PROVIDER_IDS = ("ollama", "qwen", "bedrock")
FILE_REVIEW_STORAGE_PROFILES = ("windows", "linux")


class SystemSettingService:
    FILE_REVIEW_STORAGE_PATH_KEY = "file_review.default_storage_path"
    FILE_REVIEW_ACTIVE_STORAGE_PROFILE_KEY = "file_review.active_storage_profile"
    FILE_REVIEW_WINDOWS_STORAGE_PATH_KEY = "file_review.windows_storage_path"
    FILE_REVIEW_LINUX_STORAGE_PATH_KEY = "file_review.linux_storage_path"
    FILE_REVIEW_PER_USER_SUBDIRECTORIES_KEY = "file_review.per_user_subdirectories"
    ENABLED_SCANNERS_KEY = "guardrail.enabled_scanners"
    SCANNER_STRICT_MODE_KEY = "guardrail.strict_mode"
    BUSINESS_SENSITIVE_PROVIDER_KEY = "business_sensitive.provider"
    BUSINESS_SENSITIVE_MODEL_KEY = "business_sensitive.model"

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def get_file_review_storage_path(self) -> str:
        return self.get_file_review_storage_path_for_profile(self.get_file_review_active_storage_profile())

    def get_file_review_active_storage_profile(self) -> str:
        record = self._get(self.FILE_REVIEW_ACTIVE_STORAGE_PROFILE_KEY)
        configured = record.value if record is not None else self.settings.file_review_active_storage_profile
        return self._normalize_file_review_storage_profile(configured)

    def get_file_review_storage_path_for_profile(self, profile: str) -> str:
        normalized_profile = self._normalize_file_review_storage_profile(profile)
        if normalized_profile == "windows":
            record = self._get(self.FILE_REVIEW_WINDOWS_STORAGE_PATH_KEY)
            configured = record.value if record is not None else self.settings.file_review_windows_storage_path
            if configured.strip():
                return configured.strip()
            return self._legacy_file_review_storage_path()

        record = self._get(self.FILE_REVIEW_LINUX_STORAGE_PATH_KEY)
        configured = record.value if record is not None else self.settings.file_review_linux_storage_path
        if configured.strip():
            return configured.strip()
        return self._legacy_file_review_storage_path()

    def get_file_review_per_user_subdirectories(self) -> bool:
        record = self._get(self.FILE_REVIEW_PER_USER_SUBDIRECTORIES_KEY)
        if record is None:
            return self.settings.file_review_per_user_storage_dirs
        return record.value.strip().lower() in {"1", "true", "yes", "on"}

    def set_file_review_storage_settings(
        self,
        *,
        active_storage_profile: str,
        windows_storage_path: str,
        linux_storage_path: str,
        per_user_subdirectories: bool,
    ) -> dict[str, str | bool]:
        normalized_profile = self._normalize_file_review_storage_profile(active_storage_profile)
        normalized_windows_path = windows_storage_path.strip()
        normalized_linux_path = linux_storage_path.strip()
        if not normalized_windows_path:
            raise ValueError("Windows storage path cannot be empty.")
        if not normalized_linux_path:
            raise ValueError("Linux storage path cannot be empty.")

        self._set(self.FILE_REVIEW_ACTIVE_STORAGE_PROFILE_KEY, normalized_profile)
        self._set(self.FILE_REVIEW_WINDOWS_STORAGE_PATH_KEY, normalized_windows_path)
        self._set(self.FILE_REVIEW_LINUX_STORAGE_PATH_KEY, normalized_linux_path)
        self._set(self.FILE_REVIEW_PER_USER_SUBDIRECTORIES_KEY, json.dumps(per_user_subdirectories))
        self.db.commit()
        return {
            "active_storage_profile": normalized_profile,
            "windows_storage_path": normalized_windows_path,
            "linux_storage_path": normalized_linux_path,
            "per_user_subdirectories": per_user_subdirectories,
        }

    def _legacy_file_review_storage_path(self) -> str:
        record = self._get(self.FILE_REVIEW_STORAGE_PATH_KEY)
        if record and record.value.strip():
            return record.value.strip()
        return self.settings.file_review_default_storage_path

    def set_file_review_storage_path(self, path: str) -> str:
        normalized = path.strip()
        self._set(self.FILE_REVIEW_STORAGE_PATH_KEY, normalized)
        self.db.commit()
        return normalized

    def get_enabled_scanners(self) -> list[str]:
        record = self._get(self.ENABLED_SCANNERS_KEY)
        if record is None or not record.value.strip():
            return list(INPUT_SCANNER_IDS)

        try:
            parsed = json.loads(record.value)
        except json.JSONDecodeError:
            return list(INPUT_SCANNER_IDS)

        if not isinstance(parsed, list):
            return list(INPUT_SCANNER_IDS)

        scanner_ids = [str(item) for item in parsed]
        try:
            return self.validate_enabled_scanners(scanner_ids)
        except ValueError:
            return list(INPUT_SCANNER_IDS)

    def set_enabled_scanners(self, scanner_ids: list[str]) -> list[str]:
        validated = self.validate_enabled_scanners(scanner_ids)
        self._set(self.ENABLED_SCANNERS_KEY, json.dumps(validated))
        self.db.commit()
        return validated

    def get_scanner_strict_mode(self) -> bool:
        record = self._get(self.SCANNER_STRICT_MODE_KEY)
        if record is None:
            return self.settings.scanner_strict_mode
        return record.value.strip().lower() in {"1", "true", "yes", "on"}

    def set_scanner_strict_mode(self, enabled: bool) -> bool:
        self._set(self.SCANNER_STRICT_MODE_KEY, json.dumps(enabled))
        self.db.commit()
        return enabled

    def get_business_sensitive_config(self) -> dict[str, str]:
        provider_record = self._get(self.BUSINESS_SENSITIVE_PROVIDER_KEY)
        provider = self._normalize_business_sensitive_provider(
            provider_record.value if provider_record is not None else self.settings.business_sensitive_provider
        )

        model_record = self._get(self.BUSINESS_SENSITIVE_MODEL_KEY)
        model = (model_record.value if model_record is not None else "").strip()
        if not model:
            model = self.get_default_business_sensitive_model(provider)

        return {"provider": provider, "model": model}

    def set_business_sensitive_config(self, provider: str, model: str | None = None) -> dict[str, str]:
        normalized_provider = self._normalize_business_sensitive_provider(provider)
        normalized_model = (model or "").strip() or self.get_default_business_sensitive_model(normalized_provider)
        self._set(self.BUSINESS_SENSITIVE_PROVIDER_KEY, normalized_provider)
        self._set(self.BUSINESS_SENSITIVE_MODEL_KEY, normalized_model)
        self.db.commit()
        return {"provider": normalized_provider, "model": normalized_model}

    def get_business_sensitive_options(self) -> list[dict[str, str]]:
        return [
            {
                "provider": "ollama",
                "model": self.get_default_business_sensitive_model("ollama"),
                "label": "Ollama / qwen3.5:4b",
                "description": "Local Ollama scanner runtime.",
            },
            {
                "provider": "qwen",
                "model": self.get_default_business_sensitive_model("qwen"),
                "label": "阿里云百炼 / deepseek-v4-flash",
                "description": "OpenAI-compatible DashScope scanner runtime.",
            },
            {
                "provider": "bedrock",
                "model": self.get_default_business_sensitive_model("bedrock"),
                "label": "AWS Bedrock",
                "description": "Amazon Bedrock Converse API scanner runtime.",
            },
        ]

    def get_default_business_sensitive_model(self, provider: str) -> str:
        normalized_provider = self._normalize_business_sensitive_provider(provider)
        if normalized_provider == "qwen":
            return self.settings.business_sensitive_qwen_model or "deepseek-v4-flash"
        if normalized_provider == "bedrock":
            return self.settings.business_sensitive_bedrock_model or self.settings.bedrock_default_model
        return self.settings.business_sensitive_model or "qwen3.5:4b"

    def validate_enabled_scanners(self, scanner_ids: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        allowed = set(INPUT_SCANNER_IDS)
        for scanner_id in scanner_ids:
            value = str(scanner_id).strip()
            if value not in allowed:
                raise ValueError(f"Unknown scanner id: {value}")
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _normalize_business_sensitive_provider(self, provider: str) -> str:
        value = (provider or "").strip().lower()
        if value not in BUSINESS_SENSITIVE_PROVIDER_IDS:
            raise ValueError(f"Unknown business-sensitive provider: {provider}")
        return value

    def _normalize_file_review_storage_profile(self, profile: str) -> str:
        value = (profile or "").strip().lower()
        if value not in FILE_REVIEW_STORAGE_PROFILES:
            raise ValueError(f"Unknown file storage profile: {profile}")
        return value

    def _set(self, key: str, value: str) -> SystemSetting:
        record = self._get(key)
        if record is None:
            record = SystemSetting(key=key, value=value)
            self.db.add(record)
        else:
            record.value = value
        return record

    def _get(self, key: str) -> SystemSetting | None:
        return self.db.scalar(select(SystemSetting).where(SystemSetting.key == key))
