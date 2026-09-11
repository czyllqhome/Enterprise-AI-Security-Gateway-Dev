from pathlib import Path
from types import SimpleNamespace

from app.services.file_ocr_service import FileOCRService


def service_with_paths(det: Path, rec: Path, cls: Path) -> FileOCRService:
    service = FileOCRService.__new__(FileOCRService)
    service._ocr_engine = None
    service._load_error = None
    service.device = "cpu"
    service.settings = SimpleNamespace(
        file_ocr_det_model_dir=str(det),
        file_ocr_rec_model_dir=str(rec),
        file_ocr_cls_model_dir=str(cls),
    )
    return service


def test_corrupt_cached_archive_is_removed_before_engine_start(tmp_path, monkeypatch):
    det, rec, cls_dir = tmp_path / "det", tmp_path / "rec", tmp_path / "cls"
    det.mkdir()
    corrupt_archive = det / "det-model.tar"
    corrupt_archive.write_bytes(b"truncated archive")
    engine = object()

    class FakePaddleOCR:
        def __new__(cls, **kwargs):
            assert not corrupt_archive.exists()
            assert kwargs["det_model_dir"] == str(det.resolve())
            assert kwargs["rec_model_dir"] == str(rec.resolve())
            assert kwargs["cls_model_dir"] == str(cls_dir.resolve())
            assert kwargs["use_gpu"] is False
            return engine

    monkeypatch.setitem(__import__("sys").modules, "torch", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "paddleocr",
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    assert service_with_paths(det, rec, cls_dir)._get_engine() is engine


def test_missing_model_directories_are_given_to_paddle_for_download(tmp_path):
    service = service_with_paths(tmp_path / "det", tmp_path / "rec", tmp_path / "cls")

    resolved = service._resolve_model_dir(str(tmp_path / "missing"), tmp_path / "fallback")

    assert resolved == str((tmp_path / "missing").resolve())
