from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4


class FileStorageService:
    def __init__(self, base_directory: str) -> None:
        self.base_directory = Path(base_directory).expanduser().resolve()

    def ensure_base_directory(self) -> Path:
        self.base_directory.mkdir(parents=True, exist_ok=True)
        return self.base_directory

    def build_target_path(self, original_filename: str) -> Path:
        self.ensure_base_directory()
        original_path = Path(original_filename or "upload")
        suffix = original_path.suffix.lower()
        stem = self._sanitize_stem(original_path.stem)[:80] or "upload"
        unique_name = f"{stem}-{uuid4().hex}{suffix}"
        return self.base_directory / unique_name

    def _sanitize_stem(self, value: str) -> str:
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "upload").strip("-._")
        return candidate or "upload"
