from types import SimpleNamespace

from PIL import Image, PngImagePlugin

from app.services.file_extraction_service import FileExtractionService
from app.services.guardrails.llm_guard_service import GuardrailService


def test_png_dpi_metadata_does_not_look_like_a_bank_card(tmp_path):
    path = tmp_path / "animals.png"
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("description", "Public animal photograph")
    Image.new("RGB", (8, 8), "white").save(path, dpi=(143.9926, 143.9926), pnginfo=png_info)
    ocr = SimpleNamespace(image_to_text=lambda _: "Animal Welfare Institute\nANIMALS101\nELEPHANTS")

    document = FileExtractionService(ocr_service=ocr).extract(path)
    metadata = next(segment.text for segment in document.segments if segment.location == "Image metadata")
    matches = GuardrailService._scan_with_custom_patterns(GuardrailService.__new__(GuardrailService), metadata)

    assert "Public animal photograph" in metadata
    assert "143.9926" in metadata
    assert not [match for match in matches if match["type"] == "BANK_CARD"]
