from __future__ import annotations

import argparse
import os
import json
import statistics
import time

from app.services.guardrails.privacy_filter_scanner import PrivacyFilterScanner
from app.services.guardrails.qwen3guard_scanner import Qwen3GuardScanner


SAMPLE = "请用一句话解释企业 AI 安全网关的作用。"


def process_rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1)
    except Exception:
        pass
    proc_status = f"/proc/{os.getpid()}/status"
    if os.path.exists(proc_status):
        with open(proc_status, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / 1024 / 1024, 1)
        except Exception:
            return None
    return None


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
    qwen_rss_mb = process_rss_mb()

    privacy = PrivacyFilterScanner()
    started = time.perf_counter()
    privacy.warmup()
    privacy_warmup_ms = round((time.perf_counter() - started) * 1000, 3)
    combined_rss_mb = process_rss_mb()

    report = {
        "samples": samples,
        "qwen3guard": {
            "device": qwen.runtime_device,
            "warmup_ms": qwen_warmup_ms,
            "process_rss_after_warmup_mb": qwen_rss_mb,
            **summarize(measure(lambda: qwen.scan_prompt(SAMPLE), samples)),
        },
        "privacy_filter": {
            "device": privacy.device,
            "warmup_ms": privacy_warmup_ms,
            "combined_process_rss_mb": combined_rss_mb,
            **summarize(measure(lambda: privacy.scan(SAMPLE), samples)),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
