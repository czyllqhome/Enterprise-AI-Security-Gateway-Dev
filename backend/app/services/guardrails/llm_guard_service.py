from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from ...core.model_cache import configure_local_model_cache
from ...schemas.guardrail import GuardrailEntity, GuardrailScanResult
from ..system_setting_service import INPUT_SCANNER_IDS
from .business_sensitive_scanner import BusinessSensitiveScanner
from .chinese_patterns import CUSTOM_PATTERNS
from .entity_normalizer import normalize_entities
from .privacy_filter_scanner import (
    PRIVACY_FILTER_SCANNER_NAME,
    PRIVACY_FILTER_SOURCE,
    PrivacyFilterScanner,
)
from .qwen3guard_scanner import Qwen3GuardModerationResult, Qwen3GuardScanner

logger = logging.getLogger(__name__)

LOCAL_MODEL_CACHE_ROOT = configure_local_model_cache()
_GUARDRAIL_SERVICE_LOCK = threading.Lock()
_GUARDRAIL_SERVICE_SINGLETON: "GuardrailService | None" = None

try:
    from llm_guard.input_scanners import BanCode
    from llm_guard.input_scanners.ban_code import MODEL_SM as BANCODE_MODEL_SM
    from llm_guard.output_scanners.deanonymize import Deanonymize
    from llm_guard.vault import Vault
except Exception:  # pragma: no cover
    BanCode = None
    BANCODE_MODEL_SM = None
    Deanonymize = None
    Vault = None


PROXY_ENV_VARS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
]
HUGGINGFACE_OFFLINE_ENV_VARS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}

SOURCE_CODE_FENCE_RE = re.compile(r"```[\w+-]*\s*\n[\s\S]+?\n```", re.MULTILINE)
SOURCE_CODE_LINE_PATTERNS = [
    re.compile(r"^\s*(def|class|import|from)\s+\w+", re.MULTILINE),
    re.compile(r"^\s*return\s+.+", re.MULTILINE),
    re.compile(r"^\s*self\.\w+\s*=\s*.+", re.MULTILINE),
    re.compile(r"^\s*(const|let|var|function)\s+\w+", re.MULTILINE),
    re.compile(r"^\s*(public|private|protected|static)\s+\w+", re.MULTILINE),
    re.compile(r"^\s*if\s*\(.+\)\s*\{", re.MULTILINE),
    re.compile(r"^\s*\w+\s*=\s*['\"{\[].+", re.MULTILINE),
]
SOURCE_CODE_INLINE_RE = re.compile(
    r"(def\s+\w+\s*\(|class\s+\w+|import\s+\w+|from\s+\w+\s+import\s+\w+|return\s+.+|self\.\w+\s*=|=>|`\s*(def|class|import|from)\b|\{\s*\n)",
    re.MULTILINE,
)
SOURCE_CODE_CONTEXT_RE = re.compile(
    r"(```|`\s*(def|class|import|from)\b|^\s*(def|class|import|from|const|let|var|function)\b|=>|;\s*$|^\s*return\b|^\s*self\.\w+\s*=.+|^\s*\w+\s*=\s*['\"{\[].+)",
    re.MULTILINE,
)
BUSINESS_ANCHOR_RE = re.compile(
    r"\b("
    r"customer|customers|client|clients|account|accounts|prospect|prospects|lead|leads|"
    r"quotation|quote|quoted|pricing|price|discount|budget|cost|tender|bid|bidding|"
    r"contract|payment terms|delivery terms|sales strategy|procurement|vendor|supplier|"
    r"crm|pipeline|deal desk|commercial approval|commercial plan|customer list|client list|"
    r"procurement intent|bid proposal|internal product code|unpublished parameters|"
    r"pricing approval|discount approval|commercial decision"
    r")\b|"
    r"(客户|客户名单|联系人|采购意向|投标|招标|报价|折扣|预算|成本|合同|付款条件|交付条件|"
    r"销售策略|商务决策|内部产品编号|料号|未公开参数)",
    re.IGNORECASE,
)
PERSONAL_PROFILE_CONTEXT_RE = re.compile(
    r"\b("
    r"resume|cv|curriculum vitae|profile|bio|biography|personal profile|contact card|"
    r"organize these contacts|organize my contacts|make me an? easy resume|make me a resume|"
    r"my name is|my id is|my phone number is|email is|about me|"
    r"personal resume|personal contact summary|personal details|my profile|my contact info"
    r")\b|"
    r"(简历|个人简历|个人资料|个人信息|联系方式|帮我写简历|生成简历|我的姓名是|"
    r"我的身份证是|我的手机号是|我的邮箱是)",
    re.IGNORECASE,
)
PERSONAL_PII_ENTITY_TYPES = {
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CN_MOBILE_NUMBER",
    "CHINESE_ID",
    "CN_ID_CARD",
    "ADDRESS",
    "BANK_CARD",
    "CREDIT_CARD",
    "CREDIT_CARD_RE",
    "US_SSN",
    "US_SSN_RE",
}
PII_ONLY_EXEMPT_BUSINESS_CATEGORIES = {"customer_data", "commercial_plan"}
BUSINESS_SENSITIVE_BLOCK_RISK_LEVELS = {"high"}
WEAPONS_HINT_RE = re.compile(r"\b(bomb|explosive|detonator|gunpowder|pipe bomb|weapon|firearm|ammo)\b|(炸弹|爆炸物|雷管|火药|枪支|枪械|弹药|武器)", re.IGNORECASE)
VIOLENT_GUIDANCE_HINT_RE = re.compile(r"\b(how to|teach me|explain|guide|build|make)\b|(怎么|教我|教程|指导|制作|做个)", re.IGNORECASE)
SELF_HARM_HINT_RE = re.compile(r"\b(suicide|self-harm|kill myself|overdose|cut myself)\b|(自杀|自残|轻生|割腕|服毒)", re.IGNORECASE)
FINANCIAL_FRAUD_HINT_RE = re.compile(r"\b(phishing|fraud|money laundering|wire fraud|scam|credit card fraud)\b|(钓鱼诈骗|信用卡诈骗|洗钱|电信诈骗|骗取钱财)", re.IGNORECASE)
HR_DISCRIMINATION_HINT_RE = re.compile(r"\b(hiring|candidate|candidates|employee|employees|pregnant|older workers|elderly|disabled applicants|workplace|interviews?)\b|(招聘|录用|候选人|员工|孕妇|老年人|年龄大的候选人|残障人士|职场|面试)", re.IGNORECASE)
HARASSMENT_HINT_RE = re.compile(r"\b(harass|harassment|bully|threaten|stalk|intimidate)\b|(骚扰|胁迫|恐吓|长期跟踪|霸凌|威胁)", re.IGNORECASE)
DISCRIMINATION_HINT_RE = re.compile(r"\b(discrimination|discriminatory|hate speech|racial hatred|slur|exclude)\b|(歧视|仇恨言论|辱骂|排斥|种族歧视|性别歧视)", re.IGNORECASE)


