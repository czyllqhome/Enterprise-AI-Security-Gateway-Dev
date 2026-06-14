from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal
from urllib import error, request

from pydantic import BaseModel, Field, ValidationError

from ...core.config import get_settings

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
    "- contract_terms: 合同条款、付款条件、违约责任、交付条件",
    "- pricing: 价格、报价、折扣、成本、预算金额",
    "- product_spec: 内部产品编号、料号、规格、未公开参数",
    "- commercial_plan: 投标方案、销售策略、客户拓展计划、内部商务决策",
    "- customer_data: 客户名单、商务联系人、采购意向",
    "- insurance_policy_terms: 保险合同条款、保单号、合同编号、特别约定、责任免除、等待期、续保/退保条款",
    "- insurance_coverage: 保险责任、保障范围、保额、免赔额、赔付比例、保险期间、承保区域",
    "- insurance_premium: 保费、费率、折扣、缴费方式、缴费周期、应收/实收保费、佣金或手续费",
    "- insurance_claims: 理赔条件、赔付金额、出险信息、赔案号、理赔进度、拒赔原因、赔付记录",
    "- insurance_underwriting: 核保结论、风险评级、健康/职业/车辆风险因素、承保限制、加费或除外责任",
    "- insurance_party_data: 投保人、被保险人、受益人、保单联系人、代理人/经纪人、企业客户等保险合同相关方信息",
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
class OllamaGenerateResponse:
    raw_text: str
    model: str
    thinking_text: str = ""


class OllamaClient:
    def __init__(self, *, base_url: str, timeout_seconds: float, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.model = model

    def generate(self, prompt: str) -> OllamaGenerateResponse:
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

        return OllamaGenerateResponse(
            raw_text=str(data.get("response", "") or ""),
            model=str(data.get("model", self.model) or self.model),
            thinking_text=str(data.get("thinking", "") or ""),
        )


class BusinessSensitiveScanner:
    SCANNER_NAME = "Business Sensitive"

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.business_sensitive_enabled
        self.model = settings.business_sensitive_model or "qwen3.5:4b"
        self.timeout_seconds = settings.business_sensitive_timeout_seconds
        self.provider = "ollama"
        self.client = OllamaClient(
            base_url=settings.business_sensitive_ollama_url,
            timeout_seconds=self.timeout_seconds,
            model=self.model,
        )

    def scan(self, text: str) -> BusinessSensitiveResult:
        candidate = (text or "").strip()
        if not candidate or not self.enabled:
            return self.fallback_result()

        prompt = self._build_prompt(candidate)
        try:
            response = self.client.generate(prompt)
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
            return self.fallback_result(summary="商务敏感扫描失败，已使用安全兜底结果。")

    def _build_prompt(self, text: str) -> str:
        categories = "\n".join(BUSINESS_CATEGORY_DESCRIPTIONS)
        return (
            "你是一个商务敏感信息分类器。\n"
            "请阅读用户文本，并且只返回一个符合响应 schema 的 JSON 对象。\n"
            "规则：\n"
            "1. 只能输出合法 JSON，不能输出 markdown、解释说明或代码块。\n"
            "2. categories[].name 必须且只能使用允许的英文枚举值。\n"
            "3. summary、reason、matched_text 必须默认使用简体中文表述。\n"
            "4. confidence 必须在 0 到 1 之间。\n"
            "5. 如果没有商务敏感信息，返回 contains_business_sensitive=false、risk_level=low、空 categories、简短中文 summary、低 confidence。\n"
            "6. 不要把个人简历、个人联系方式整理、个人身份/联系方式脱敏等非商业个人资料请求判定为商务敏感。\n"
            "7. customer_data 必须具有明确商业语境，例如企业客户、销售线索、采购、报价、投标、合同、预算或内部商务运营。\n"
            "8. 个人姓名、手机号、邮箱、身份证号、银行卡等在简历/Profile 场景中属于隐私敏感，但不属于商务敏感。\n"
            "允许的类别：\n"
            f"{categories}\n"
            "用户文本：\n"
            f"{text}"
        )

    def _parse_result(self, response: OllamaGenerateResponse) -> BusinessSensitiveResult:
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
    def fallback_result(cls, *, summary: str = "商务敏感扫描当前不可用。") -> BusinessSensitiveResult:
        return BusinessSensitiveResult(
            contains_business_sensitive=False,
            risk_level="low",
            categories=[],
            summary=summary,
            confidence=0.0,
        )
