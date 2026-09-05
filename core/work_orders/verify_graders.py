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
    _MOCK_FALSIFICATION,
    _MOCK_MIGRATION,
    _MOCK_QUALITY,
    validate_grader_verdict,
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


# WO-FALSIFY-TIMEOUT: per-role collect budgets. The narrow-scope roles grade a
# diff against a fixed rule list; the falsification analyst has to reason over the
# WHOLE diff and enumerate worst reachable states per surface, so it needs a longer
# window. Its first live run timed out at the shared 360s on an ordinary multi-file
# diff — a grader that cannot finish on realistic input is dead capability exactly
# where the worst cases matter most.
_DEFAULT_COLLECT_TIMEOUT = 360
_ROLE_COLLECT_TIMEOUTS: dict[str, int] = {"falsification": 900}
# A retry after a transient miss gets a shorter window (the first call already
# consumed the operator's patience); still per-role so falsification can finish.
_DEFAULT_RETRY_TIMEOUT = 60
_ROLE_RETRY_TIMEOUTS: dict[str, int] = {"falsification": 300}

# Operator rule: run up to 20 attempts looking for one clean verdict.
#
# There was exactly ONE retry, and a timeout is what most often needs another. Measured
# across one session: four timeouts to one success, every one at the 360s collect budget,
# and each left a work order uncloseable behind an `independent_review: unreviewable`
# gate. A single retry on a flaky provider is not a retry policy, it is a coin flip.
_MAX_GRADER_ATTEMPTS = 20

# A TIMEOUT keeps the FULL budget on every attempt. The retry budget exists for a
# formatting flake, where the model answered promptly with the wrong shape and a short
# second look suffices. Applying it to a timeout is backwards: the call ran out of time,
# so the retry was handed LESS time (60s against the 360s that already expired) and was
# near-certain to expire too. That inversion is why four timeouts in a row never
# recovered.
_TIMEOUT_MARKERS = ("timed out", "TimeoutExpired", "timeout")


def role_collect_timeout(role: str | None) -> int:
    """Collect budget for a grader role (see _ROLE_COLLECT_TIMEOUTS)."""
    return _ROLE_COLLECT_TIMEOUTS.get(role or "", _DEFAULT_COLLECT_TIMEOUT)


def role_retry_timeout(role: str | None) -> int:
    """Retry budget for a grader role (see _ROLE_RETRY_TIMEOUTS)."""
    return _ROLE_RETRY_TIMEOUTS.get(role or "", _DEFAULT_RETRY_TIMEOUT)


def _collect_grader(proc: subprocess.Popen, timeout: int = _DEFAULT_COLLECT_TIMEOUT) -> dict[str, Any]:  # type: ignore[type-arg]
    try:
        feeder = getattr(proc, "_ds_feeder", None)
        if feeder is not None:
            feeder.join(timeout=120)
            # The feeder thread already wrote AND closed proc.stdin. Detach it so
            # communicate() does not touch stdin again: on posix, communicate() flushes
            # self.stdin, and flushing an already-closed pipe raises
            # ValueError("I/O operation on closed file") — which turned every grader-spawn
            # test red on Linux full-ci while Windows' thread-based communicate() tolerated
            # it. Nulling stdin makes communicate() skip stdin entirely (WO-MAINRED-GRADER-IO).
            proc.stdin = None
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


def _should_retry(result: dict[str, Any]) -> bool:
    """A grader miss is retryable when it is unreviewable (empty output) OR non-JSON
    (_grader_error) — both are transient LLM formatting flakes a fresh call usually
    resolves. A structurally-absent CLI (grader_cli_unavailable) is NOT retryable: a
    re-spawn cannot conjure a missing binary."""
    needs = result.get("unreviewable") or result.get("_grader_error")
    return bool(needs) and result.get("reason") != "grader_cli_unavailable"


def _retry_grader_once(
    prompt: str,
    profile: dict[str, Any] | None,
    *,
    timeout: int = _DEFAULT_RETRY_TIMEOUT,
) -> dict[str, Any] | None:
    """Re-spawn + collect one grader once; return the clean retry verdict, or None if the
    retry also missed. The single shared retry step (WO-GRADER-RETRY-NONJSON) used by both
    the parallel WO-verify path and the conformance suite so they exercise identical retry
    semantics (gap 2bbed8d8)."""
    try:
        retry_proc = _spawn_grader(prompt, profile)
        retry_result = _collect_grader(retry_proc, timeout=timeout)
        if not retry_result.get("unreviewable") and not retry_result.get("_grader_error"):
            return retry_result
    except Exception:
        pass  # keep the caller's original result on retry failure
    return None


