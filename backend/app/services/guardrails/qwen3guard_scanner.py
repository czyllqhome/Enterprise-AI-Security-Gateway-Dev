from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

from ...core.config import get_settings
from ...core.model_cache import configure_local_model_cache

logger = logging.getLogger(__name__)

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover
    snapshot_download = None

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
except Exception:  # pragma: no cover
    AutoModelForCausalLM = None
    AutoTokenizer = None


SAFETY_PATTERN = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)", re.IGNORECASE)
CATEGORY_PATTERN = re.compile(
    r"(Violent|Non-violent Illegal Acts|Sexual Content or Sexual Acts|PII|Suicide & Self-Harm|"
    r"Unethical Acts|Politically Sensitive Topics|Copyright Violation|Jailbreak|None)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Qwen3GuardModerationResult:
    safety_label: str = "Safe"
    categories: list[str] = field(default_factory=list)
    raw_output: str = ""


def _resolve_runtime_device() -> str | None:
    if torch is None:
        return None
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_input_device(model) -> str | None:
    embed_weight = getattr(getattr(model, "get_input_embeddings", lambda: None)(), "weight", None)
    embed_device = getattr(embed_weight, "device", None)
    if embed_device is not None and str(embed_device) != "meta":
        return str(embed_device)

    hf_device_map = getattr(model, "hf_device_map", None) or {}
    for mapped_device in hf_device_map.values():
        if isinstance(mapped_device, str) and mapped_device not in {"disk", "meta"}:
            return mapped_device

    model_device = getattr(model, "device", None)
    if model_device is not None and str(model_device) != "meta":
        return str(model_device)

    return _resolve_runtime_device()


@lru_cache(maxsize=2)
def _load_qwen3guard_artifacts(model_reference: str):
    tokenizer = AutoTokenizer.from_pretrained(
        model_reference,
        local_files_only=True,
        trust_remote_code=True,
    )
    model_kwargs = {
        "local_files_only": True,
        "trust_remote_code": True,
        "torch_dtype": "auto",
    }
    runtime_device = _resolve_runtime_device()
    use_auto_device_map = find_spec("accelerate") is not None and runtime_device == "cuda"
    if use_auto_device_map:
        model_kwargs["device_map"] = "auto"
    else:
        if find_spec("accelerate") is None:
            logger.warning(
                "accelerate is unavailable; loading Qwen3Guard without device_map auto-placement. "
                "Install accelerate for improved startup and device placement."
            )
    model = AutoModelForCausalLM.from_pretrained(model_reference, **model_kwargs)
    if hasattr(model, "tie_weights"):
        model.tie_weights()
    if "device_map" not in model_kwargs and runtime_device is not None:
        model = model.to(runtime_device)
    return tokenizer, model


class Qwen3GuardScanner:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.qwen3guard_enabled
        self.model_name = settings.qwen3guard_model
        self.model_path = settings.qwen3guard_model_path.strip()
        self.max_new_tokens = settings.qwen3guard_max_new_tokens
        self.local_model_cache_dir = configure_local_model_cache()
        self.model_reference = self._ensure_model_reference()

    def warmup(self) -> None:
        if not self.enabled:
            raise RuntimeError("Qwen3Guard scanner is disabled.")
        if AutoTokenizer is None or AutoModelForCausalLM is None:
            raise RuntimeError("transformers is unavailable for Qwen3Guard scanner.")
        _load_qwen3guard_artifacts(self.model_reference)

    def scan_prompt(self, text: str) -> Qwen3GuardModerationResult:
        candidate = (text or "").strip()
        if not candidate or not self.enabled:
            return Qwen3GuardModerationResult()

        tokenizer, model = _load_qwen3guard_artifacts(self.model_reference)
        messages = [{"role": "user", "content": candidate}]
        rendered = tokenizer.apply_chat_template(messages, tokenize=False)
        input_device = _resolve_input_device(model)
        model_inputs = tokenizer([rendered], return_tensors="pt")
        if input_device is not None:
            model_inputs = model_inputs.to(input_device)
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=self.max_new_tokens,
        )
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]) :].tolist()
        raw_output = tokenizer.decode(output_ids, skip_special_tokens=True)
        safety_label, categories = self._parse_output(raw_output)
        return Qwen3GuardModerationResult(
            safety_label=safety_label or "Safe",
            categories=categories,
            raw_output=raw_output,
        )

    def _ensure_model_reference(self) -> str:
        resolved_reference = self._resolve_existing_model_reference()
        if resolved_reference is not None:
            return resolved_reference

        if snapshot_download is None:
            raise RuntimeError("huggingface_hub is unavailable for Qwen3Guard model download.")

        download_target = self.local_model_cache_dir / "qwen3guard" / self.model_name.split("/")[-1]
        download_target.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Qwen3Guard model not found locally; downloading snapshot. repo=%s target=%s",
            self.model_name,
            download_target,
        )
        snapshot_download(
            repo_id=self.model_name,
            cache_dir=str(self.local_model_cache_dir / "huggingface" / "hub"),
            local_dir=str(download_target),
            local_dir_use_symlinks=False,
        )
        if not (download_target / "config.json").exists():
            raise RuntimeError(f"Qwen3Guard download completed but config.json is missing in {download_target}")
        return str(download_target)

    def _resolve_existing_model_reference(self) -> str | None:
        if self.model_path:
            explicit_path = Path(self.model_path).expanduser().resolve()
            if (explicit_path / "config.json").exists():
                return str(explicit_path)

        model_leaf = self.model_name.split("/")[-1]
        direct_candidates = [
            self.local_model_cache_dir / model_leaf,
            self.local_model_cache_dir / "qwen3guard" / model_leaf,
        ]
        for candidate in direct_candidates:
            if (candidate / "config.json").exists():
                return str(candidate)

        hub_root = self.local_model_cache_dir / "huggingface" / "hub" / f"models--Qwen--{model_leaf}"
        snapshots_dir = hub_root / "snapshots"
        if snapshots_dir.exists():
            for snapshot in sorted(snapshots_dir.iterdir(), reverse=True):
                if snapshot.is_dir() and (snapshot / "config.json").exists():
                    return str(snapshot)

        return None

    @staticmethod
    def _parse_output(raw_output: str) -> tuple[str | None, list[str]]:
        normalized_categories: list[str] = []
        safety_match = SAFETY_PATTERN.search(raw_output or "")
        for category in CATEGORY_PATTERN.findall(raw_output or ""):
            normalized = category.strip()
            if normalized.lower() == "none":
                continue
            if normalized not in normalized_categories:
                normalized_categories.append(normalized)
        return (safety_match.group(1) if safety_match else None), normalized_categories
