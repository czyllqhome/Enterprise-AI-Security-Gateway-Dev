import base64
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.llm.attachments import OriginalAttachment
from app.services.llm.openai_client import LLMProviderError, OpenAIClient


def client_with_capabilities(capabilities):
    client = OpenAIClient.__new__(OpenAIClient)
    client.provider_label = "test endpoint"
    client.attachment_capabilities = capabilities
    client.client = SimpleNamespace(
        responses=SimpleNamespace(create=Mock(return_value=SimpleNamespace(
            status="completed", output_text="Answer",
        ))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock())),
    )
    return client


@pytest.mark.parametrize("mime,filename", [
    ("application/pdf", "原件.pdf"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "原件.docx"),
    ("image/png", "原件.png"),
])
def test_original_bytes_and_prompt_are_separate(mime, filename):
    payload = b"\x00original binary\xff\r\n"
    attachment = OriginalAttachment(1, filename, mime, payload, hashlib.sha256(payload).hexdigest())
    client = client_with_capabilities({"verified-model": [mime]})
    result = client.chat([{
        "role": "user", "content": "Summarize this file", "attachments": [attachment],
        "extracted_text": "OCR_ONLY_MARKER", "review_summary": "REVIEW_ONLY_MARKER",
    }], "verified-model")
    assert result == "Answer"
    request = client.client.responses.create.call_args.kwargs
    blocks = request["input"][0]["content"]
    assert blocks[0] == {"type": "input_text", "text": "Summarize this file"}
    encoded = blocks[1].get("image_url") or blocks[1]["file_data"]
    assert base64.b64decode(encoded.split(",", 1)[1]) == payload
    assert "OCR_ONLY_MARKER" not in str(request)
    assert "REVIEW_ONLY_MARKER" not in str(request)
    assert request["store"] is False
    client.client.chat.completions.create.assert_not_called()


def test_unconfigured_model_does_not_transmit_or_fallback():
    payload = b"original"
    attachment = OriginalAttachment(1, "file.pdf", "application/pdf", payload, hashlib.sha256(payload).hexdigest())
    client = client_with_capabilities({})
    with pytest.raises(LLMProviderError, match="not enabled"):
        client.chat([{"role": "user", "content": "hello", "attachments": [attachment]}], "unknown")
    client.client.responses.create.assert_not_called()
    client.client.chat.completions.create.assert_not_called()


def test_replaced_bytes_fail_hash_check():
    with pytest.raises(ValueError, match="approved hash"):
        OriginalAttachment(1, "file.pdf", "application/pdf", b"changed", hashlib.sha256(b"original").hexdigest())


def test_incomplete_response_is_not_a_success():
    payload = b"original"
    attachment = OriginalAttachment(1, "file.pdf", "application/pdf", payload, hashlib.sha256(payload).hexdigest())
    client = client_with_capabilities({"verified-model": ["application/pdf"]})
    client.client.responses.create.return_value = SimpleNamespace(status="incomplete", output_text="partial")
    with pytest.raises(LLMProviderError, match="incomplete"):
        client.chat([{"role": "user", "content": "hello", "attachments": [attachment]}], "verified-model")