def collect_grader_with_retry(
    prompt: str, profile: dict[str, Any] | None = None, *, role: str | None = None
) -> dict[str, Any]:
    """Spawn one grader, collect it, and apply the single transient-miss retry.

    The retry-owning code path the conformance suite drives (gap 2bbed8d8): a non-JSON
    first reply is re-spawned once and only a clean retry replaces it. Shares
    ``_retry_grader_once`` with the parallel WO-verify path so both retry identically.
    ``role`` selects the per-role collect/retry budget (WO-FALSIFY-TIMEOUT) so this
    path and the parallel path give a role the same window.
    """
    try:
        proc = _spawn_grader(prompt, profile)
    except FileNotFoundError:
        return {
            "unreviewable": True,
            "reason": "grader_cli_unavailable",
            "_grader_error": "grader provider not available on this host",
        }
    try:
        result = _collect_grader(proc, timeout=role_collect_timeout(role))
    except Exception as exc:
        result = {"_grader_error": str(exc)}

    # Up to _MAX_GRADER_ATTEMPTS looking for one clean verdict, rather than the single
    # retry this had. The budget for each attempt depends on HOW the previous one missed:
    # a timeout gets the full collect window again, because it ran out of time and handing
    # it less is the inversion that made four consecutive timeouts unrecoverable; a
    # formatting flake gets the shorter retry window, which is what that budget is for.
    attempts = 1
    while _should_retry(result) and attempts < _MAX_GRADER_ATTEMPTS:
        timed_out = any(m in str(result.get("_grader_error", "")) for m in _TIMEOUT_MARKERS)
        budget = role_collect_timeout(role) if timed_out else role_retry_timeout(role)
        retry = _retry_grader_once(prompt, profile, timeout=budget)
        attempts += 1
        if retry is not None:
            result = retry
            break

    # Say how many attempts it took. A verdict that needed 11 tries and one that landed
    # first time are different facts about provider health, and collapsing them hides a
    # degrading provider until it fails outright.
    if attempts > 1:
        result = dict(result)
        result["grader_attempts"] = attempts
    return result


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
        if "falsification" in prompts:
            mocks["falsification"] = _MOCK_FALSIFICATION.copy()
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
            result = _collect_grader(proc, timeout=role_collect_timeout(name))
        except Exception as exc:
            # Grader failure is non-fatal; return a safe default so the rest proceeds.
            result = {"_grader_error": str(exc)}
        # Retry once on a transient grader miss — empty output (unreviewable) OR
        # non-JSON output (_grader_error, e.g. the grader replied in prose). Both
        # are LLM formatting flakes a fresh call usually resolves; without the
        # non-JSON retry a prose reply defaults the score to 0.0 and false-FAILs
        # the WO (WO-GRADER-RETRY-NONJSON — WO-GAP-DEDUPE-CLASS needed 3 manual
        # verify runs). The retry step is shared with the conformance suite so both
        # paths retry identically (gap 2bbed8d8).
        # SAME POLICY AS THE SERIAL PATH. This had a single retry while
        # collect_grader_with_retry gained twenty, and THIS is the path a live
        # `ds work-order verify` takes -- so fixing only the other one would have left
        # every real verify on one coin flip. Fixed-in-one-branch-not-its-sibling is the
        # shape this session found four times; the loop is written out here rather than
        # shared only because the two paths carry different per-grader state.
        attempts = 1
        while _should_retry(result) and attempts < _MAX_GRADER_ATTEMPTS:
            timed_out = any(m in str(result.get("_grader_error", "")) for m in _TIMEOUT_MARKERS)
            budget = role_collect_timeout(name) if timed_out else role_retry_timeout(name)
            retry = _retry_grader_once(prompts[name], profiles.get(name), timeout=budget)
            attempts += 1
            if retry is not None:
                result = retry
                break
        if attempts > 1:
            result = dict(result)
            result["grader_attempts"] = attempts
        # gap 0a64cf8c: check real-mode grader output against the published per-role
        # contract in the LIVE path (not only in tests). Observability only — the
        # errors are attached as evidence; scoring keeps its own fallbacks so a
        # score-less-but-scorable verdict (e.g. {"passed": true}) is not rejected here.
        if not result.get("unreviewable") and not result.get("_grader_error"):
            schema_errors = validate_grader_verdict(result, role=name)
            if schema_errors:
                result["_schema_errors"] = schema_errors
        results[name] = result
    return results
