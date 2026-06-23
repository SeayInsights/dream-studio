#!/usr/bin/env python
"""
Benchmark script for EventNormalizer adapter overhead.

Tests adapter normalization performance across 1000 events per adapter type.
Target: <10ms average overhead per event (CONSTITUTION.md requirement).

Usage:
    py scripts/benchmark_normalizer.py
"""

import time
from datetime import datetime, UTC
from typing import Any

from core.adapters.normalizers import EventNormalizer


def mock_claude_response() -> dict[str, Any]:
    """Generate realistic Claude API response."""
    return {
        "id": f"msg_{int(time.time() * 1000)}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello, world!"}],
        "model": "claude-sonnet-4.5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def mock_gpt_response() -> dict[str, Any]:
    """Generate realistic GPT API response."""
    return {
        "id": f"chatcmpl_{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello, world!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


def mock_default_response() -> dict[str, Any]:
    """Generate generic API response."""
    return {
        "response": "Hello, world!",
        "metadata": {"timestamp": datetime.now(UTC).isoformat()},
    }


def benchmark_adapter(
    adapter_name: str, raw_output: Any, iterations: int = 1000
) -> tuple[float, float]:
    """
    Benchmark single adapter normalization.

    Args:
        adapter_name: Name of adapter to test
        raw_output: Mock API response to normalize
        iterations: Number of iterations to run

    Returns:
        Tuple of (total_time_ms, avg_time_ms)
    """
    normalizer = EventNormalizer()

    # Warm-up run (JIT compilation, etc.)
    normalizer.normalize(raw_output, adapter_name)

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        event = normalizer.normalize(raw_output, adapter_name)
        # Validate event to ensure full normalization path is exercised
        event.validate()
    end = time.perf_counter()

    total_ms = (end - start) * 1000
    avg_ms = total_ms / iterations

    return total_ms, avg_ms


def main():
    """Run full benchmark suite."""
    print("=" * 80)
    print("EventNormalizer Performance Benchmark")
    print("=" * 80)
    print("Target: <10ms average overhead per event (CONSTITUTION.md)")
    print("Iterations per adapter: 1000")
    print()

    results = []

    # Benchmark ClaudeAdapter
    print("[1/3] Benchmarking ClaudeAdapter...")
    total, avg = benchmark_adapter("claude", mock_claude_response())
    results.append(("ClaudeAdapter", total, avg))
    print(f"  Total: {total:.2f}ms | Average: {avg:.4f}ms")

    # Benchmark GPTAdapter
    print("[2/3] Benchmarking GPTAdapter...")
    total, avg = benchmark_adapter("gpt", mock_gpt_response())
    results.append(("GPTAdapter", total, avg))
    print(f"  Total: {total:.2f}ms | Average: {avg:.4f}ms")

    # Benchmark DefaultAdapter
    print("[3/3] Benchmarking DefaultAdapter...")
    total, avg = benchmark_adapter("unknown", mock_default_response())
    results.append(("DefaultAdapter", total, avg))
    print(f"  Total: {total:.2f}ms | Average: {avg:.4f}ms")

    # Summary
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"{'Adapter':<20} {'Total (ms)':<15} {'Avg (ms)':<15} {'Status':<10}")
    print("-" * 80)

    all_pass = True
    for adapter, total, avg in results:
        status = "PASS" if avg < 10.0 else "FAIL"
        if avg >= 10.0:
            all_pass = False
        print(f"{adapter:<20} {total:<15.2f} {avg:<15.4f} {status:<10}")

    print("=" * 80)
    if all_pass:
        print("SC-C5 VERIFIED: All adapters meet <10ms overhead requirement")
    else:
        print("SC-C5 FAILED: One or more adapters exceed 10ms overhead")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
