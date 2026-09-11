import hashlib
import io
import json
from pathlib import Path
import zipfile

from ..core.config import get_settings


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def review_policy_hash(enabled_scanners: list[str], business_config: dict[str, str] | None = None) -> str:
    settings = get_settings()
    # Includes model/threshold/cache configuration; only the hash is persisted.
    config = settings.model_dump(mode="json")
    relevant = {k: v for k, v in config.items() if k.startswith((
        "file_review_", "file_ocr_", "privacy_filter_", "qwen3guard_", "business_sensitive_",
    ))}
    return sha256(json.dumps({"version": 3, "scanners": sorted(enabled_scanners), "config": relevant,
                              "business_runtime": business_config or {}},
                             sort_keys=True, ensure_ascii=True).encode())


def verify_mime(filename: str, content: bytes) -> str:
    """Validate the original container, never convert or rewrite its bytes."""
    extension = Path(filename).suffix.lower()
    if extension == ".doc":
        raise ValueError("Legacy .doc files are not supported. Save the document as .docx or PDF and upload it again.")
    if extension == ".pdf":
        import fitz
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                if not content.startswith(b"%PDF-") or document.needs_pass or document.page_count == 0:
                    raise ValueError("Encrypted, empty or invalid PDF.")
        except Exception as exc:
            raise ValueError("Unreadable PDF file.") from exc
        return "application/pdf"
    office = {
        ".docx": ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".xlsx": ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".pptx": ("ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    }
    if extension in office:
        required, mime = office[extension]
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if required not in names or "[Content_Types].xml" not in names:
                    raise ValueError("Office content does not match the extension.")
                if sum(entry.file_size for entry in archive.infolist()) > 200 * 1024 * 1024:
                    raise ValueError("Office expanded content exceeds the review limit.")
        except zipfile.BadZipFile as exc:
            raise ValueError("Unreadable Office file.") from exc
        return mime
    image_formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".bmp": "BMP", ".webp": "WEBP"}
    if extension in image_formats:
        from PIL import Image
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != image_formats[extension]:
                    raise ValueError("Image content does not match the extension.")
                image.verify()
        except Exception as exc:
            raise ValueError("Unreadable image or mismatched extension.") from exc
        return "image/" + ("jpeg" if extension in {".jpg", ".jpeg"} else extension[1:])
    raise ValueError("Original file type is not supported.")
