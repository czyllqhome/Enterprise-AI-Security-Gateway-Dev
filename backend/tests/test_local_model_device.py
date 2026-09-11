import pytest
from types import SimpleNamespace

from app.core.config import Settings
from app.core.local_model_device import normalize_local_model_device, resolve_local_model_device
from app.services.file_ocr_service import FileOCRService
from app.services.guardrails.privacy_filter_scanner import PrivacyFilterScanner
from app.services.guardrails import qwen3guard_scanner


def test_scanners_inherit_global_device_by_default():
    settings = Settings(_env_file=None)

    assert settings.local_model_device == "auto"
    assert settings.qwen3guard_device == "inherit"
    assert settings.privacy_filter_device == "inherit"
    assert settings.file_ocr_device == "inherit"
    assert resolve_local_model_device(
        "cpu", settings.qwen3guard_device, setting_name="QWEN3GUARD_DEVICE"
    ) == "cpu"


def test_scanner_device_can_override_global_policy():
    assert resolve_local_model_device("cpu", "cuda", setting_name="QWEN3GUARD_DEVICE") == "cuda"
    assert resolve_local_model_device("cuda", "cpu", setting_name="PRIVACY_FILTER_DEVICE") == "cpu"


@pytest.mark.parametrize("value", ["gpu", "mps", "", "cuda:0"])
def test_invalid_global_device_is_rejected(value):
    with pytest.raises(ValueError, match="LOCAL_MODEL_DEVICE"):
        normalize_local_model_device(value)


def test_auto_keeps_privacy_filter_and_ocr_on_cpu():
    assert PrivacyFilterScanner._resolve_device("auto") == "cpu"
    assert FileOCRService._resolve_device("auto") == "cpu"


def test_qwen_cuda_request_fails_when_cuda_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        qwen3guard_scanner,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    with pytest.raises(RuntimeError, match="requires CUDA"):
        qwen3guard_scanner._resolve_runtime_device("cuda")


def test_privacy_cuda_request_fails_when_cuda_is_unavailable(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    with pytest.raises(RuntimeError, match="requires CUDA"):
        PrivacyFilterScanner._resolve_device("cuda")


def test_ocr_cuda_request_fails_with_cpu_paddle_build(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules,
        "paddle",
        SimpleNamespace(is_compiled_with_cuda=lambda: False),
    )
    with pytest.raises(RuntimeError, match="built without CUDA"):
        FileOCRService._resolve_device("cuda")
