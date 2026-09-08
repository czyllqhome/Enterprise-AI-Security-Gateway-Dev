from __future__ import annotations

import logging
import tarfile
from pathlib import Path

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class FileOCRService:
    def __init__(self) -> None:
        self._ocr_engine = None
        self._load_error: Exception | None = None
        self.settings = get_settings()

    def image_to_text(self, image_path: str | Path) -> str:
        engine = self._get_engine()
        if engine is None:
            return ""

        try:
            result = engine.ocr(str(image_path), cls=True)
        except Exception as exc:
            logger.warning("PaddleOCR failed for image %s: %s", image_path, exc)
            return ""

        lines: list[str] = []
        for block in result or []:
            for item in block or []:
                if not item or len(item) < 2:
                    continue
                text_payload = item[1]
                if not text_payload:
                    continue
                text = str(text_payload[0] or "").strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)

    def _get_engine(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        if self._load_error is not None:
            return None
        try:
            cache_root = Path(__file__).resolve().parents[2] / ".runtime-cache"
            # PaddleOCR pulls in albumentations, which imports torch via
            # albumentations.pytorch. Preloading torch keeps its Windows DLL
            # initialization stable before PaddleOCR loads additional native deps.
            import torch  # noqa: F401
            from paddleocr import PaddleOCR

            model_cache = cache_root / "paddleocr"
            det_model_dir = self._resolve_model_dir(
                self.settings.file_ocr_det_model_dir,
                model_cache / "det",
            )
            rec_model_dir = self._resolve_model_dir(
                self.settings.file_ocr_rec_model_dir,
                model_cache / "rec",
            )
            cls_model_dir = self._resolve_model_dir(
                self.settings.file_ocr_cls_model_dir,
                model_cache / "cls",
            )

            model_dirs = (det_model_dir, rec_model_dir, cls_model_dir)
            for model_dir in model_dirs:
                Path(model_dir).mkdir(parents=True, exist_ok=True)
                self._discard_corrupt_archives(Path(model_dir))
            logger.info(
                "Using PaddleOCR model directories: det=%s rec=%s cls=%s",
                det_model_dir,
                rec_model_dir,
                cls_model_dir,
            )

            try:
                self._ocr_engine = self._create_engine(
                    PaddleOCR, det_model_dir, rec_model_dir, cls_model_dir,
                )
            except Exception as exc:
                if not self._is_corrupt_archive_error(exc):
                    raise
                removed = sum(
                    self._discard_download_archives(Path(model_dir))
                    for model_dir in model_dirs
                )
                if not removed:
                    raise
                logger.warning(
                    "Discarded %s incomplete PaddleOCR download(s); retrying once.",
                    removed,
                )
                self._ocr_engine = self._create_engine(
                    PaddleOCR, det_model_dir, rec_model_dir, cls_model_dir,
                )
            return self._ocr_engine
        except Exception as exc:
            self._load_error = exc
            logger.warning("PaddleOCR is unavailable; OCR features will be skipped. reason=%s", exc)
            return None

    def _create_engine(self, paddle_ocr, det_model_dir: str, rec_model_dir: str, cls_model_dir: str):
        return paddle_ocr(
            use_angle_cls=True,
            lang="ch",
            det_model_dir=det_model_dir,
            rec_model_dir=rec_model_dir,
            cls_model_dir=cls_model_dir,
        )

    def _resolve_model_dir(self, raw_value: str, fallback: Path) -> str:
        candidate = (raw_value or "").strip()
        if not candidate:
            return str(fallback.resolve())
        path = Path(candidate).expanduser().resolve()
        if path.exists() and not path.is_dir():
            raise ValueError(f"Configured PaddleOCR model path is not a directory: {path}")
        if not path.exists():
            logger.info("PaddleOCR model directory will be initialized: %s", path)
        return str(path)

    def _discard_corrupt_archives(self, model_dir: Path) -> int:
        removed = 0
        for archive in model_dir.glob("*.tar"):
            try:
                with tarfile.open(archive, "r") as handle:
                    # Reading every member forces tarfile to detect a truncated payload.
                    for member in handle:
                        if member.isfile():
                            extracted = handle.extractfile(member)
                            if extracted is not None:
                                while extracted.read(1024 * 1024):
                                    pass
            except (tarfile.TarError, EOFError, OSError):
                archive.unlink(missing_ok=True)
                removed += 1
                logger.warning("Removed corrupt PaddleOCR model archive: %s", archive)
        return removed

    def _discard_download_archives(self, model_dir: Path) -> int:
        removed = 0
        for archive in model_dir.glob("*.tar"):
            archive.unlink(missing_ok=True)
            removed += 1
        return removed

    def _is_corrupt_archive_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return isinstance(exc, (tarfile.TarError, EOFError)) or any(
            marker in message
            for marker in ("unexpected end of data", "truncated", "unexpected end of file")
        )
