from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal
from urllib import error, request

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ..provider_credential_service import ProviderCredentialNotFoundError, ProviderCredentialService

logger = logging.getLogger(__name__)

BUSINESS_SENSITIVE_CATEGORIES = (
    "contract_terms",
    "pricing",
    "product_spec",
    "commercial_plan",
    "customer_data",
    "insurance_policy_terms",
    "insurance_coverage",
    "insurance_premium",
    "insurance_claims",
    "insurance_underwriting",
    "insurance_party_data",
)
BUSINESS_CATEGORY_DESCRIPTIONS = (
    "- contract_terms: contract terms, payment terms, breach liability, delivery terms",
    "- pricing: price, quote, discount, cost, budget amount",
    "- product_spec: internal product code, material number, unpublished specifications or parameters",
    "- commercial_plan: bid plan, sales strategy, customer expansion plan, internal commercial decision",
    "- customer_data: customer list, business contact, procurement intent",
    "- insurance_policy_terms: policy terms, policy number, contract number, exclusions, waiting period, renewal or surrender terms",
    "- insurance_coverage: insurance liability, coverage scope, sum insured, deductible, compensation ratio, policy period, underwriting region",
    "- insurance_premium: premium, rate, discount, payment method, payment period, receivables, paid premium, commission or fees",
    "- insurance_claims: claim conditions, claim amount, incident information, claim number, claim progress, denial reason, payout record",
    "- insurance_underwriting: underwriting conclusion, risk rating, health/occupation/vehicle risk factors, coverage limits, surcharges or exclusions",
    "- insurance_party_data: policyholder, insured, beneficiary, policy contact, agent/broker, enterprise customer data",
)
BusinessSensitiveCategoryName = Literal[
    "contract_terms",
    "pricing",
    "product_spec",
    "commercial_plan",
    "customer_data",
    "insurance_policy_terms",
    "insurance_coverage",
    "insurance_premium",
    "insurance_claims",
    "insurance_underwriting",
    "insurance_party_data",
]
BusinessSensitiveRiskLevel = Literal["low", "medium", "high"]
BusinessSensitiveProvider = Literal["ollama", "qwen", "bedrock"]


class BusinessSensitiveCategory(BaseModel):
    name: BusinessSensitiveCategoryName
    matched_text: str = ""
    reason: str = ""


class BusinessSensitiveResult(BaseModel):
    contains_business_sensitive: bool = False
    risk_level: BusinessSensitiveRiskLevel = "low"
    categories: list[BusinessSensitiveCategory] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class ModelGenerateResponse:
    raw_text: str
    model: str
    thinking_text: str = ""


@dataclass(slots=True)
class BusinessSensitiveRuntimeConfig:
    provider: BusinessSensitiveProvider
    model: str
    base_url: str
    api_key: str = ""
    display_name: str = ""


