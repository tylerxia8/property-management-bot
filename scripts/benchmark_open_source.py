"""Local synthetic measurements, not portfolio accuracy or production load."""

import hashlib
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from grok_bot.domain.listing_match import resolve_hint
from grok_bot.domain.media_scan import sha256_file


def peak(call):
    tracemalloc.start()
    result = call()
    _, memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, memory


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic-upload"
        with path.open("wb") as handle:
            for _ in range(16):
                handle.write(b"x" * 1024 * 1024)
        original, original_peak = peak(lambda: hashlib.sha256(path.read_bytes()).hexdigest())
        streamed, streamed_peak = peak(lambda: sha256_file(path))
        assert original == streamed
    rows = [{"id": str(i), "display_label": f"{i} Elm Street"} for i in range(1, 1001)]
    elapsed = []
    for _ in range(100):
        started = time.perf_counter()
        result = resolve_hint("Elmm Street", rows)
        elapsed.append((time.perf_counter() - started) * 1000)
        assert result["match"] is None and "Possible listings" in result["clarification"]
    print(json.dumps({
        "input_mib": 16,
        "whole_file_hash_peak_bytes": original_peak,
        "streamed_hash_peak_bytes": streamed_peak,
        "hash_peak_reduction_percent": round(100 * (1 - streamed_peak / original_peak), 1),
        "listing_candidates": 1000,
        "iterations": 100,
        "listing_suggestion_p50_ms": round(statistics.median(elapsed), 3),
        "listing_suggestion_p95_ms": round(sorted(elapsed)[94], 3),
    }, indent=2))


if __name__ == "__main__":
    main()
