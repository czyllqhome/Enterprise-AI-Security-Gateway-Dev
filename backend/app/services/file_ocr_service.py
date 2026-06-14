from __future__ import annotations

import logging
import os
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
            paddle_cache = cache_root / "paddle"
            paddle_cache.mkdir(parents=True, exist_ok=True)
            os.environ["PADDLE_HOME"] = str(paddle_cache)
            os.environ["XDG_CACHE_HOME"] = str(cache_root)
            os.environ["HOME"] = str(cache_root)
            os.environ["USERPROFILE"] = str(cache_root)
            # PaddleOCR pulls in albumentations, which imports torch via
            # albumentations.pytorch. Preloading torch keeps its Windows DLL
            # initialization stable before PaddleOCR loads additional native deps.
            import torch  # noqa: F401
            from paddleocr import PaddleOCR

            det_model_dir = self._resolve_model_dir(self.settings.file_ocr_det_model_dir)
            rec_model_dir = self._resolve_model_dir(self.settings.file_ocr_rec_model_dir)
            cls_model_dir = self._resolve_model_dir(self.settings.file_ocr_cls_model_dir)

            if det_model_dir:
                logger.info("Using local PaddleOCR det model: %s", det_model_dir)
            if rec_model_dir:
                logger.info("Using local PaddleOCR rec model: %s", rec_model_dir)
            if cls_model_dir:
                logger.info("Using local PaddleOCR cls model: %s", cls_model_dir)
            if det_model_dir and not rec_model_dir:
                logger.warning("Local PaddleOCR det model found, but rec model is not configured; PaddleOCR may still try to download rec.")
            if det_model_dir and not cls_model_dir:
                logger.warning("Local PaddleOCR det model found, but cls model is not configured; PaddleOCR may still try to download cls.")

            self._ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                det_model_dir=det_model_dir,
                rec_model_dir=rec_model_dir,
                cls_model_dir=cls_model_dir,
            )
            return self._ocr_engine
        except Exception as exc:
            self._load_error = exc
            logger.warning("PaddleOCR is unavailable; OCR features will be skipped. reason=%s", exc)
            return None

    def _resolve_model_dir(self, raw_value: str) -> str | None:
        candidate = (raw_value or "").strip()
        if not candidate:
            return None
        path = Path(candidate).expanduser().resolve()
        if path.exists() and path.is_dir():
            return str(path)
        logger.warning("Configured PaddleOCR model directory does not exist: %s", path)
        return None
