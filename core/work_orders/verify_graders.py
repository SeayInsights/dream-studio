"""Parallel LLM grader execution for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
subprocess-based grader spawning (``claude --print``), JSON-object extraction
from grader output, per-grader collection with retry, and the parallel
grader-set runner (mock-mode aware). No logic changes — extracted verbatim
from the original module.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from .verify_shared import (
    _MOCK_COMPLETION,
    _MOCK_CORRECTNESS,
    _MOCK_ENV,
    _MOCK_MIGRATION,
    _MOCK_QUALITY,
)

# ── Parallel grader execution ───────────────────────────────────────────────────


def _spawn_grader(prompt: str) -> subprocess.Popen:  # type: ignore[type-arg]
    """Spawn a grader, feeding the prompt via stdin.

    The prompt must NOT be passed as an argv element: with a real diff it
    routinely exceeds Windows' ~32K command-line limit and CreateProcess fails
    with WinError 206 (found re-verifying WO-DEBT-I under WO-GRADER-LOOKUP).
    Stdin is written from a daemon thread so all graders start consuming
    immediately and in parallel — a 64K pipe buffer would otherwise block the
    spawn loop on large prompts.
    """
    import threading

    proc = subprocess.Popen(
        ["claude", "--print"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _feed() -> None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            pass  # broken pipe → grader died; _collect_grader surfaces it

    feeder = threading.Thread(target=_feed, daemon=True)
    feeder.start()
    # _collect_grader joins this before communicate() — communicate() closes
    # stdin, which would otherwise race a still-writing feeder and silently
    # truncate the prompt.
    proc._ds_feeder = feeder  # type: ignore[attr-defined]
    return proc


def _extract_first_json_object(text: str) -> str | None:
    """Return the first balanced top-level JSON object substring, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]  # noqa: E203
    return None


def _collect_grader(proc: subprocess.Popen, timeout: int = 360) -> dict[str, Any]:  # type: ignore[type-arg]
    try:
        feeder = getattr(proc, "_ds_feeder", None)
        if feeder is not None:
            feeder.join(timeout=120)
        stdout, _ = proc.communicate(timeout=timeout)
        output = stdout.strip()
        # T1: empty/whitespace-only output → unreviewable, not a hard failure.
        # Graders sometimes return nothing when the model is busy or the prompt
        # is truncated — treat as unreviewable so close_work_order is not blocked.
        if not output:
            return {"unreviewable": True, "reason": "grader_no_summary"}
        # Strip leading/trailing fences when the entire output is a fenced block.
        if output.startswith("```"):
            lines = output.splitlines()
            output = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()
        # Fast path: clean JSON.
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass
        # Slow path: prose prefix or trailing text — extract first balanced object.
        candidate = _extract_first_json_object(output)
        if candidate is not None:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Grader returned non-JSON.\nRaw:\n{stdout[:500]}")
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Grader failed: {exc}")


def _run_graders_parallel(
    prompts: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Spawn all graders in parallel via Popen, collect results."""
    if os.environ.get(_MOCK_ENV):
        mocks: dict[str, dict[str, Any]] = {
            "completion": _MOCK_COMPLETION.copy(),
            "correctness": _MOCK_CORRECTNESS.copy(),
            "quality": _MOCK_QUALITY.copy(),
        }
        if "migration" in prompts:
            mocks["migration"] = _MOCK_MIGRATION.copy()
        return mocks

    # Spawn each grader. When the `claude` CLI is absent (CI, or any host without
    # it), Popen raises FileNotFoundError — treat that grader as unreviewable
    # rather than letting the exception abort the whole verify (the post-merge
    # main-red on WO-FIX-VERIFY-GATE). It then flows through the existing
    # unreviewable-graders path (no false-done: unreviewable never certifies).
    procs: dict[str, subprocess.Popen[str] | None] = {}
    for name, prompt in prompts.items():
        try:
            procs[name] = _spawn_grader(prompt)
        except FileNotFoundError:
            procs[name] = None
    results: dict[str, dict[str, Any]] = {}
    for name, proc in procs.items():
        if proc is None:
            results[name] = {
                "unreviewable": True,
                "reason": "grader_cli_unavailable",
                "_grader_error": "claude CLI not found on this host",
            }
            continue
        try:
            result = _collect_grader(proc)
        except Exception as exc:
            # Grader failure is non-fatal; return a safe default so the rest proceeds.
            result = {"_grader_error": str(exc)}
        # Retry once on a transient grader miss — empty output (unreviewable) OR
        # non-JSON output (_grader_error, e.g. the grader replied in prose). Both
        # are LLM formatting flakes a fresh call usually resolves; without the
        # non-JSON retry a prose reply defaults the score to 0.0 and false-FAILs
        # the WO (WO-GRADER-RETRY-NONJSON — WO-GAP-DEDUPE-CLASS needed 3 manual
        # verify runs). Skip when the CLI is simply absent (grader_cli_unavailable)
        # — a re-spawn cannot recover that. Accept the retry only if it is clean.
        needs_retry = result.get("unreviewable") or result.get("_grader_error")
        if needs_retry and result.get("reason") != "grader_cli_unavailable":
            try:
                retry_proc = _spawn_grader(prompts[name])
                retry_result = _collect_grader(retry_proc, timeout=60)
                if not retry_result.get("unreviewable") and not retry_result.get("_grader_error"):
                    result = retry_result
            except Exception:
                pass  # keep original result on retry failure
        results[name] = result
    return results
