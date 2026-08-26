from __future__ import annotations

import logging
import re
import shutil
from importlib.util import find_spec
from pathlib import Path
from typing import Literal

from ...core.config import BASE_DIR, get_settings

logger = logging.getLogger(__name__)

PRIVACY_FILTER_SCANNER_NAME = "Privacy Filter"
PRIVACY_FILTER_SOURCE = "privacy_filter"
PRIVACY_FILTER_REPO_ID = "openai/privacy-filter"

LABEL_TYPE_MAP = {
    "private_person": "PERSON",
    "private_address": "ADDRESS",
    "private_email": "EMAIL_ADDRESS",
    "private_phone": "PHONE_NUMBER",
    "private_url": "PRIVATE_URL",
    "private_date": "PRIVATE_DATE",
    "account_number": "ACCOUNT_NUMBER",
    "secret": "SECRET",
}

CHINESE_NAME_HINT_RE = re.compile(r"(姓名|联系人|员工|客户|人员|负责人|申请人)")
PHONE_HINT_RE = re.compile(r"(电话|手机|手机号|联系方式|mobile|phone|tel)", re.IGNORECASE)
DIGIT_HEAVY_RE = re.compile(r"\+?\d(?:[\d\s\-()]){6,}\d")


class PrivacyFilterScanner:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.privacy_filter_enabled
        self.auto_download = settings.privacy_filter_auto_download
        self.model_path = self._resolve_model_path(settings.privacy_filter_model_path)
        self.device = self._resolve_device(settings.privacy_filter_device)
        self.decode_mode = self._resolve_decode_mode(settings.privacy_filter_decode_mode)
        self.output_mode = self._resolve_output_mode(settings.privacy_filter_output_mode)
        self.context_window_length = (
            settings.privacy_filter_context_window_length
            if settings.privacy_filter_context_window_length > 0
            else None
        )
        self._scanner = None

    @property
    def model_reference(self) -> str:
        return str(self.model_path)

    def warmup(self) -> None:
        if not self.enabled:
            raise RuntimeError("Privacy Filter scanner is disabled.")
        if find_spec("opf") is None:
            raise RuntimeError("opf package is unavailable for Privacy Filter scanner.")
        self._ensure_checkpoint()
        self._scanner = self._build_scanner()
        # OPF initializes its tokenizer/runtime lazily. A real inference here keeps
        # tokenizer downloads and model initialization out of the first user request.
        self._scanner.redact("Privacy filter warmup check.")

    def scan(self, text: str) -> list[dict]:
        candidate = text or ""
        if not candidate.strip() or not self.enabled:
            return []
        scanner = self._scanner or self._build_scanner()
        self._scanner = scanner
        result = scanner.redact(candidate)
        matches = self._extract_matches(candidate, result)
        matches.extend(self._scan_chinese_context_probes(scanner, candidate))
        return self._deduplicate_matches(matches)

    def _extract_matches(self, candidate: str, result, *, offset: int = 0) -> list[dict]:
        matches: list[dict] = []
        for span in getattr(result, "detected_spans", ()) or ():
            label = str(getattr(span, "label", "") or "")
            entity_type = LABEL_TYPE_MAP.get(label)
            if entity_type is None:
                continue
            start = int(getattr(span, "start", -1))
            end = int(getattr(span, "end", -1))
            if start < 0 or end <= start or end > len(candidate):
                continue
            original = str(getattr(span, "text", "") or candidate[start:end])
            if not original:
                continue
            matches.append(
                {
                    "type": entity_type,
                    "original": original,
                    "start": offset + start,
                    "end": offset + end,
                    "source": PRIVACY_FILTER_SOURCE,
                }
            )
        return matches

    def _scan_chinese_context_probes(self, scanner, text: str) -> list[dict]:
        lines = list(self._iter_nonempty_lines(text))
        probes: list[dict] = []
        for index, (line, start) in enumerate(lines):
            for prefix, allowed_types in self._build_context_probes(
                line,
                lines[index - 1][0] if index > 0 else "",
            ):
                probes.append(
                    {
                        "text": f"{prefix}{line}",
                        "line": line,
                        "source_start": start,
                        "allowed_types": allowed_types,
                    }
                )
        if not probes:
            return []

        combined_parts: list[str] = []
        cursor = 0
        for probe in probes:
            probe["combined_start"] = cursor
            combined_parts.append(probe["text"])
            cursor += len(probe["text"])
            probe["combined_end"] = cursor
            combined_parts.append("\n")
            cursor += 1

        combined = "".join(combined_parts)
        try:
            result = scanner.redact(combined)
        except Exception:
            logger.debug("Privacy Filter batched context probe failed.", exc_info=True)
            return []

        matches: list[dict] = []
        for match in self._extract_matches(combined, result):
            probe = next(
                (
                    item
                    for item in probes
                    if item["combined_start"] <= match["start"]
                    and match["end"] <= item["combined_end"]
                ),
                None,
            )
            if probe is None or match["type"] not in probe["allowed_types"]:
                continue
            local_start = self._find_probe_value_offset(probe["line"], match["original"])
            if local_start is None:
                continue
            matches.append(
                {
                    **match,
                    "start": probe["source_start"] + local_start,
                    "end": probe["source_start"] + local_start + len(match["original"]),
                }
            )
        return matches

    def _build_context_probes(self, line: str, previous_line: str) -> list[tuple[str, set[str]]]:
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            return []

        hints = f"{previous_line}\n{stripped}"
        probes: list[tuple[str, set[str]]] = []
        if CHINESE_NAME_HINT_RE.search(hints) and re.search(r"[\u4e00-\u9fff]", stripped):
            probes.append(("Name: ", {"PERSON"}))
        if PHONE_HINT_RE.search(hints) or DIGIT_HEAVY_RE.search(stripped):
            probes.append(("Phone number: ", {"PHONE_NUMBER"}))
        return probes

    @staticmethod
    def _iter_nonempty_lines(text: str):
        cursor = 0
        for raw_line in text.splitlines(keepends=True):
            line = raw_line.rstrip("\r\n")
            leading_spaces = len(line) - len(line.lstrip())
            stripped = line.strip()
            if stripped:
                yield stripped, cursor + leading_spaces
            cursor += len(raw_line)

    @staticmethod
    def _find_probe_value_offset(line: str, value: str) -> int | None:
        if not value:
            return None
        index = line.find(value)
        if index >= 0:
            return index
        compact_line = re.sub(r"\s+", "", line)
        compact_value = re.sub(r"\s+", "", value)
        if compact_value and compact_value in compact_line:
            return line.find(value.strip()[0])
        return None

    @staticmethod
    def _deduplicate_matches(matches: list[dict]) -> list[dict]:
        deduplicated: list[dict] = []
        seen: set[tuple[int, int, str, str]] = set()
        for match in sorted(matches, key=lambda item: (item["start"], item["end"], item["type"])):
            key = (match["start"], match["end"], match["type"], match["original"])
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(match)
        return deduplicated

    def _build_scanner(self):
        from opf import OPF

        return OPF(
            model=str(self.model_path),
            context_window_length=self.context_window_length,
            device=self.device,
            output_mode=self.output_mode,
            decode_mode=self.decode_mode,
        )

    def _ensure_checkpoint(self) -> None:
        if self._is_valid_checkpoint(self.model_path):
            return
        if not self.auto_download:
            raise RuntimeError(
                f"Privacy Filter checkpoint is missing at {self.model_path}; "
                "set PRIVACY_FILTER_AUTO_DOWNLOAD=true to download it."
            )
        self.model_path.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=PRIVACY_FILTER_REPO_ID,
                local_dir=str(self.model_path),
                allow_patterns=["original/*"],
                local_dir_use_symlinks=False,
            )
            self._promote_original_subtree(self.model_path)
        except Exception as exc:
            raise RuntimeError(
                f"Privacy Filter checkpoint download failed for {PRIVACY_FILTER_REPO_ID}: {exc}"
            ) from exc
        if not self._is_valid_checkpoint(self.model_path):
            raise RuntimeError(f"Privacy Filter checkpoint is incomplete at {self.model_path}.")

    @staticmethod
    def _is_valid_checkpoint(path: Path) -> bool:
        return path.is_dir() and (path / "config.json").is_file() and any(path.glob("*.safetensors"))

    @staticmethod
    def _resolve_model_path(value: str) -> Path:
        path = Path(value or "").expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()

    @staticmethod
    def _promote_original_subtree(target: Path) -> None:
        original_dir = target / "original"
        if not original_dir.is_dir():
            return
        for path in original_dir.iterdir():
            destination = target / path.name
            if destination.exists():
                continue
            shutil.move(str(path), str(destination))
        try:
            original_dir.rmdir()
        except OSError:
            logger.debug("Privacy Filter original checkpoint directory was not empty after promotion.")

    @staticmethod
    def _resolve_device(value: str) -> Literal["cpu", "cuda"]:
        normalized = (value or "auto").strip().lower()
        if normalized == "cuda":
            return "cuda"
        # Keep OPF on CPU by default. Qwen3Guard owns the local GPU lane and
        # Windows OPF CUDA execution additionally requires Triton MoE kernels.
        return "cpu"

    @staticmethod
    def _resolve_decode_mode(value: str) -> Literal["viterbi", "argmax"]:
        normalized = (value or "viterbi").strip().lower()
        if normalized in {"viterbi", "argmax"}:
            return normalized
        logger.warning("Invalid PRIVACY_FILTER_DECODE_MODE=%s; using viterbi.", value)
        return "viterbi"

    @staticmethod
    def _resolve_output_mode(value: str) -> Literal["typed", "redacted"]:
        normalized = (value or "typed").strip().lower()
        if normalized in {"typed", "redacted"}:
            return normalized
        logger.warning("Invalid PRIVACY_FILTER_OUTPUT_MODE=%s; using typed.", value)
        return "typed"
