"""Combine business review and strict privacy/safety checks, without modifying the original."""

from .file_review_scanner import FileReviewScanner
from ..schemas.file_review import FileReviewResult
from types import SimpleNamespace


def review_original_document(
    document, business_reviewer, guardrails, enabled_scanners, db, visual_reviewer=None,
    checkpoints=None, business_result: FileReviewResult | None = None,
):
    # visual_reviewer remains in the signature for compatibility but the optimized
    # pipeline never invokes a per-page vision model.
    if checkpoints:
        business_reviewer.checkpoint_store = checkpoints
    result = business_result or business_reviewer.review(document)
    if result.review_decision != "allow":
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
    if result.review_decision == "unknown":
        result.summary = "Original-file review is incomplete; no original file may be transmitted."
    return result
