"""Gate-bypass event emission (WO-BYPASS-TELEMETRY).

Every gate escape hatch leaves a mark: acknowledgment env vars
(MIGRATION_RISK_ACKNOWLEDGED), review-trailer consumption
(Docs-Reviewed-No-Change), and force-closes all record a ``gate.bypassed``
canonical event so ``ds doctor`` / ``ds project state`` can answer "which
hatches fired, and how often". Best-effort by contract — a broken emit path
never changes a gate outcome.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: A launcher that STARTED the gate declares itself here. The gate cannot tell, from the
#: inside, whether a git hook, a runner or an operator started it, so it reads a
#: declaration and otherwise says what it can see -- never a guess.
INVOCATION_ENV = "DREAM_STUDIO_GATE_INVOCATION"

#: The values a launcher may declare. Anything else in the variable is ignored, so a stray
#: ambient value cannot put an unvalidated string into the ledger.
DECLARED_INVOCATIONS = frozenset({"pre_push_hook", "pre_push_runner", "ci_gate"})


def invocation() -> str:
    """Who started this gate run: a declared launcher, else what the environment shows.

    ``pre_push_hook`` (hooks/git/pre-push), ``pre_push_runner`` (core.gates.pre_push run
    without the hook: ``ds workflow run pre-push`` or ``py -m core.gates.pre_push``) and
    ``ci_gate`` (interfaces/cli/ci_gate.py) are declared by those launchers. Undeclared:
    ``github_actions`` when GITHUB_ACTIONS is set, otherwise ``direct`` -- the gate was
    run on its own, by an operator or a script, and nothing says which.
    """
    declared = os.environ.get(INVOCATION_ENV, "")
    if declared in DECLARED_INVOCATIONS:
        return declared
    if os.environ.get("GITHUB_ACTIONS"):
        return "github_actions"
    return "direct"


def _git(repo_root: Path, *args: str) -> str | None:
    """Stdout of a read-only ``git <args>``, or None when it failed or printed nothing."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        result = None  # no git, or it hung: reported as absent below, not as an answer
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def run_context(repo_root: Path, base_ref: str | None) -> dict[str, Any]:
    """Which run of which tree a gate bypass belongs to.

    ``branch`` is None on a detached HEAD and every git-derived field is None when git
    cannot answer: an absent value is recorded as absent, never filled in. ``base_sha`` is
    what ``base_ref`` pointed at when the gate ran (refs move; the name alone cannot say).
    """
    return {
        "branch": _git(repo_root, "symbolic-ref", "--short", "-q", "HEAD"),
        "head_sha": _git(repo_root, "rev-parse", "HEAD"),
        "base_ref": base_ref,
        "base_sha": (
            _git(repo_root, "rev-parse", "--verify", "-q", f"{base_ref}^{{commit}}")
            if base_ref
            else None
        ),
        "invocation": invocation(),
    }


def record_gate_bypass(gate: str, reason: str, extra: dict[str, Any] | None = None) -> None:
    """Emit a ``gate.bypassed`` spool event for a non-force gate escape hatch.

    Mirrors the force-close emission in ``close_main`` (same event type, same
    business-canonical routing) so ``bypass_report`` aggregates both families.
    """
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        payload: dict[str, Any] = {"gate": gate, "reason": reason}
        if extra:
            payload.update(extra)
        envelope = CanonicalEventEnvelope(
            event_type="gate.bypassed",
            session_id=None,
            payload=payload,
            timestamp=datetime.now(UTC).isoformat(),
            severity="warning",
            trace={"domain": "sdlc", "attribution_status": "unattributed"},
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass  # never let telemetry change a gate outcome
