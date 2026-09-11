from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from ..core.config import get_settings
from ..schemas.file_review import FileReviewHit, FileReviewResult
from ..schemas.file_review_runtime import ExtractedDocument
from .guardrails.business_sensitive_scanner import (
    BUSINESS_SENSITIVE_CATEGORIES,
    BusinessSensitiveCategory,
    BusinessSensitiveResult,
    BusinessSensitiveRuntimeConfig,
    BusinessSensitiveScanner,
)

logger = logging.getLogger(__name__)

FILE_REVIEW_CHUNK_CHAR_LIMIT = 12000

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
    contains_business_sensitive: bool = Field(strict=True)
    risk_level: Literal["low", "medium", "high"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    # Some local models omit the optional-looking array for a clean verdict.
    # Treat that omission as an empty list; a positive verdict without concrete,
    # verifiable category evidence still fails closed in review().
    categories: list[BusinessSensitiveCategory] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_verdict(self):
        if not self.contains_business_sensitive and (self.categories or self.risk_level != "low"):
            raise ValueError("Inconsistent file review verdict")
        return self


class FileReviewScanner:
    def __init__(self, db=None) -> None:
        settings = get_settings()
        self.enabled = settings.file_review_enabled and settings.business_sensitive_enabled
        self.business_scanner = BusinessSensitiveScanner()
        self.runtime: BusinessSensitiveRuntimeConfig = self.business_scanner.resolve_runtime_config(db)
        self.provider = self.runtime.provider
        self.model = self.runtime.model
        self.client = self.business_scanner._get_client(self.runtime)
        self.chunk_workers = max(settings.file_review_chunk_workers, 1)
        self.max_chunks = max(settings.file_review_max_chunks, 1)
        self.chunk_char_limit = max(settings.file_review_chunk_char_limit, 1000)
        self.chunk_overlap_chars = min(max(settings.file_review_chunk_overlap_chars, 0), self.chunk_char_limit - 1)

    def supports_direct_file_review(self, mime_type: str) -> bool:
        return self.runtime.provider == "openrouter" and (
            mime_type == "application/pdf" or mime_type.startswith("image/")
        )

    def review_file(self, *, filename: str, mime_type: str, content: bytes) -> FileReviewResult:
        try:
            result = self.business_scanner.scan_file_or_raise(
                filename=filename, mime_type=mime_type, content=content, runtime=self.runtime,
            )
        except Exception as exc:
            logger.warning("Direct multimodal file review failed for %s: %s", filename, exc)
            return FileReviewResult(
                review_decision="unknown", failed_locations=[filename],
                summary="Multimodal business-sensitive review failed.", model=self.model,
                evaluated_at=datetime.now(timezone.utc),
            )
        return self._business_result_to_file_result(result, location=filename)

    def _business_result_to_file_result(self, result: BusinessSensitiveResult, *, location: str) -> FileReviewResult:
        hits = [FileReviewHit(
            category=category.name, risk_level=result.risk_level, reason=category.reason,
            matched_text=category.matched_text[:300], location=location,
        ) for category in result.categories]
        decision = "allow"
        if result.contains_business_sensitive:
            decision = "block" if result.risk_level == "high" else "needs_confirmation"
        return FileReviewResult(
            review_decision=decision, total_chunks=1, reviewed_chunks=1,
            contains_business_sensitive=result.contains_business_sensitive,
            risk_level=result.risk_level, summary=result.summary[:500], confidence=result.confidence,
            categories=sorted({category.name for category in result.categories}), hits=hits[:30],
            model=self.model, evaluated_at=datetime.now(timezone.utc),
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
        chunks = self._build_review_chunks(segments)
        max_chunks = getattr(self, "max_chunks", get_settings().file_review_max_chunks)
        if len(chunks) > max_chunks:
            return FileReviewResult(
                review_decision="unknown", total_chunks=len(chunks),
                failed_locations=[f"Document exceeds the {max_chunks}-chunk review limit."],
                summary="Document is too large for complete business-sensitive review.",
                model=self.model, evaluated_at=datetime.now(timezone.utc),
            )
        failed_locations: list[str] = []
        reviewed_chunks = 0

        def evaluate(segment):
            store = getattr(self, "checkpoint_store", None)
            if store:
                return store.run("business", segment["location"], segment["text"].encode(),
                    lambda: self._review_segment(segment["location"], segment["text"]),
                    lambda value: value.model_dump(), FileReviewChunkResult.model_validate,
                    lambda value: value is not None and (not value.contains_business_sensitive or (
                        bool(value.categories) and all(category.name in BUSINESS_SENSITIVE_CATEGORIES
                            and bool(category.matched_text) and self._text_contains_evidence(segment["text"], category.matched_text)
                            and (not category.name.startswith("insurance_") or INSURANCE_CONTEXT_RE.search(segment["text"]))
                            for category in value.categories)
                    )))
            return self._review_segment(segment["location"], segment["text"])

        workers = min(getattr(self, "chunk_workers", 1), max(len(chunks), 1))
        if workers == 1:
            chunk_results = [evaluate(segment) for segment in chunks]
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="file-business-review") as executor:
                chunk_results = list(executor.map(evaluate, chunks))

        for segment, chunk_result in zip(chunks, chunk_results):
            if chunk_result is None:
                failed_locations.append(segment["location"])
                continue
            reviewed_chunks += 1
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
            if chunk_result.contains_business_sensitive and not segment_hits:
                # A positive verdict with unverifiable evidence is not a clean scan.
                failed_locations.append(segment["location"])
                reviewed_chunks -= 1
            if not segment_hits:
                continue
            hits.extend(segment_hits)
            contains = True
            max_confidence = max(max_confidence, chunk_result.confidence)
            highest_risk = self._pick_higher_risk(highest_risk, chunk_result.risk_level)

        if contains and highest_risk == "low":
            highest_risk = "medium"

        return FileReviewResult(
            review_decision=(
                "block" if contains and highest_risk == "high"
                else "needs_confirmation" if contains
                else "unknown" if failed_locations else "allow"
            ),
            total_chunks=len(chunks),
            reviewed_chunks=reviewed_chunks,
            failed_locations=failed_locations,
            contains_business_sensitive=contains,
            risk_level=highest_risk,
            summary=("Review incomplete; some content could not be evaluated." if failed_locations
                     else "; ".join(summaries[:8])[:500] if summaries else "No business-sensitive content detected."),
            confidence=round(max_confidence, 4),
            categories=sorted(categories),
            hits=hits[:30],
            model=self.model,
            evaluated_at=datetime.now(timezone.utc),
        )

    def _build_review_chunks(self, segments) -> list[dict[str, str]]:
        chunk_limit = getattr(self, "chunk_char_limit", FILE_REVIEW_CHUNK_CHAR_LIMIT)
        overlap = getattr(self, "chunk_overlap_chars", 500)
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
            if len(text) > chunk_limit:
                flush()
                # Overlap protects entities/phrases straddling a chunk boundary.
                step = chunk_limit - overlap
                for offset in range(0, len(text), step):
                    chunks.append({
                        "location": f"{location} (chars {offset + 1}-{min(offset + chunk_limit, len(text))})",
                        "text": text[offset:offset + chunk_limit],
                    })
                    if offset + chunk_limit >= len(text):
                        break
                continue
            if current_parts and current_length + len(text) > chunk_limit:
                flush()
            current_parts.append(text)
            if location not in current_locations:
                current_locations.append(location)
            current_length += len(text)
            if current_length >= chunk_limit:
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

    def _review_segment(self, location: str, text: str) -> FileReviewChunkResult | None:
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
        return None

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
            f"{text}"
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
