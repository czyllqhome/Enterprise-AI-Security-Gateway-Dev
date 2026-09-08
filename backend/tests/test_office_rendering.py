from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.office_rendering_service import OfficeRenderingService
from app.services.file_extraction_service import FileExtractionService
from app.schemas.file_review_runtime import ExtractedDocument


def test_converter_uses_argument_list_isolated_profile_and_no_shell(tmp_path, monkeypatch):
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake")
    source = tmp_path / "source.docx"
    source.write_bytes(b"original")

    def run(command, **kwargs):
        (tmp_path / "source.pdf").write_bytes(b"rendered")
        assert command[0] == str(executable.resolve())
        assert any(value.startswith("-env:UserInstallation=file:///") for value in command)
        assert command[-1] == str(source.resolve())
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.services.office_rendering_service.subprocess.run", run)
    assert OfficeRenderingService(str(executable), 10).render_pdf(source, tmp_path) == tmp_path / "source.pdf"


def test_missing_converter_is_explicitly_unavailable(tmp_path):
    with pytest.raises(RuntimeError, match="not been configured"):
        OfficeRenderingService("", 10).render_pdf(tmp_path / "source.doc", tmp_path)


def test_rendered_office_pages_become_visual_review_units(tmp_path, monkeypatch):
    import fitz
    rendered = tmp_path / "rendered.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((40, 40), "Rendered content")
        document.save(rendered)
    monkeypatch.setattr("app.services.office_rendering_service.OfficeRenderingService.render_pdf",
                        lambda self, source, output: rendered)
    extracted = ExtractedDocument("test", "", coverage_issues=["Slide layouts require rendered visual review."])
    result = FileExtractionService(SimpleNamespace())._with_office_render(tmp_path / "slides.pptx", extracted)
    assert result.coverage_complete
    assert result.visual_units[0].location == "Rendered page 1"
    assert "Rendered content" in result.plain_text