def _is_loopback_proxy(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


@contextmanager
def _without_broken_loopback_proxies():
    original_values: dict[str, str] = {}
    try:
        for key in PROXY_ENV_VARS:
            value = os.environ.get(key)
            if _is_loopback_proxy(value):
                original_values[key] = value
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in original_values.items():
            os.environ[key] = value


@contextmanager
def _offline_huggingface_access():
    original_values: dict[str, str | None] = {}
    try:
        for key, value in HUGGINGFACE_OFFLINE_ENV_VARS.items():
            original_values[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _resolve_cached_hf_snapshot(repo_id: str, *, root: Path) -> str | None:
    owner, _, model_name = repo_id.partition("/")
    if not owner or not model_name:
        return None

    cache_candidates = [
        root / "huggingface" / "hub" / f"models--{owner}--{model_name}",
        root / "transformers" / f"models--{owner}--{model_name}",
    ]
    for cache_dir in cache_candidates:
        snapshots_dir = cache_dir / "snapshots"
        if not snapshots_dir.exists():
            continue
        for snapshot in sorted(snapshots_dir.iterdir(), reverse=True):
            if snapshot.is_dir() and (snapshot / "config.json").exists():
                return str(snapshot)
    return None


def _build_local_bancode_model(model: Any | None) -> Any | None:
    if model is None:
        return None

    path = _resolve_cached_hf_snapshot(getattr(model, "path", ""), root=LOCAL_MODEL_CACHE_ROOT)
    onnx_path = _resolve_cached_hf_snapshot(getattr(model, "onnx_path", ""), root=LOCAL_MODEL_CACHE_ROOT)
    if path is None and onnx_path is None:
        return model

    return replace(
        model,
        path=path or model.path,
        onnx_path=onnx_path or model.onnx_path,
    )


class GuardrailService:
    def __init__(self) -> None:
        self._privacy_filter_scanner = self._build_privacy_filter_scanner()
        self._bancode_scanner = self._build_bancode_scanner()
        self._qwen3guard_scanner = self._build_qwen3guard_scanner()
        self._prompt_injection_scanner = self._qwen3guard_scanner
        self._ban_topics_scanner = self._qwen3guard_scanner
        self._business_sensitive_scanner = self._build_business_sensitive_scanner()

    def scan_text(self, text: str, enabled_scanners: list[str] | None = None) -> GuardrailScanResult:
        enabled = self._normalize_enabled_scanners(enabled_scanners)
        enabled_set = set(enabled)
        qwen3guard_moderation = None
        if enabled_set & {"prompt_injection", "ban_topics"}:
            qwen3guard_moderation = self._scan_with_qwen3guard(text)

        bancode_triggered = self._scan_with_bancode(text) if "bancode" in enabled_set else False
        prompt_injection_triggered = (
            self._scan_with_prompt_injection(text, qwen3guard_moderation)
            if "prompt_injection" in enabled_set
            else False
        )
        banned_topics = (
            self._scan_with_ban_topics(text, qwen3guard_moderation)
            if "ban_topics" in enabled_set
            else []
        )
        business_sensitive_result = (
            self._scan_with_business_sensitive(text)
            if "business_sensitive" in enabled_set
            else BusinessSensitiveScanner.fallback_result(summary="Business Sensitive scanner disabled.")
        )
        privacy_filter_matches = self._scan_with_privacy_filter(text) if "privacy_filter" in enabled_set else []
        privacy_filter_matches = self._reclassify_chinese_id_account_numbers(privacy_filter_matches)
        custom_matches = self._scan_with_custom_patterns(text) if "custom_regex" in enabled_set else []
        raw_entities = self._deduplicate_entities(privacy_filter_matches + custom_matches)
        raw_entities = self._merge_adjacent_phone_entities(raw_entities, text)
        entities = normalize_entities(raw_entities)
        business_sensitive_result = self._apply_business_sensitive_policy(text, entities, business_sensitive_result)
        sanitized_text = self._apply_replacements(text, entities)
        scanners: list[str] = []
        blocked_reason = None
        if bancode_triggered:
            scanners.append("BanCode")
            blocked_reason = self._append_blocked_reason(
                blocked_reason,
                "已拦截：检测到源代码或类似代码的内容。",
                "Blocked: Source code or code-like content was detected.",
            )
        if prompt_injection_triggered:
            scanners.append("PromptInjection")
            blocked_reason = self._append_blocked_reason(
                blocked_reason,
                "已拦截：检测到可能绕过系统规则或泄露隐藏指令的提示注入内容。",
                "Blocked: Possible prompt injection content was detected.",
            )
        if banned_topics:
            scanners.append("BanTopics")
            topics_text = ", ".join(banned_topics)
            blocked_reason = self._append_blocked_reason(
                blocked_reason,
                f"已拦截：检测到受限主题：{topics_text}。",
                f"Blocked: Restricted topics were detected: {topics_text}.",
            )
        if business_sensitive_result.contains_business_sensitive:
            scanners.append("Business Sensitive")
            if self._should_block_business_sensitive(business_sensitive_result):
                blocked_reason = self._append_blocked_reason(
                    blocked_reason,
                    f"已拦截：检测到商务敏感内容：{business_sensitive_result.summary}",
                    f"Blocked: Business-sensitive content was detected: {business_sensitive_result.summary}",
                )
        if privacy_filter_matches:
            scanners.append(PRIVACY_FILTER_SCANNER_NAME)
        if custom_matches:
            scanners.append("Custom Regex")
        business_sensitive_payload = (
            business_sensitive_result.model_dump()
            if hasattr(business_sensitive_result, "model_dump")
            else business_sensitive_result
        )
        return GuardrailScanResult(
            original_text=text,
            sanitized_text=sanitized_text,
            has_sensitive_data=bool(entities),
            entities=entities,
            bancode_triggered=bancode_triggered,
            prompt_injection_triggered=prompt_injection_triggered,
            ban_topics_triggered=bool(banned_topics),
            banned_topics=banned_topics,
            blocked_reason=blocked_reason,
            llm_guard_hit_count=0,
            secrets_hit_count=0,
            privacy_filter_hit_count=len(privacy_filter_matches),
            custom_regex_hit_count=len(custom_matches),
            scanners=scanners,
            enabled_scanners=enabled,
            entity_types=sorted({entity.type for entity in entities}),
            business_sensitive_result=business_sensitive_payload,
        )

    def _normalize_enabled_scanners(self, enabled_scanners: list[str] | None) -> list[str]:
        if enabled_scanners is None:
            return list(INPUT_SCANNER_IDS)
        allowed = set(INPUT_SCANNER_IDS)
        normalized: list[str] = []
        for scanner_id in enabled_scanners:
            value = str(scanner_id).strip()
            if value in allowed and value not in normalized:
                normalized.append(value)
        return normalized

    def _append_blocked_reason(self, current: str | None, chinese_reason: str, english_reason: str) -> str:
        reason = f"{chinese_reason}\n{english_reason}"
        return f"{current}\n{reason}".strip() if current else reason

    def get_scanner_availability(self) -> dict[str, bool]:
        return {
            "privacy_filter": self._privacy_filter_scanner is not None,
            "bancode": True,
            "prompt_injection": self._qwen3guard_scanner is not None,
            "ban_topics": self._qwen3guard_scanner is not None,
            "business_sensitive": self._business_sensitive_scanner is not None,
            "custom_regex": True,
            "deanonymize": Deanonymize is not None and Vault is not None,
        }

    def get_scanner_runtime_details(self) -> dict[str, str]:
        prompt_injection_model = getattr(self._qwen3guard_scanner, "model_reference", None) or "Qwen/Qwen3Guard-Gen-0.6B"
        bancode_model = self._get_model_path(self._bancode_scanner) or "LLM Guard BanCode heuristic fallback"
        ban_topics_model = getattr(self._qwen3guard_scanner, "model_reference", None) or "Qwen/Qwen3Guard-Gen-0.6B"
        privacy_filter_model = getattr(self._privacy_filter_scanner, "model_reference", None) or "local checkpoint unavailable"

        return {
            "BanCode": (
                "Model: "
                f"{bancode_model}. "
                "If the classifier is unavailable, heuristic source-code detection remains active."
            ),
            "PromptInjection": (
                "Model: "
                f"{prompt_injection_model}. "
                "Qwen3Guard local moderation flags jailbreak and prompt-injection attempts."
            ),
            "BanTopics": (
                "Model: "
                f"{ban_topics_model}. "
                "Qwen3Guard local moderation maps safety categories to project ban-topic labels."
            ),
            PRIVACY_FILTER_SCANNER_NAME: (
                "Model: Privacy Filter local checkpoint "
                f"{privacy_filter_model}. "
                "Detects PII and secrets across 8 labels; Custom Regex remains as the offline fallback."
            ),
            "Business Sensitive": (
                "Model: local Ollama "
                f"{getattr(self._business_sensitive_scanner, 'model', 'qwen3.5:4b')}. "
                "Structured JSON is validated with safe fallback behavior."
            ),
            "Custom Regex": (
                "Model: none. "
                "Chinese and English regex enhancement handles local patterns and credential phrases."
            ),
            "Deanonymize": (
                "Model: none. "
                "Placeholder restoration uses Vault mappings and local text replacement."
            ),
            "Sensitive Logging": (
                "Model: none. "
                "Triggered prompts are persisted to SQLite and the /log console."
            ),
        }

    def deanonymize_text(self, text: str, entities: list[dict] | None) -> str:
        if not text or not entities:
            return text

        replacements = [
            (entity["replacement"], entity["original"])
            for entity in entities
            if entity.get("replacement") and entity.get("original")
        ]
        if not replacements:
            return text

        if Deanonymize is not None and Vault is not None:
            try:
                vault = Vault(replacements)
                scanner = Deanonymize(vault)
                deanonymized_text, _, _ = scanner.scan("", text)
                return deanonymized_text
            except Exception:
                logger.debug("LLM Guard deanonymize failed; falling back to manual replacement.")

        deanonymized_text = text
        for placeholder, original in replacements:
            deanonymized_text = deanonymized_text.replace(placeholder, original)
        return deanonymized_text

    def _build_privacy_filter_scanner(self) -> PrivacyFilterScanner | None:
        try:
            scanner = PrivacyFilterScanner()
            scanner.warmup()
            return scanner
        except Exception as exc:
            logger.warning(
                "Privacy Filter scanner initialization failed; Custom Regex remains active as fallback. reason=%s",
                exc,
            )
            return None

    def _build_bancode_scanner(self) -> Any | None:
        if BanCode is None:
            return None
        local_model = _build_local_bancode_model(BANCODE_MODEL_SM)
        try:
            with _without_broken_loopback_proxies():
                return BanCode(model=local_model)
        except Exception as exc:
            logger.warning(
                "LLM Guard BanCode scanner PyTorch initialization failed; trying ONNX fallback. reason=%s",
                exc,
            )
            if find_spec("optimum.onnxruntime") is not None and getattr(local_model, "onnx_path", None):
                try:
                    with _without_broken_loopback_proxies(), _offline_huggingface_access():
                        return BanCode(model=local_model, use_onnx=True)
                except Exception as onnx_exc:
                    logger.warning(
                        "LLM Guard BanCode scanner ONNX initialization failed; source code filtering will use heuristic fallback. reason=%s",
                        onnx_exc,
                    )
            elif find_spec("optimum.onnxruntime") is not None:
                logger.warning(
                    "LLM Guard BanCode scanner ONNX fallback skipped because no cached ONNX snapshot was found; source code filtering will use heuristic fallback."
                )
            logger.warning(
                "LLM Guard BanCode scanner initialization failed; source code filtering will use heuristic fallback. reason=%s",
                exc,
            )
            return None

    def _build_qwen3guard_scanner(self) -> Qwen3GuardScanner | None:
        try:
            scanner = Qwen3GuardScanner()
            scanner.warmup()
            return scanner
        except Exception as exc:
            logger.warning(
                "Qwen3Guard scanner initialization failed; BanTopics and PromptInjection are disabled. reason=%s",
                exc,
            )
            return None

    def _build_business_sensitive_scanner(self) -> BusinessSensitiveScanner | None:
        try:
            return BusinessSensitiveScanner()
        except Exception as exc:
            logger.warning(
                "BusinessSensitive scanner initialization failed; business-sensitive filtering disabled. reason=%s",
                exc,
            )
            return None

    def _scan_with_privacy_filter(self, text: str) -> list[dict]:
        if self._privacy_filter_scanner is None:
            return []
        try:
            return self._privacy_filter_scanner.scan(text)
        except Exception:
            logger.debug("Privacy Filter runtime scan failed; Custom Regex remains active as fallback.", exc_info=True)
            return []

    def _reclassify_chinese_id_account_numbers(self, matches: list[dict]) -> list[dict]:
        reclassified: list[dict] = []
        for match in matches:
            entity = dict(match)
            if (
                self._canonical_entity_type(str(entity.get("type", ""))) == "ACCOUNT_NUMBER"
                and self._looks_like_chinese_id(str(entity.get("original", "")))
            ):
                entity["type"] = "CHINESE_ID"
            reclassified.append(entity)
        return reclassified

    def _looks_like_chinese_id(self, value: str) -> bool:
        candidate = re.sub(r"\s+", "", value or "")
        if not re.fullmatch(r"\d{17}[0-9Xx]", candidate):
            return False
        birth = candidate[6:14]
        year = int(birth[:4])
        month = int(birth[4:6])
        day = int(birth[6:8])
        if year < 1900 or year > 2099:
            return False
        days_in_month = {
            1: 31,
            2: 29 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31,
        }
        return 1 <= month <= 12 and 1 <= day <= days_in_month[month]

    def _scan_with_bancode(self, text: str) -> bool:
        heuristic_triggered = self._scan_with_bancode_fallback(text)
        if heuristic_triggered:
            return True

        if self._bancode_scanner is None:
            return False
        try:
            _, is_valid, _ = self._bancode_scanner.scan(text)
            if not is_valid and self._has_code_context(text):
                return True
        except Exception:
            logger.debug("LLM Guard BanCode runtime scan failed; falling back to heuristic source code detection.")
        return False

    def _scan_with_bancode_fallback(self, text: str) -> bool:
        candidate = (text or "").strip()
        if not candidate:
            return False

        if SOURCE_CODE_FENCE_RE.search(candidate):
            return True

        if "\n" not in candidate:
            return bool(SOURCE_CODE_INLINE_RE.search(candidate) and len(candidate) >= 40)

        matched_patterns = sum(1 for pattern in SOURCE_CODE_LINE_PATTERNS if pattern.search(candidate))
        indented_lines = sum(1 for line in candidate.splitlines() if line.startswith(("    ", "\t")))
        return matched_patterns >= 2 or (matched_patterns >= 1 and indented_lines >= 1)

    def _scan_with_qwen3guard(self, text: str) -> Qwen3GuardModerationResult:
        if self._qwen3guard_scanner is None:
            return Qwen3GuardModerationResult()
        try:
            return self._qwen3guard_scanner.scan_prompt(text)
        except Exception:
            logger.debug("Qwen3Guard runtime scan failed for prompt moderation.", exc_info=True)
            return Qwen3GuardModerationResult()

    def _scan_with_prompt_injection(self, text: str, moderation: Qwen3GuardModerationResult | None = None) -> bool:
        result = moderation or self._scan_with_qwen3guard(text)
        if result.safety_label not in {"Unsafe", "Controversial"}:
            return False
        return "Jailbreak" in result.categories

    def _has_code_context(self, text: str) -> bool:
        candidate = (text or "").strip()
        if not candidate:
            return False
        return bool(SOURCE_CODE_CONTEXT_RE.search(candidate))

    def _scan_with_ban_topics(self, text: str, moderation: Qwen3GuardModerationResult | None = None) -> list[str]:
        result = moderation or self._scan_with_qwen3guard(text)
        if result.safety_label not in {"Unsafe", "Controversial"}:
            return []
        return self._map_qwen3guard_categories_to_ban_topics(text, result.categories)

    def _map_qwen3guard_categories_to_ban_topics(self, text: str, categories: list[str]) -> list[str]:
        matched_topics: list[str] = []
        candidate = text or ""
        for category in categories:
            if category == "Jailbreak":
                continue
            if category == "Suicide & Self-Harm":
                matched_topics.append("self-harm")
                continue
            if category == "Violent":
                if WEAPONS_HINT_RE.search(candidate):
                    matched_topics.append("weapons")
                elif VIOLENT_GUIDANCE_HINT_RE.search(candidate):
                    matched_topics.append("illegal violent guidance")
                else:
                    matched_topics.append("violent wrongdoing")
                continue
            if category == "Non-violent Illegal Acts":
                matched_topics.append("financial fraud" if FINANCIAL_FRAUD_HINT_RE.search(candidate) else "restricted-topic")
                continue
            if category == "Unethical Acts":
                if HR_DISCRIMINATION_HINT_RE.search(candidate):
                    matched_topics.append("hr discriminatory or harassing content")
                elif HARASSMENT_HINT_RE.search(candidate):
                    matched_topics.append("harassment")
                elif DISCRIMINATION_HINT_RE.search(candidate):
                    matched_topics.append("discriminatory abuse")
                else:
                    matched_topics.append("restricted-topic")
                continue

        deduplicated: list[str] = []
        for topic in matched_topics:
            if topic not in deduplicated:
                deduplicated.append(topic)
        return deduplicated

    def _scan_with_business_sensitive(self, text: str):
        if self._business_sensitive_scanner is None:
            return BusinessSensitiveScanner.fallback_result(summary="Business sensitivity scanner unavailable.")
        return self._business_sensitive_scanner.scan(text)

    def _apply_business_sensitive_policy(self, text: str, entities: list[GuardrailEntity], result):
        if not getattr(result, "contains_business_sensitive", False):
            return result
        if self._should_exempt_pii_only_business_sensitive(text, entities, result):
            logger.info(
                "BusinessSensitive scanner hit was downgraded to non-blocking PII-only handling. summary=%s",
                getattr(result, "summary", ""),
            )
            return BusinessSensitiveScanner.fallback_result(
                summary="Business-sensitive hit downgraded because the prompt is a personal PII/profile request without commercial context."
            )
        return result

    def _should_exempt_pii_only_business_sensitive(self, text: str, entities: list[GuardrailEntity], result) -> bool:
        if self._contains_business_anchor(text):
            return False

        categories = {getattr(category, "name", "") for category in getattr(result, "categories", [])}
        if categories and not categories.issubset(PII_ONLY_EXEMPT_BUSINESS_CATEGORIES):
            return False

        entity_types = {entity.type for entity in entities}
        has_personal_pii = bool(entity_types & PERSONAL_PII_ENTITY_TYPES)
        if not has_personal_pii:
            return False

        if self._has_personal_profile_context(text):
            return True

        # If the text is dominated by direct personal identifiers and lacks commercial anchors,
        # prefer ordinary PII redaction over commercial blocking.
        return len(entity_types - PERSONAL_PII_ENTITY_TYPES) == 0 and len(entity_types) > 0

    def _contains_business_anchor(self, text: str) -> bool:
        candidate = (text or "").strip()
        return bool(candidate and BUSINESS_ANCHOR_RE.search(candidate))

    def _has_personal_profile_context(self, text: str) -> bool:
        candidate = (text or "").strip()
        return bool(candidate and PERSONAL_PROFILE_CONTEXT_RE.search(candidate))

    def _should_block_business_sensitive(self, result) -> bool:
        if not getattr(result, "contains_business_sensitive", False):
            return False
        return getattr(result, "risk_level", "low") in BUSINESS_SENSITIVE_BLOCK_RISK_LEVELS

    def _scan_with_custom_patterns(self, text: str) -> list[dict]:
        matches: list[dict] = []
        for entity_type, pattern in CUSTOM_PATTERNS:
            for match in pattern.finditer(text):
                if "value" in pattern.groupindex:
                    original = (match.group("value") or "").strip()
                    start = match.start("value")
                    end = match.end("value")
                else:
                    original = match.group(0).strip()
                    start = match.start()
                    end = match.end()
                if not original:
                    continue
                matches.append(
                    {
                        "type": entity_type,
                        "original": original,
                        "start": start,
                        "end": end,
                        "source": "custom_regex",
                    }
                )
        return matches

    def _get_model_path(self, scanner: Any | None) -> str | None:
        if scanner is None:
            return None
        model = getattr(scanner, "_model", None) or getattr(scanner, "model", None)
        if model is None:
            return None
        return getattr(model, "path", None) or getattr(model, "onnx_path", None)

    def _deduplicate_entities(self, entities: list[dict]) -> list[dict]:
        deduplicated: list[dict] = []
        for candidate in sorted(
            entities,
            key=lambda item: (
                item["start"],
                item["end"],
                0 if item.get("source") == PRIVACY_FILTER_SOURCE else 1,
                item["type"],
            ),
        ):
            exact_match = next(
                (
                    existing
                    for existing in deduplicated
                    if candidate["start"] == existing["start"]
                    and candidate["end"] == existing["end"]
                    and candidate["original"] == existing["original"]
                    and candidate["type"].upper() == existing["type"].upper()
                ),
                None,
            )
            if exact_match is not None:
                self._merge_entity_sources(exact_match, candidate)
                continue

            overlap = next(
                (
                    existing
                    for existing in deduplicated
                    if not (candidate["end"] <= existing["start"] or candidate["start"] >= existing["end"])
                ),
                None,
            )
            if overlap is None:
                deduplicated.append(candidate)
                continue

            if self._can_merge_same_type_overlap(candidate, overlap):
                chosen = self._choose_preferred_overlap_entity(candidate, overlap)
                other = overlap if chosen is candidate else candidate
                self._merge_entity_sources(chosen, other)
                if chosen is candidate:
                    deduplicated.remove(overlap)
                    deduplicated.append(chosen)
                continue

            if self._should_prefer_narrower_overlap(candidate, overlap):
                deduplicated.remove(overlap)
                deduplicated.append(candidate)
                continue

            if self._entity_priority(candidate) > self._entity_priority(overlap):
                deduplicated.remove(overlap)
                deduplicated.append(candidate)
        return deduplicated

    def _merge_adjacent_phone_entities(self, entities: list[dict], text: str) -> list[dict]:
        if not entities:
            return entities

        merged: list[dict] = []
        sorted_entities = sorted(entities, key=lambda item: (item["start"], item["end"], item["type"]))
        index = 0
        while index < len(sorted_entities):
            current = sorted_entities[index]
            current_type = self._canonical_entity_type(current.get("type", ""))
            if (
                current_type == "PHONE_NUMBER"
                and current.get("source") == "llm_guard"
                and current.get("original") == "+"
                and index + 1 < len(sorted_entities)
            ):
                following = sorted_entities[index + 1]
                following_type = self._canonical_entity_type(following.get("type", ""))
                between = text[current["end"]:following["start"]]
                if (
                    following_type == "PHONE_NUMBER"
                    and following.get("source") == "llm_guard"
                    and following["start"] == current["end"]
                    and between == ""
                ):
                    combined = {
                        "type": "PHONE_NUMBER",
                        "original": f"{current['original']}{following['original']}",
                        "start": current["start"],
                        "end": following["end"],
                        "source": "llm_guard",
                        "sources": sorted(
                            {
                                *current.get("sources", []),
                                current.get("source"),
                                *following.get("sources", []),
                                following.get("source"),
                            }
                            - {None}
                        ),
                    }
                    merged.append(combined)
                    index += 2
                    continue
            merged.append(current)
            index += 1
        return merged

    def _merge_entity_sources(self, target: dict, incoming: dict) -> None:
        sources = list(target.get("sources", []))
        for source in [target.get("source"), *incoming.get("sources", []), incoming.get("source")]:
            if source and source not in sources:
                sources.append(source)
        target["sources"] = sources
        if self._entity_priority(incoming) > self._entity_priority(target):
            target["source"] = incoming.get("source", target.get("source"))

    def _can_merge_same_type_overlap(self, candidate: dict, overlap: dict) -> bool:
        candidate_type = self._canonical_entity_type(candidate.get("type", ""))
        overlap_type = self._canonical_entity_type(overlap.get("type", ""))
        return candidate_type == overlap_type

    def _choose_preferred_overlap_entity(self, candidate: dict, overlap: dict) -> dict:
        if self._should_prefer_narrower_overlap(candidate, overlap):
            return candidate
        if self._should_prefer_narrower_overlap(overlap, candidate):
            return overlap
        return candidate if self._entity_priority(candidate) >= self._entity_priority(overlap) else overlap

    def _should_prefer_narrower_overlap(self, candidate: dict, overlap: dict) -> bool:
        candidate_type = self._canonical_entity_type(candidate.get("type", ""))
        overlap_type = self._canonical_entity_type(overlap.get("type", ""))
        if candidate_type != overlap_type:
            return False
        candidate_length = candidate["end"] - candidate["start"]
        overlap_length = overlap["end"] - overlap["start"]
        return candidate_length < overlap_length

    def _canonical_entity_type(self, value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
        return normalized.removesuffix("_RE")

    def _entity_priority(self, entity: dict) -> int:
        entity_type = self._canonical_entity_type(entity.get("type", ""))
        source = entity.get("source")
        if source == "custom_regex" and entity_type == "CHINESE_ID":
            return 360
        source_priority_map = {
            PRIVACY_FILTER_SOURCE: 220,
            "llm_guard_secrets": 220,
            "llm_guard": 120,
            "custom_regex": -20,
        }
        source_priority = source_priority_map.get(source, 0)
        type_priority_map = {
            "DATABASE_PASSWORD": 125,
            "PRIVATE_KEY": 122,
            "CLIENT_SECRET": 121,
            "ACCESS_TOKEN": 120,
            "AUTHORIZATION_HEADER": 119,
            "ENV_SECRET": 118,
            "COOKIE_SECRET": 117,
            "CREDENTIAL": 116,
            "DATABASE_URL": 115,
            "DATABASE_USER": 114,
            "PASSWORD": 113,
            "CHINESE_ID": 105,
            "CN_ID_CARD": 100,
            "BANK_CARD": 95,
            "CREDIT_CARD": 95,
            "CREDIT_CARD_RE": 95,
            "EMAIL_ADDRESS": 90,
            "EMAIL_ADDRESS_RE": 90,
            "CN_MOBILE_NUMBER": 85,
            "PHONE_NUMBER": 80,
            "ADDRESS": 78,
            "IPV4_ADDRESS": 70,
            "IPV6_ADDRESS": 70,
            "IP_ADDRESS": 70,
            "OPENAI_TOKEN": 68,
            "SECRET": 66,
            "API_KEY": 60,
            "PERSON": 50,
        }
        return source_priority + type_priority_map.get(entity_type, 40)

    def _apply_replacements(self, text: str, entities: list[GuardrailEntity]) -> str:
        if not entities:
            return text

        parts: list[str] = []
        cursor = 0
        for entity in sorted(entities, key=lambda item: item.start):
            parts.append(text[cursor:entity.start])
            parts.append(entity.replacement)
            cursor = entity.end
        parts.append(text[cursor:])
        return "".join(parts)


def get_guardrail_service() -> GuardrailService:
    global _GUARDRAIL_SERVICE_SINGLETON
    if _GUARDRAIL_SERVICE_SINGLETON is not None:
        return _GUARDRAIL_SERVICE_SINGLETON

    with _GUARDRAIL_SERVICE_LOCK:
        if _GUARDRAIL_SERVICE_SINGLETON is None:
            _GUARDRAIL_SERVICE_SINGLETON = GuardrailService()
        return _GUARDRAIL_SERVICE_SINGLETON


def _clear_guardrail_service_cache() -> None:
    global _GUARDRAIL_SERVICE_SINGLETON
    with _GUARDRAIL_SERVICE_LOCK:
        _GUARDRAIL_SERVICE_SINGLETON = None


get_guardrail_service.cache_clear = _clear_guardrail_service_cache  # type: ignore[attr-defined]
