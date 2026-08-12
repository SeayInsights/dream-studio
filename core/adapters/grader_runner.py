"""Provider-neutral grader / live-eval runner (WO-GRADER-PROVIDER-NEUTRAL).

The verification plane — the mechanism the whole accountability claim rests on — must
not hardcode one vendor's CLI. Both `core/work_orders/verify_graders.py` (WO verify
graders) and `core/eval/runner_process.py` (live-mode evals) previously spawned
`["claude", "--print"]` literally. This module resolves the spawn argv from a provider
*profile* and owns the subprocess spawn, so a flag change in one vendor's CLI no longer
breaks verification and evals simultaneously.

Profile shape (a plain dict; the backing table + per-role selection land in
WO-GRADER-PROFILE-REGISTRY — this module only consumes a resolved profile)::

    {
      "command": "claude",              # executable
      "print_flag": "--print",          # non-interactive one-shot flag (optional)
      "model_flag": "--model",          # optional; omit if the provider takes no model flag
      "output_format_flag": "--output-format",  # optional
      "prompt_via": "stdin" | "argv",   # how the prompt is delivered
      "extra_args": [...],              # optional trailing args
    }

Resolution precedence (highest first):
  1. an explicit ``profile`` argument (from the registry / per-role selection)
  2. ``DS_GRADER_STUB`` — a path to a stub grader script, run via the current
     interpreter. Lets verify + evals run headlessly (CI, or any host without a
     vendor CLI) and is how the conformance suite swaps in a second provider.
  3. ``DS_GRADER_ARGV`` — an operator override, shlex-split into the base argv.
  4. the default vendor profile (the ``claude`` CLI) — preserves prior behavior.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from typing import Any

_STUB_ENV = "DS_GRADER_STUB"
_ARGV_ENV = "DS_GRADER_ARGV"

# The historical default: the claude CLI, prompt fed on stdin for the WO graders.
_DEFAULT_PROFILE: dict[str, Any] = {
    "command": "claude",
    "print_flag": "--print",
    "model_flag": "--model",
    "output_format_flag": "--output-format",
    "prompt_via": "stdin",
}


def resolve_profile(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the provider profile to use, honoring the resolution precedence."""
    if profile:
        return profile
    stub = os.environ.get(_STUB_ENV)
    if stub:
        # A stub is run via the current interpreter and reads the prompt from stdin
        # (WO graders) or, in argv mode, as a trailing arg. It ignores model/format
        # flags it does not understand.
        return {
            "command": sys.executable,
            "base_args": [stub],
            "prompt_via": "stdin",
            "is_stub": True,
        }
    override = os.environ.get(_ARGV_ENV)
    if override:
        parts = shlex.split(override)
        return {"command": parts[0], "base_args": parts[1:], "prompt_via": "stdin"}
    return dict(_DEFAULT_PROFILE)


def resolve_grader_argv(
    profile: dict[str, Any] | None = None,
    *,
    prompt: str | None = None,
    model: str | None = None,
    output_format: str | None = None,
) -> list[str]:
    """Resolve the full spawn argv from a provider profile.

    ``prompt`` is appended only when the profile delivers the prompt via argv
    (``prompt_via == "argv"``); stdin-delivered prompts never appear in argv (a real
    diff exceeds Windows' ~32K command-line limit — WinError 206).
    """
    p = resolve_profile(profile)
    argv: list[str] = [p["command"], *p.get("base_args", [])]
    print_flag = p.get("print_flag")
    if print_flag:
        argv.append(print_flag)
    # The model comes from the explicit `model` arg (live-eval) or the profile's
    # own `model_id` (WO-GRADER-PROFILE-REGISTRY: profiles carry the model to request).
    effective_model = model or p.get("model_id")
    if effective_model and p.get("model_flag"):
        argv += [p["model_flag"], effective_model]
    if output_format and p.get("output_format_flag"):
        argv += [p["output_format_flag"], output_format]
    argv += list(p.get("extra_args", []))
    if prompt is not None and p.get("prompt_via") == "argv":
        argv.append(prompt)
    return argv


def spawn_grader(prompt: str, profile: dict[str, Any] | None = None) -> subprocess.Popen:  # type: ignore[type-arg]
    """Spawn a grader for the WO-verify path, feeding the prompt via stdin.

    The prompt is NEVER an argv element (large diffs overflow the Windows cmdline).
    Stdin is written from a daemon thread so all graders start consuming in parallel.
    """
    argv = resolve_grader_argv(profile)
    proc = subprocess.Popen(
        argv,
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
            pass  # broken pipe → grader died; the collector surfaces it

    feeder = threading.Thread(target=_feed, daemon=True)
    feeder.start()
    proc._ds_feeder = feeder  # type: ignore[attr-defined]
    return proc


def run_generation(
    prompt: str,
    *,
    model: str | None = None,
    output_format: str | None = None,
    timeout: int = 120,
    profile: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """One-shot generation for the live-eval path.

    Delivers the prompt per the profile (argv by default for the CLI generation
    shape; stdin for stub profiles) and returns the CompletedProcess.
    """
    p = resolve_profile(profile)
    prompt_via = p.get("prompt_via", "argv")
    argv = resolve_grader_argv(
        p,
        prompt=prompt if prompt_via == "argv" else None,
        model=model,
        output_format=output_format,
    )
    stdin_data = prompt if prompt_via == "stdin" else None
    return subprocess.run(
        argv,
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def grader_provider_available(profile: dict[str, Any] | None = None) -> bool:
    """True if the provider is invocable. Checks the profile's ``availability_probe``
    (WO-GRADER-PROFILE-REGISTRY min field) when present, else the command: a PATH name
    resolves via which, an absolute path via exists. Used to fail closed / mark
    unreviewable rather than crash when the provider is absent (CI, or any host without it)."""
    import shutil

    p = resolve_profile(profile)
    probe = p.get("availability_probe") or p["command"]
    if os.path.isabs(probe):
        return os.path.exists(probe)
    return shutil.which(probe) is not None
