"""Parallel LLM grader execution for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
subprocess-based grader spawning (via the provider-neutral runner), JSON-object
extraction from grader output, per-grader collection with retry, and the parallel
grader-set runner (mock-mode aware).

WO-GRADER-PROVIDER-NEUTRAL / -PROFILE-REGISTRY: the spawn provider is NOT hardcoded
here. Each grader role resolves its own provider profile via
``config.grader_profiles.resolve_grader_profile(role)`` and spawns through
``core.adapters.grader_runner`` — so which provider grades which role is config-driven
and inspectable (``describe_grader_selection``).
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


def _spawn_grader(prompt: str, profile: dict[str, Any] | None = None) -> subprocess.Popen:  # type: ignore[type-arg]
    """Spawn a grader, feeding the prompt via stdin.

    The spawn argv is resolved by the provider-neutral ``core.adapters.grader_runner``
    from the given per-role provider ``profile`` (see
    ``config.grader_profiles.resolve_grader_profile``) — never a hardcoded vendor CLI.
    The prompt is delivered on stdin, never as an argv element (a real diff would
    overflow the Windows ~32K cmdline, WinError 206), written from a daemon thread so
    graders consume in parallel.
    """
    from core.adapters.grader_runner import spawn_grader

    return spawn_grader(prompt, profile)


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

    # Spawn each grader through its per-role provider profile
    # (config.grader_profiles.resolve_grader_profile). When the resolved provider is
    # absent (CI, or any host without it) Popen raises FileNotFoundError, and an
    # unresolvable role raises UnresolvableGraderProfile — treat either as unreviewable
    # rather than aborting the whole verify (the post-merge main-red on WO-FIX-VERIFY-GATE).
    # It flows through the existing unreviewable path (no false-done: unreviewable never
    # certifies).
    from config.grader_profiles import UnresolvableGraderProfile, resolve_grader_profile

    procs: dict[str, subprocess.Popen[str] | None] = {}
    profiles: dict[str, dict[str, Any] | None] = {}
    for name, prompt in prompts.items():
        try:
            profiles[name] = resolve_grader_profile(name)
            procs[name] = _spawn_grader(prompt, profiles[name])
        except (FileNotFoundError, UnresolvableGraderProfile):
            procs[name] = None
            profiles[name] = None
    results: dict[str, dict[str, Any]] = {}
    for name, proc in procs.items():
        if proc is None:
            results[name] = {
                "unreviewable": True,
                "reason": "grader_cli_unavailable",
                "_grader_error": "grader provider not available on this host",
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
                retry_proc = _spawn_grader(prompts[name], profiles.get(name))
                retry_result = _collect_grader(retry_proc, timeout=60)
                if not retry_result.get("unreviewable") and not retry_result.get("_grader_error"):
                    result = retry_result
            except Exception:
                pass  # keep original result on retry failure
        results[name] = result
    return results
