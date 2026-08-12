"""Mock grader fixtures shared by verify siblings.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
``DREAM_STUDIO_VERIFY_MOCK`` env-var name and the deterministic mock fixtures
substituted for the real graders in CI. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MOCK_ENV = "DREAM_STUDIO_VERIFY_MOCK"

# ── Grader I/O contract (WO-VERIFY-CONFORMANCE) ─────────────────────────────────
#
# The grader verdict schema is the published, provider-neutral I/O contract: any
# provider whose output validates against it can back the graders. This turns
# "portable in principle" (WO-GRADER-PROVIDER-NEUTRAL) into a checkable claim.

_GRADER_VERDICT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "grader_verdict.schema.json"
)

# The fixed prompt the conformance suite feeds a provider. A conformant provider
# returns ONLY a JSON grader verdict (a *_score in [0,1]).
_CONFORMANCE_PROMPT = (
    "You are a Dream Studio verification grader. Respond with ONLY a JSON object "
    'matching the grader verdict contract, e.g. {"completion_score": 1.0, '
    '"summary": "...", "gaps": []}. No prose outside the JSON.'
)


def grader_verdict_schema() -> dict[str, Any]:
    """Load the published grader verdict I/O-contract schema."""
    return json.loads(_GRADER_VERDICT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_grader_verdict(verdict: Any) -> list[str]:
    """Return schema-validation error messages for a grader verdict ([] == conformant)."""
    import jsonschema

    if not isinstance(verdict, dict):
        return [f"verdict is not a JSON object (got {type(verdict).__name__})"]
    validator = jsonschema.Draft202012Validator(grader_verdict_schema())
    return [e.message for e in validator.iter_errors(verdict)]


def run_grader_conformance(
    profile: dict[str, Any] | None = None, *, prompt: str | None = None
) -> dict[str, Any]:
    """Run one provider through the conformance check.

    Spawns the provider via the provider-neutral runner, collects its output, and
    validates the parsed verdict against the published contract. Returns
    ``{provider, passed, errors, verdict}``. Any provider (the vendor CLI, a stub, a
    second vendor) is exercised identically — that is the portability proof.
    """
    from core.adapters.grader_runner import resolve_profile, spawn_grader
    from core.work_orders.verify_graders import _collect_grader

    resolved = resolve_profile(profile)
    proc = spawn_grader(prompt or _CONFORMANCE_PROMPT, resolved)
    try:
        verdict = _collect_grader(proc)
    except Exception as exc:
        # A non-JSON / crashed provider is non-conformant, not an error to propagate.
        return {
            "provider": resolved.get("command"),
            "passed": False,
            "errors": [f"provider did not return a parseable verdict: {exc}"],
            "verdict": None,
        }
    if isinstance(verdict, dict) and (verdict.get("unreviewable") or verdict.get("_grader_error")):
        errors = [str(verdict.get("reason") or verdict.get("_grader_error") or "no verdict")]
    else:
        errors = validate_grader_verdict(verdict)
    return {
        "provider": resolved.get("command"),
        "passed": not errors,
        "errors": errors,
        "verdict": verdict,
    }


def record_conformance_result(result: dict[str, Any], path: Path) -> Path:
    """Persist a conformance result as an evidence artifact (JSON). Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


# ── Mock fixtures (one per grader) ─────────────────────────────────────────────

_MOCK_COMPLETION: dict[str, Any] = {
    "passed": True,
    "tasks_verified": [],
    "summary": "[mock] completion grader — DREAM_STUDIO_VERIFY_MOCK=1",
    "gaps": [],
    "completion_score": 1.0,
}

_MOCK_CORRECTNESS: dict[str, Any] = {
    "correctness_passed": True,
    "correctness_score": 1.0,
    "violations": [],
    "coverage_gaps": [],
    "migration_gaps": [],
}

_MOCK_QUALITY: dict[str, Any] = {
    "quality_passed": True,
    "quality_score": 1.0,
    "issues": [],
}

_MOCK_MIGRATION: dict[str, Any] = {
    "migration_safe": True,
    "migration_score": 1.0,
    "risks": [],
}

# Backward-compat alias used by callers that imported _MOCK_FIXTURE directly.
_MOCK_FIXTURE: dict[str, Any] = {
    "passed": True,
    "tasks_verified": [],
    "summary": "[mock] verification fixture — DREAM_STUDIO_VERIFY_MOCK=1",
    "gaps": [],
    "correctness_signals": {
        "architecture_violations": [],
        "coverage_gaps": [],
        "migration_gaps": [],
        "correctness_passed": True,
    },
}
