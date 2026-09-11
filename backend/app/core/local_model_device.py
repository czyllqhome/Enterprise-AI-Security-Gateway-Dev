from typing import Literal


LocalModelDevice = Literal["auto", "cpu", "cuda"]
LOCAL_MODEL_DEVICES = {"auto", "cpu", "cuda"}
LOCAL_MODEL_DEVICE_OVERRIDES = LOCAL_MODEL_DEVICES | {"inherit"}


def normalize_local_model_device(value: str, *, setting_name: str = "LOCAL_MODEL_DEVICE") -> LocalModelDevice:
    normalized = value.strip().lower()
    if normalized not in LOCAL_MODEL_DEVICES:
        allowed = ", ".join(sorted(LOCAL_MODEL_DEVICES))
        raise ValueError(f"{setting_name} must be one of: {allowed}.")
    return normalized  # type: ignore[return-value]


def resolve_local_model_device(
    global_device: str,
    scanner_device: str | None,
    *,
    setting_name: str,
) -> LocalModelDevice:
    override = (scanner_device or "inherit").strip().lower()
    if override not in LOCAL_MODEL_DEVICE_OVERRIDES:
        allowed = ", ".join(sorted(LOCAL_MODEL_DEVICE_OVERRIDES))
        raise ValueError(f"{setting_name} must be one of: {allowed}.")
    if override == "inherit":
        return normalize_local_model_device(global_device)
    return normalize_local_model_device(override, setting_name=setting_name)
