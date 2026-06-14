from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

from ..core.config import get_settings
from ..schemas.file_review import FileReviewHit, FileReviewResult
from ..schemas.file_review_runtime import ExtractedDocument
from .guardrails.business_sensitive_scanner import (
    BUSINESS_SENSITIVE_CATEGORIES,
    BusinessSensitiveCategory,
    OllamaClient,
)

logger = logging.getLogger(__name__)

FILE_REVIEW_CHUNK_CHAR_LIMIT = 1000

INSURANCE_CONTEXT_RE = re.compile(
    r"(保险|保单|投保|被保险|受益人|保费|理赔|承保|核保|保险责任|免赔|"
    r"policy|insured|insurer|premium|claim|underwriting|coverage)",
    re.IGNORECASE,
)
INSURANCE_CONTEXT_RE = re.compile(
    r"(\u4fdd\u9669|\u4fdd\u5355|\u6295\u4fdd|\u88ab\u4fdd\u9669|\u53d7\u76ca\u4eba|\u4fdd\u8d39|\u7406\u8d54|\u627f\u4fdd|\u6838\u4fdd|\u4fdd\u9669\u8d23\u4efb|\u514d\u8d54|"
    r"policy|insured|insurer|premium|claim|underwriting|coverage)",
    re.IGNORECASE,
)


class FileReviewChunkResult(BaseModel):
    contains_business_sensitive: bool = False
    risk_level: str = "low"
    summary: str = ""
    confidence: float = 0.0
    categories: list[BusinessSensitiveCategory] = Field(default_factory=list)