class OllamaClient:
    def __init__(self, *, base_url: str, timeout_seconds: float, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.model = model

    def generate(self, prompt: str) -> ModelGenerateResponse:
        json_schema = BusinessSensitiveResult.model_json_schema()
        no_think_prompt = (
            "/no_think\n"
            "Do not use thinking mode. Do not output internal reasoning or <think> blocks. "
            "Return only the requested JSON object.\n\n"
            f"{prompt}"
        )
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": no_think_prompt,
                "stream": False,
                "format": json_schema,
                "think": False,
                "options": {
                    "temperature": 0,
                    "top_p": 0.1,
                    "repeat_penalty": 1.0,
                    "num_predict": 512,
                },
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.URLError as exc:
            logger.warning("BusinessSensitive Ollama request failed. reason=%s", exc)
            raise

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.warning("BusinessSensitive Ollama envelope JSON decode failed. reason=%s", exc)
            raise

        return ModelGenerateResponse(
            raw_text=str(data.get("response", "") or ""),
            model=str(data.get("model", self.model) or self.model),
            thinking_text=str(data.get("thinking", "") or ""),
        )


class OpenAICompatibleBusinessSensitiveClient:
    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float, model: str, provider_label: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.provider_label = provider_label

    def generate(self, prompt: str) -> ModelGenerateResponse:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a business-sensitive information classifier. "
                            "Return only one valid JSON object and no markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "top_p": 0.1,
                "max_tokens": 512,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.warning("BusinessSensitive %s request rejected. detail=%s", self.provider_label, detail or exc.reason)
            raise
        except error.URLError as exc:
            logger.warning("BusinessSensitive %s request failed. reason=%s", self.provider_label, exc)
            raise

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.warning("BusinessSensitive %s envelope JSON decode failed. reason=%s", self.provider_label, exc)
            raise

        choices = data.get("choices") or []
        message = choices[0].get("message") if choices else {}
        return ModelGenerateResponse(
            raw_text=str((message or {}).get("content", "") or ""),
            model=str(data.get("model", self.model) or self.model),
        )


class BedrockBusinessSensitiveClient:
    def __init__(self, *, region_name: str, timeout_seconds: float, model: str) -> None:
        self.region_name = region_name
        self.timeout_seconds = timeout_seconds
        self.model = model
        settings = get_settings()
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import BotoCoreError, ClientError

            session_kwargs = {}
            if settings.bedrock_profile_name.strip():
                session_kwargs["profile_name"] = settings.bedrock_profile_name.strip()
            self._boto_core_error = BotoCoreError
            self._client_error = ClientError
            session = boto3.Session(**session_kwargs)
            self.client = session.client(
                "bedrock-runtime",
                region_name=region_name,
                config=Config(
                    connect_timeout=timeout_seconds,
                    read_timeout=timeout_seconds,
                    retries={"max_attempts": 2},
                ),
            )
        except Exception as exc:
            logger.warning("BusinessSensitive Bedrock client initialization failed. reason=%s", exc)
            raise

    def generate(self, prompt: str) -> ModelGenerateResponse:
        try:
            response = self.client.converse(
                modelId=self.model,
                system=[
                    {
                        "text": (
                            "You are a business-sensitive information classifier. "
                            "Return only one valid JSON object and no markdown."
                        ),
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                inferenceConfig={
                    "temperature": 0,
                    "topP": 0.1,
                    "maxTokens": 512,
                },
            )
        except self._client_error as exc:
            detail = exc.response.get("Error", {}).get("Message") or str(exc)
            logger.warning("BusinessSensitive Bedrock request rejected. detail=%s", detail)
            raise
        except self._boto_core_error as exc:
            logger.warning("BusinessSensitive Bedrock request failed. reason=%s", exc)
            raise

        message = ((response.get("output") or {}).get("message") or {})
        blocks = message.get("content") or []
        raw_text = "\n".join(
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("text")
        )
        return ModelGenerateResponse(raw_text=raw_text, model=self.model)


class BusinessSensitiveScanner:
    SCANNER_NAME = "Business Sensitive"

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.business_sensitive_enabled
        self.timeout_seconds = settings.business_sensitive_timeout_seconds
        self.provider = self._normalize_provider(settings.business_sensitive_provider)
        self.model = self._default_model_for_provider(self.provider)

    def scan(self, text: str, db: Session | None = None) -> BusinessSensitiveResult:
        candidate = (text or "").strip()
        if not candidate or not self.enabled:
            return self.fallback_result()

        prompt = self._build_prompt(candidate)
        try:
            runtime = self._resolve_runtime_config(db)
            self.provider = runtime.provider
            self.model = runtime.model
            response = self._build_client(runtime).generate(prompt)
            parsed = self._parse_result(response)
            normalized = self._normalize_result(parsed)
            if normalized.contains_business_sensitive:
                self._log_hit(normalized)
            return normalized
        except Exception as exc:
            logger.warning(
                "BusinessSensitive scanner failed; using safe fallback. model=%s reason=%s",
                f"{self.provider}/{self.model}",
                exc,
            )
            return self.fallback_result(summary="Business-sensitive scan failed; safe fallback result was used.")

    def is_runtime_available(self, db: Session | None = None) -> bool:
        if not self.enabled:
            return False
        try:
            runtime = self._resolve_runtime_config(db)
        except Exception:
            return False
        return bool(runtime.provider in {"ollama", "bedrock"} or runtime.api_key)

    def describe_runtime(self, db: Session | None = None) -> str:
        try:
            runtime = self._resolve_runtime_config(db)
        except Exception as exc:
            return f"Business-sensitive scanner runtime is not configured: {exc}"

        if runtime.provider == "qwen":
            configured = "configured" if runtime.api_key else "missing API key"
            return (
                f"Model: Aliyun Bailian {runtime.model}. "
                f"Base URL: {runtime.base_url}. API key: {configured}. "
                "Structured JSON is validated with safe fallback behavior."
            )
        if runtime.provider == "bedrock":
            return (
                f"Model: AWS Bedrock {runtime.model}. "
                f"Region: {get_settings().bedrock_region}. "
                "AWS credentials are resolved through the default SDK credential chain. "
                "Structured JSON is validated with safe fallback behavior."
            )
        return (
            f"Model: local Ollama {runtime.model}. "
            f"Base URL: {runtime.base_url}. "
            "Structured JSON is validated with safe fallback behavior."
        )

    def _build_prompt(self, text: str) -> str:
        categories = "\n".join(BUSINESS_CATEGORY_DESCRIPTIONS)
        schema = BusinessSensitiveResult.model_json_schema()
        return (
            "You are a business-sensitive information classifier.\n"
            "Read the user text and return exactly one JSON object matching this schema:\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n\n"
            "Rules:\n"
            "1. Output valid JSON only. Do not output markdown, explanations, or code fences.\n"
            "2. categories[].name must use only the allowed enum values.\n"
            "3. summary, reason, and matched_text should use Simplified Chinese by default.\n"
            "4. confidence must be between 0 and 1.\n"
            "5. If no business-sensitive content is present, return contains_business_sensitive=false, "
            "risk_level=low, empty categories, a short Chinese summary, and low confidence.\n"
            "6. Do not classify personal resumes, personal contact cleanup, or ordinary PII/profile requests "
            "as business-sensitive unless they also contain clear commercial context.\n"
            "7. customer_data requires explicit business context such as enterprise customers, sales leads, "
            "procurement, quotation, bidding, contract, budget, or internal commercial operations.\n\n"
            "Allowed categories:\n"
            f"{categories}\n\n"
            "User text:\n"
            f"{text}"
        )

    def _resolve_runtime_config(self, db: Session | None = None) -> BusinessSensitiveRuntimeConfig:
        settings = get_settings()
        provider = self._normalize_provider(settings.business_sensitive_provider)
        model = self._default_model_for_provider(provider)

        if db is not None:
            from ..system_setting_service import SystemSettingService

            stored = SystemSettingService(db).get_business_sensitive_config()
            provider = self._normalize_provider(stored["provider"])
            model = stored["model"] or self._default_model_for_provider(provider)

        if provider == "qwen":
            api_key = settings.business_sensitive_qwen_api_key
            base_url = settings.business_sensitive_qwen_base_url
            display_name = "Aliyun Bailian"
            if db is not None:
                try:
                    credential = ProviderCredentialService(db).require_credential("qwen")
                    api_key = credential.api_key or api_key
                    base_url = credential.base_url or base_url
                    display_name = credential.display_name or display_name
                except ProviderCredentialNotFoundError:
                    pass
            if not api_key:
                raise ValueError("Aliyun Bailian API key is not configured.")
            return BusinessSensitiveRuntimeConfig(
                provider="qwen",
                model=model or settings.business_sensitive_qwen_model or "deepseek-v4-flash",
                base_url=base_url,
                api_key=api_key,
                display_name=display_name,
            )

        if provider == "bedrock":
            return BusinessSensitiveRuntimeConfig(
                provider="bedrock",
                model=model or settings.business_sensitive_bedrock_model or settings.bedrock_default_model,
                base_url=f"bedrock-runtime.{settings.bedrock_region}.amazonaws.com",
                display_name="AWS Bedrock",
            )

        return BusinessSensitiveRuntimeConfig(
            provider="ollama",
            model=model or settings.business_sensitive_model or "qwen3.5:4b",
            base_url=settings.business_sensitive_ollama_url,
            display_name="Ollama",
        )

    def _build_client(self, runtime: BusinessSensitiveRuntimeConfig):
        if runtime.provider == "qwen":
            return OpenAICompatibleBusinessSensitiveClient(
                api_key=runtime.api_key,
                base_url=runtime.base_url,
                timeout_seconds=self.timeout_seconds,
                model=runtime.model,
                provider_label=runtime.display_name or "Aliyun Bailian",
            )
        if runtime.provider == "bedrock":
            return BedrockBusinessSensitiveClient(
                region_name=get_settings().bedrock_region,
                timeout_seconds=self.timeout_seconds,
                model=runtime.model,
            )
        return OllamaClient(
            base_url=runtime.base_url,
            timeout_seconds=self.timeout_seconds,
            model=runtime.model,
        )

    def _normalize_provider(self, provider: str) -> BusinessSensitiveProvider:
        value = (provider or "").strip().lower()
        if value == "qwen":
            return "qwen"
        if value == "bedrock":
            return "bedrock"
        return "ollama"

    def _default_model_for_provider(self, provider: BusinessSensitiveProvider) -> str:
        settings = get_settings()
        if provider == "qwen":
            return settings.business_sensitive_qwen_model or "deepseek-v4-flash"
        if provider == "bedrock":
            return settings.business_sensitive_bedrock_model or settings.bedrock_default_model
        return settings.business_sensitive_model or "qwen3.5:4b"

    def _parse_result(self, response: ModelGenerateResponse) -> BusinessSensitiveResult:
        payload = self._extract_json_object(response.raw_text)
        if payload is None:
            logger.warning(
                "BusinessSensitive scanner could not extract JSON body from model output. response=%r thinking=%r",
                response.raw_text[:500],
                response.thinking_text[:500],
            )
            raise ValueError("missing-json-body")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("BusinessSensitive scanner JSON decode failed. reason=%s raw=%r", exc, payload[:500])
            raise
        try:
            return BusinessSensitiveResult.model_validate(data)
        except ValidationError as exc:
            logger.warning("BusinessSensitive scanner schema validation failed. reason=%s data=%r", exc, data)
            raise

    def _normalize_result(self, result: BusinessSensitiveResult) -> BusinessSensitiveResult:
        categories = [
            category
            for category in result.categories
            if category.name in BUSINESS_SENSITIVE_CATEGORIES
        ]
        contains = bool(result.contains_business_sensitive or categories)
        risk_level: BusinessSensitiveRiskLevel = result.risk_level
        if contains and risk_level == "low":
            risk_level = "medium"
        if not contains:
            risk_level = "low"
        confidence = min(max(float(result.confidence), 0.0), 1.0)
        summary = (result.summary or "").strip()
        if not summary:
            summary = "检测到商务敏感内容。" if contains else "未检测到商务敏感内容。"
        if contains and summary.lower() in {
            "no business-sensitive content detected.",
            "no business sensitive content detected.",
            "no commercial sensitive content detected.",
        }:
            summary = "检测到商务敏感内容。"
        return BusinessSensitiveResult(
            contains_business_sensitive=contains,
            risk_level=risk_level,
            categories=categories,
            summary=summary,
            confidence=confidence,
        )

    def _extract_json_object(self, raw_text: str) -> str | None:
        candidate = (raw_text or "").strip()
        if not candidate:
            return None
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return candidate[start : end + 1]

    def _log_hit(self, result: BusinessSensitiveResult) -> None:
        examples = ", ".join(
            filter(
                None,
                [
                    f"{category.name}:{category.matched_text[:40]}"
                    for category in result.categories[:3]
                ],
            )
        )
        logger.warning(
            "BusinessSensitive scanner detected commercial sensitive content. risk=%s confidence=%.3f examples=%s summary=%s",
            result.risk_level,
            result.confidence,
            examples or "n/a",
            result.summary,
        )

    @classmethod
    def fallback_result(cls, *, summary: str = "Business-sensitive scanner is currently unavailable.") -> BusinessSensitiveResult:
        return BusinessSensitiveResult(
            contains_business_sensitive=False,
            risk_level="low",
            categories=[],
            summary=summary,
            confidence=0.0,
        )
