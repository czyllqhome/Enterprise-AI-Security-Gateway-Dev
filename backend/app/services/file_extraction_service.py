from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from ..schemas.file_review_runtime import ExtractedDocument, ExtractedSegmentPayload
from .file_ocr_service import FileOCRService

logger = logging.getLogger(__name__)


class UnsupportedFileTypeError(Exception):
    pass


class FileExtractionService:
    SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def __init__(self, ocr_service: FileOCRService | None = None) -> None:
        self.ocr_service = ocr_service or FileOCRService()

    def extract(self, file_path: str | Path) -> ExtractedDocument:
        path = Path(file_path)
        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(f"Unsupported file type: {extension or 'unknown'}")
        if extension == ".docx":
            return self._extract_docx(path)
        if extension == ".xlsx":
            return self._extract_xlsx(path)
        if extension == ".pptx":
            return self._extract_pptx(path)
        if extension == ".pdf":
            return self._extract_pdf(path)
        return self._extract_image(path)

    def _extract_docx(self, path: Path) -> ExtractedDocument:
        from docx import Document

        document = Document(path)
        segments: list[ExtractedSegmentPayload] = []
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        for index, text in enumerate(paragraphs, start=1):
            segments.append(ExtractedSegmentPayload(location=f"Paragraph {index}", text=text))

        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                cell_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if not cell_texts:
                    continue
                text = " | ".join(cell_texts)
                segments.append(
                    ExtractedSegmentPayload(
                        location=f"Table {table_index} Row {row_index}",
                        text=text,
                        source_kind="table",
                    )
                )

        combined = "\n".join(segment.text for segment in segments)
        return ExtractedDocument(summary=f"{len(segments)} extracted segments", plain_text=combined, segments=segments)

    def _extract_xlsx(self, path: Path) -> ExtractedDocument:
        from openpyxl import load_workbook

        workbook = load_workbook(filename=path, read_only=True, data_only=True)
        segments: list[ExtractedSegmentPayload] = []
        for sheet in workbook.worksheets:
            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(value).strip() for value in row if value not in (None, "")]
                if not values:
                    continue
                text = " | ".join(values)
                segments.append(
                    ExtractedSegmentPayload(
                        location=f"{sheet.title}!Row {row_index}",
                        text=text,
                        sheet_name=sheet.title,
                        source_kind="table",
                    )
                )

        combined = "\n".join(segment.text for segment in segments)
        return ExtractedDocument(summary=f"{len(segments)} extracted rows", plain_text=combined, segments=segments)

    def _extract_pptx(self, path: Path) -> ExtractedDocument:
        from pptx import Presentation

        presentation = Presentation(path)
        segments: list[ExtractedSegmentPayload] = []

        for slide_index, slide in enumerate(presentation.slides, start=1):
            for shape_index, shape in enumerate(slide.shapes, start=1):
                if getattr(shape, "has_text_frame", False):
                    text = "\n".join(paragraph.text.strip() for paragraph in shape.text_frame.paragraphs if paragraph.text.strip())
                    if text:
                        segments.append(
                            ExtractedSegmentPayload(
                                location=f"Slide {slide_index} Shape {shape_index}",
                                text=text,
                                slide_number=slide_index,
                            )
                        )
                if getattr(shape, "shape_type", None) == 13 and getattr(shape, "image", None):
                    image_bytes = shape.image.blob
                    ocr_text = self._ocr_bytes(image_bytes, suffix=f"-slide-{slide_index}.png")
                    if ocr_text:
                        segments.append(
                            ExtractedSegmentPayload(
                                location=f"Slide {slide_index} Image {shape_index}",
                                text=ocr_text,
                                slide_number=slide_index,
                                source_kind="image_ocr",
                            )
                        )

        combined = "\n".join(segment.text for segment in segments)
        return ExtractedDocument(summary=f"{len(segments)} extracted slide items", plain_text=combined, segments=segments)

    def _extract_pdf(self, path: Path) -> ExtractedDocument:
        import fitz

        segments: list[ExtractedSegmentPayload] = []
        document = fitz.open(path)
        for page_index, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()
            if text:
                segments.append(
                    ExtractedSegmentPayload(
                        location=f"Page {page_index}",
                        text=text,
                        page_number=page_index,
                    )
                )
                continue

            try:
                pixmap = page.get_pixmap(dpi=160)
                ocr_text = self._ocr_bytes(pixmap.tobytes("png"), suffix=f"-page-{page_index}.png")
            except Exception as exc:
                logger.warning("PDF rasterization failed for %s page %s: %s", path, page_index, exc)
                ocr_text = ""
            if ocr_text:
                segments.append(
                    ExtractedSegmentPayload(
                        location=f"Page {page_index}",
                        text=ocr_text,
                        page_number=page_index,
                        source_kind="image_ocr",
                    )
                )

        combined = "\n".join(segment.text for segment in segments)
        return ExtractedDocument(summary=f"{len(segments)} extracted pages", plain_text=combined, segments=segments)

    def _extract_image(self, path: Path) -> ExtractedDocument:
        text = self.ocr_service.image_to_text(path)
        segment = ExtractedSegmentPayload(location="Image", text=text, source_kind="image_ocr")
        summary = "1 OCR segment" if text else "No OCR text extracted"
        return ExtractedDocument(summary=summary, plain_text=text, segments=[segment] if text else [])

    def _ocr_bytes(self, payload: bytes, *, suffix: str) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        try:
            return self.ocr_service.image_to_text(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