class FileReviewScanner:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.file_review_enabled
        self.model = settings.file_review_model
        self.timeout_seconds = settings.file_review_timeout_seconds
        self.client = OllamaClient(
            base_url=settings.file_review_ollama_url,
            timeout_seconds=self.timeout_seconds,
            model=self.model,
        )

    def review(self, document: ExtractedDocument) -> FileReviewResult:
        if not self.enabled:
            return FileReviewResult(summary="File review is disabled.", model=self.model)
        segments = [segment for segment in document.segments if (segment.text or "").strip()]
        if not segments:
            return FileReviewResult(
                summary="No extractable content was found in the uploaded file.",
                model=self.model,
                evaluated_at=datetime.now(timezone.utc),
            )

        hits: list[FileReviewHit] = []
        max_confidence = 0.0
        contains = False
        highest_risk = "low"
        summaries: list[str] = []
        categories: set[str] = set()

        for segment in self._build_review_chunks(segments)[:80]:
            chunk_result = self._review_segment(segment["location"], segment["text"])
            if chunk_result.summary and chunk_result.summary != "No business-sensitive content detected.":
                summaries.append(f"{segment['location']}: {chunk_result.summary}")
            segment_hits: list[FileReviewHit] = []
            for category in chunk_result.categories:
                if category.name not in BUSINESS_SENSITIVE_CATEGORIES:
                    continue
                matched_text = (category.matched_text or "").strip()
                if not matched_text or not self._text_contains_evidence(segment["text"], matched_text):
                    continue
                if category.name.startswith("insurance_") and not INSURANCE_CONTEXT_RE.search(segment["text"]):
                    continue
                categories.add(category.name)
                segment_hits.append(
                    FileReviewHit(
                        category=category.name,
                        risk_level=chunk_result.risk_level,
                        reason=category.reason or chunk_result.summary,
                        matched_text=matched_text[:300],
                        location=segment["location"],
                    )
                )
            if not segment_hits:
                continue
            hits.extend(segment_hits)
            contains = True
            max_confidence = max(max_confidence, chunk_result.confidence)
            highest_risk = self._pick_higher_risk(highest_risk, chunk_result.risk_level)

        if contains and highest_risk == "low":
            highest_risk = "medium"

        return FileReviewResult(
            contains_business_sensitive=contains,
            risk_level=highest_risk,
            summary="; ".join(summaries[:8]) if summaries else "No business-sensitive content detected.",
            confidence=round(max_confidence, 4),
            categories=sorted(categories),
            hits=hits[:30],
            model=self.model,
            evaluated_at=datetime.now(timezone.utc),
        )

    def _build_review_chunks(self, segments) -> list[dict[str, str]]:
        chunks: list[dict[str, str]] = []
        current_parts: list[str] = []
        current_locations: list[str] = []
        current_length = 0

        def flush() -> None:
            nonlocal current_parts, current_locations, current_length
            if not current_parts:
                return
            chunks.append(
                {
                    "location": self._format_chunk_location(current_locations),
                    "text": "\n".join(current_parts),
                }
            )
            current_parts = []
            current_locations = []
            current_length = 0

        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            location = segment.location or "Document"
            if current_parts and current_length + len(text) > FILE_REVIEW_CHUNK_CHAR_LIMIT:
                flush()
            current_parts.append(text)
            if location not in current_locations:
                current_locations.append(location)
            current_length += len(text)
            if current_length >= FILE_REVIEW_CHUNK_CHAR_LIMIT:
                flush()

        flush()
        return chunks

    def _format_chunk_location(self, locations: list[str]) -> str:
        if not locations:
            return "Document"
        if len(locations) == 1:
            return locations[0]
        if len(locations) <= 3:
            return " / ".join(locations)
        return f"{locations[0]} - {locations[-1]}"

    def _review_segment(self, location: str, text: str) -> FileReviewChunkResult:
        prompt = self._build_prompt(location, text)
        try:
            response = self.client.generate(prompt)
            payload = self._extract_json_object(response.raw_text)
            if payload is None:
                raise ValueError("missing-json-body")
            data = json.loads(payload)
            return FileReviewChunkResult.model_validate(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("File review parsing failed at %s: %s", location, exc)
        except Exception as exc:
            logger.warning("File review model call failed at %s: %s", location, exc)
        return FileReviewChunkResult(
            contains_business_sensitive=False,
            risk_level="low",
            summary="No business-sensitive content detected.",
            confidence=0.0,
            categories=[],
        )

    def _build_prompt(self, location: str, text: str) -> str:
        allowed_categories = ", ".join(BUSINESS_SENSITIVE_CATEGORIES)
        return (
            "You are an enterprise document business-sensitive information reviewer.\n"
            "Review only the actual document segment below and output only one valid JSON object.\n"
            "Required JSON fields: contains_business_sensitive, risk_level, summary, confidence, categories.\n"
            "categories must be an array of objects with: name, matched_text, reason.\n"
            f"Allowed category names: {allowed_categories}.\n"
            "summary must be one short sentence describing what information this document segment contains. "
            "For example, describe whether it is a contract, policy, invoice, resume, customer list, procurement document, hiring document, or technical file, and mention the main business content.\n"
            "If no business-sensitive content is present, return contains_business_sensitive=false, "
            "risk_level=low, categories=[], but still provide the one-sentence content summary.\n"
            "Use concise Chinese for summary and reason when the document is Chinese.\n"
            "Do not infer the industry from examples, file name, or prior conversations. "
            "Classify only what is explicitly present in the segment.\n"
            "matched_text must be a short exact substring copied from the segment. "
            "If you cannot quote exact evidence, do not add that category.\n"
            "Use insurance_* categories only when the segment explicitly contains insurance terms such as "
            "\u4fdd\u9669, \u4fdd\u5355, \u6295\u4fdd, \u88ab\u4fdd\u9669\u4eba, \u4fdd\u8d39, \u7406\u8d54, \u627f\u4fdd, \u6838\u4fdd, policy, insured, premium, claim, underwriting, or coverage.\n"
            "For ordinary procurement, sales, purchase, service, NDA, or supply contracts, use general categories "
            "such as contract_terms, pricing, product_spec, commercial_plan, or customer_data.\n"
            "The reason must describe the concrete evidence type found in this segment, not a generic industry template.\n"
            f"Segment location: {location}\n"
            "Document segment:\n"
            f"{text[:6000]}"
        )

    def _text_contains_evidence(self, text: str, evidence: str) -> bool:
        normalized_text = re.sub(r"\s+", "", text or "").lower()
        normalized_evidence = re.sub(r"\s+", "", evidence or "").lower()
        return bool(normalized_evidence and normalized_evidence in normalized_text)

    def _extract_json_object(self, raw_text: str) -> str | None:
        candidate = (raw_text or "").strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return candidate[start : end + 1]

    def _pick_higher_risk(self, current: str, incoming: str) -> str:
        levels = {"low": 0, "medium": 1, "high": 2}
        return incoming if levels.get(incoming, 0) > levels.get(current, 0) else current
