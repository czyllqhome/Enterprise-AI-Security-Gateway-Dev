"""Original file transport values. Extracted/OCR content never belongs here."""

import base64
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OriginalAttachment:
    file_id: int
    filename: str
    mime_type: str
    content: bytes
    sha256: str

    def __post_init__(self):
        if hashlib.sha256(self.content).hexdigest() != self.sha256:
            raise ValueError("Attachment bytes do not match the approved hash.")

    def responses_content(self) -> dict:
        data = base64.b64encode(self.content).decode("ascii")
        url = f"data:{self.mime_type};base64,{data}"
        if self.mime_type.startswith("image/"):
            return {"type": "input_image", "image_url": url}
        return {"type": "input_file", "filename": self.filename, "file_data": url}


def responses_messages(messages: list[dict]) -> list[dict]:
    """Translate trusted application messages without adding review material."""
    result = []
    for message in messages:
        attachments = message.get("attachments") or []
        if not attachments:
            result.append({"role": message["role"], "content": message["content"]})
            continue
        if message["role"] != "user":
            raise ValueError("Only user messages may contain original attachments.")
        content = [{"type": "input_text", "text": message["content"]}]
        content.extend(attachment.responses_content() for attachment in attachments)
        result.append({"role": "user", "content": content})
    return result
