import json
from types import SimpleNamespace

import pytest

from app.schemas.file_review import FileReviewResult
from app.schemas.file_review_runtime import ExtractedDocument, ExtractedSegmentPayload
from app.services.file_review_scanner import FileReviewScanner


def scanner_with(generate):
    scanner = FileReviewScanner.__new__(FileReviewScanner)
    scanner.enabled = True
    scanner.model = "test-model"
    scanner.client = SimpleNamespace(generate=generate)
    return scanner


def clean_response():
    return SimpleNamespace(raw_text=json.dumps({
        "contains_business_sensitive": False,
        "risk_level": "low",
        "summary": "Public information.",
        "confidence": 0.9,
        "categories": [],
    }))


def document(*texts):
    return ExtractedDocument("test", "\n".join(texts), [
        ExtractedSegmentPayload(location=f"Page {index + 1}", text=text)
        for index, text in enumerate(texts)
    ])


def test_scans_beyond_eightieth_chunk():
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return clean_response()

    result = scanner_with(generate).review(document(*[str(i) + "x" * 1000 for i in range(81)]))
    assert result.review_decision == "allow"
    assert result.total_chunks == result.reviewed_chunks == len(prompts)
    assert any("Page 81" in prompt for prompt in prompts)


def test_long_segment_keeps_tail_and_overlapping_boundaries():
    text = "x" * 950 + "boundary-sensitive-marker" + "y" * 7000 + "TAIL_EVIDENCE"
    scanner = scanner_with(lambda _: clean_response())
    chunks = scanner._build_review_chunks(document(text).segments)
    assert all(len(chunk["text"]) <= 1000 for chunk in chunks)
    assert "TAIL_EVIDENCE" in chunks[-1]["text"]
    assert any("boundary-sensitive-marker" in chunk["text"] for chunk in chunks)
    assert "TAIL_EVIDENCE" in scanner._build_prompt("Page 1", text)


@pytest.mark.parametrize("raw", ["not json", "{}", '{"risk_level":"low"}', json.dumps({
    "contains_business_sensitive": False, "risk_level": "banana", "summary": "ok",
    "confidence": 0.9, "categories": [],
})])
def test_invalid_model_response_is_unknown(raw):
    result = scanner_with(lambda _: SimpleNamespace(raw_text=raw)).review(document("Some text"))
    assert result.review_decision == "unknown"
    assert result.reviewed_chunks == 0
    assert result.failed_locations == ["Page 1"]


def test_timeout_does_not_erase_other_chunk_results():
    def generate(prompt):
        if "Page 2" in prompt:
            raise TimeoutError("test")
        return clean_response()

    result = scanner_with(generate).review(document("a" * 1000, "b" * 1000))
    assert result.review_decision == "unknown"
    assert result.total_chunks == 2
    assert result.reviewed_chunks == 1
    assert result.failed_locations == ["Page 2"]


def test_disabled_or_empty_review_does_not_allow():
    scanner = scanner_with(lambda _: clean_response())
    assert scanner.review(document()).review_decision == "unknown"
    scanner.enabled = False
    assert scanner.review(document("text")).review_decision == "unknown"


def test_legacy_result_has_no_complete_review_proof():
    assert FileReviewResult.model_validate({"risk_level": "low"}).review_decision == "unknown"


def test_positive_verdict_without_evidence_is_unknown():
    result = scanner_with(lambda _: SimpleNamespace(raw_text=json.dumps({
        "contains_business_sensitive": True, "risk_level": "high", "summary": "Sensitive",
        "confidence": 0.9, "categories": [],
    }))).review(document("test"))
    assert result.review_decision == "unknown"
    assert result.reviewed_chunks == 0


def test_medium_business_sensitive_content_blocks_unchanged_original():
    response = SimpleNamespace(raw_text=json.dumps({
        "contains_business_sensitive": True,
        "risk_level": "medium",
        "summary": "Contains contract pricing.",
        "confidence": 0.91,
        "categories": [{
            "name": "pricing",
            "matched_text": "unit price 1200",
            "reason": "Commercial price",
        }],
    }))

    result = scanner_with(lambda _: response).review(
        document("The agreed unit price 1200 is confidential."),
    )

    assert result.contains_business_sensitive is True
    assert result.risk_level == "medium"
    assert result.review_decision == "block"
