from __future__ import annotations

import argparse
import json
import statistics
import time

from app.services.guardrails.privacy_filter_scanner import PrivacyFilterScanner
from app.services.guardrails.qwen3guard_scanner import Qwen3GuardScanner


SAMPLE = "请用一句话解释企业 AI 安全网关的作用。"


def measure(operation, samples: int) -> list[float]:
    durations: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        durations.append(round((time.perf_counter() - started) * 1000, 3))
    return durations


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * ratio), len(ordered) - 1)
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    samples = max(args.samples, 1)

    qwen = Qwen3GuardScanner()
    started = time.perf_counter()
    qwen.warmup()
    qwen_warmup_ms = round((time.perf_counter() - started) * 1000, 3)

    privacy = PrivacyFilterScanner()
    started = time.perf_counter()
    privacy.warmup()
    privacy_warmup_ms = round((time.perf_counter() - started) * 1000, 3)

    report = {
        "samples": samples,
        "qwen3guard": {
            "device": qwen.runtime_device,
            "warmup_ms": qwen_warmup_ms,
            **summarize(measure(lambda: qwen.scan_prompt(SAMPLE), samples)),
        },
        "privacy_filter": {
            "device": privacy.device,
            "warmup_ms": privacy_warmup_ms,
            **summarize(measure(lambda: privacy.scan(SAMPLE), samples)),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
