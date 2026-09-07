from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from app.schemas.file_review import FileReviewResult
from app.schemas.file_review_runtime import ExtractedDocument, ExtractedSegmentPayload
from app.schemas.guardrail import GuardrailScanResult
from app.services.file_review_scanner import FileReviewScanner
from app.services.original_file_review import review_original_document


def run_review(*, complete=True, private=False, failure=False, enabled=None):
    document = ExtractedDocument("test", "Public text", [ExtractedSegmentPayload("Page 1", "Public text")],
                                 coverage_complete=complete)
    scanner = FileReviewScanner.__new__(FileReviewScanner)
    scanner.review = Mock(return_value=FileReviewResult(review_decision="allow", total_chunks=1, reviewed_chunks=1))
    guard = SimpleNamespace(scan_text=Mock(return_value=GuardrailScanResult(
        original_text="Public text", sanitized_text="Public text", has_sensitive_data=private, entities=[],
    )))
    if failure:
        guard.scan_text.side_effect = RuntimeError("scanner unavailable")
    result = review_original_document(document, scanner, guard,
        ["custom_regex", "business_sensitive"] if enabled is None else enabled, None)
    return result, guard


def test_complete_original_requires_business_and_privacy_review():
    result, guard = run_review()
    assert result.review_decision == "allow"
    assert guard.scan_text.call_args.kwargs["strict_mode"] is True
    assert guard.scan_text.call_args.kwargs["enabled_scanners"] == ["custom_regex"]


def test_privacy_finding_blocks_original_instead_of_sending_sanitized_text():
    result, _ = run_review(private=True)
    assert result.review_decision == "block"


def test_privacy_runtime_failure_is_unknown():
    result, _ = run_review(failure=True)
    assert result.review_decision == "unknown"
    assert result.failed_locations == ["Page 1"]


def test_incomplete_parser_cannot_produce_original_file_approval():
    result, _ = run_review(complete=False)
    assert result.review_decision == "unknown"


def test_disabled_privacy_checks_cannot_approve_original_file():
    result, guard = run_review(enabled=["business_sensitive"])
    assert result.review_decision == "unknown"
    guard.scan_text.assert_not_called()


def test_strict_privacy_mode_propagates_runtime_failure():
    from app.services.guardrails.llm_guard_service import GuardrailService
    service = GuardrailService.__new__(GuardrailService)
    service.get_scanner_availability = lambda **kw: {"privacy_filter": True}
    service._privacy_filter_scanner = SimpleNamespace(scan=Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError, match="offline"):
        service.scan_text("text", enabled_scanners=["privacy_filter"], strict=True)


def test_strict_moderation_rejects_unparseable_verdict():
    from app.services.guardrails.llm_guard_service import GuardrailService
    service = GuardrailService.__new__(GuardrailService)
    service.get_scanner_availability = lambda **kw: {"prompt_injection": True}
    service._qwen3guard_scanner = SimpleNamespace(
        scan_prompt=lambda _: SimpleNamespace(raw_output="broken", safety_label="Safe"),
        _parse_output=lambda _: (None, []),
    )
    with pytest.raises(RuntimeError, match="invalid verdict"):
        service.scan_text("text", enabled_scanners=["prompt_injection"], strict=True)
