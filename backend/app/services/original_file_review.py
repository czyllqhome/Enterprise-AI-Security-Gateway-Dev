"""Combine business review and strict privacy/safety checks, without modifying the original."""

from .file_review_scanner import FileReviewScanner
from .file_vision_review import FileVisionReviewer, VisualReviewResult
from ..schemas.file_review import FileReviewResult
from ..schemas.file_review_runtime import ExtractedSegmentPayload
from dataclasses import replace
from types import SimpleNamespace


def review_original_document(document, business_reviewer, guardrails, enabled_scanners, db, visual_reviewer=None, checkpoints=None):
    visual_reviewer = visual_reviewer or FileVisionReviewer()
    segments = list(document.segments)
    visual_failures = []
    visual_successes = 0
    for unit in document.visual_units:
        try:
            if checkpoints:
                verdict = checkpoints.run("visual", unit.location, unit.image_bytes,
                    lambda: visual_reviewer.review(unit), lambda value: value.model_dump(),
                    VisualReviewResult.model_validate, lambda value: value.decision in {"allow", "block"})
            else:
                verdict = visual_reviewer.review(unit)
        except Exception:
            visual_failures.append(unit.location)
            continue
        if verdict.decision == "block":
            return FileReviewResult(review_decision="block", summary=verdict.reason,
                                    total_visual_units=len(document.visual_units),
                                    reviewed_visual_units=visual_successes + 1)
        if verdict.decision != "allow":
            visual_failures.append(unit.location)
            continue
        visual_successes += 1
        segments.append(ExtractedSegmentPayload(location=unit.location + " visual review",
            text=verdict.visible_text + "\n" + verdict.description, source_kind="visual_review"))
    document = replace(document, segments=segments)
    if checkpoints:
        business_reviewer.checkpoint_store = checkpoints
    result = business_reviewer.review(document)
    result.total_visual_units = len(document.visual_units)
    result.reviewed_visual_units = visual_successes
    if result.review_decision == "block":
        return result
    # Business review already runs through the dedicated, strict file reviewer.
    scanners = [name for name in enabled_scanners if name not in {"business_sensitive", "deanonymize"}]
    if not {"privacy_filter", "custom_regex"}.intersection(scanners):
        result.review_decision = "unknown"
        result.summary = "No privacy scanner is enabled for original-file review."
        return result
    for chunk in FileReviewScanner._build_review_chunks(business_reviewer, document.segments):
        try:
            def evaluate_privacy():
                return guardrails.scan_text(
                    chunk["text"],
                    enabled_scanners=scanners,
                    db=db,
                    # Preserve partial scanner results so a definitive block is
                    # not hidden by a different scanner being unavailable. A
                    # degraded clean result is still handled as unknown below.
                    strict_mode=False,
                )
            if checkpoints:
                scan = checkpoints.run("privacy", chunk["location"], chunk["text"].encode(), evaluate_privacy,
                    lambda value: {name: getattr(value, name) for name in (
                        "has_sensitive_data", "bancode_triggered", "prompt_injection_triggered", "ban_topics_triggered",
                        "degraded_scanners")},
                    lambda value: SimpleNamespace(**value),
                    lambda value: (
                        value.has_sensitive_data or value.bancode_triggered
                        or value.prompt_injection_triggered or value.ban_topics_triggered
                        or not value.degraded_scanners
                    ))
            else:
                scan = evaluate_privacy()
        except Exception:
            result.review_decision = "unknown"
            result.failed_locations.append(chunk["location"])
            continue
        if scan.has_sensitive_data or scan.bancode_triggered or scan.prompt_injection_triggered or scan.ban_topics_triggered:
            result.review_decision = "block"
            result.summary = "Original file contains privacy or safety findings and cannot be sent unchanged."
            return result
        if getattr(scan, "degraded_scanners", []):
            result.review_decision = "unknown"
            result.failed_locations.append(chunk["location"])
    if not document.coverage_complete:
        result.review_decision = "unknown"
        result.failed_locations.extend(document.coverage_issues or ["Original content coverage is not verified."])
    if visual_failures:
        result.review_decision = "unknown"
        result.failed_locations.extend(visual_failures)
    if result.review_decision == "unknown":
        result.summary = "Original-file review is incomplete; no original file may be transmitted."
    return result
