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

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_GRADER_VERDICT_SCHEMA_PATH = _SCHEMA_DIR / "grader_verdict.schema.json"

# The four grader roles each publish their own contract: a role verdict must carry that
# role's own score (gap 0a64cf8c). The combined schema above stays the "any role" union.
GRADER_ROLES = ("completion", "correctness", "quality", "migration")
_ROLE_SCHEMA_PATHS = {
    role: _SCHEMA_DIR / f"grader_verdict_{role}.schema.json" for role in GRADER_ROLES
}

# The fixed prompts the conformance suite feeds a provider — one per role, each asking
# for that role's own score so the returned verdict is checked against the role contract
# (gap 2bbed8d8). A conformant provider returns ONLY a JSON grader verdict.
_ROLE_CONFORMANCE_PROMPTS = {
    "completion": '{"completion_score": 1.0, "summary": "...", "gaps": []}',
    "correctness": '{"correctness_score": 1.0, "violations": [], "coverage_gaps": []}',
    "quality": '{"quality_score": 1.0, "issues": []}',
    "migration": '{"migration_score": 1.0, "migration_safe": true, "risks": []}',
}


def _conformance_prompt(role: str | None) -> str:
    example = _ROLE_CONFORMANCE_PROMPTS.get(
        role or "completion", _ROLE_CONFORMANCE_PROMPTS["completion"]
    )
    return (
        "You are a Dream Studio verification grader"
        + (f" acting in the {role} role" if role else "")
        + ". Respond with ONLY a JSON object matching the grader verdict contract, e.g. "
        + example
        + ". No prose outside the JSON."
    )


# Backward-compat alias (the completion-shaped prompt).
_CONFORMANCE_PROMPT = _conformance_prompt("completion")


def grader_verdict_schema(role: str | None = None) -> dict[str, Any]:
    """Load a published grader-verdict I/O-contract schema.

    ``role`` in ``GRADER_ROLES`` loads that role's own contract (which requires the role's
    score); ``None`` loads the combined "any role" union schema.
    """
    path = _ROLE_SCHEMA_PATHS[role] if role in _ROLE_SCHEMA_PATHS else _GRADER_VERDICT_SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def validate_grader_verdict(verdict: Any, role: str | None = None) -> list[str]:
    """Return schema-validation error messages for a grader verdict ([] == conformant).

    When ``role`` names a grader role the verdict is checked against that role's own
    contract (so a completion verdict must carry ``completion_score`` etc., gap 0a64cf8c);
    otherwise it is checked against the combined union contract.
    """
    import jsonschema

    if not isinstance(verdict, dict):
        return [f"verdict is not a JSON object (got {type(verdict).__name__})"]
    validator = jsonschema.Draft202012Validator(grader_verdict_schema(role))
    return [e.message for e in validator.iter_errors(verdict)]


def run_grader_conformance(
    profile: dict[str, Any] | None = None, *, role: str | None = None, prompt: str | None = None
) -> dict[str, Any]:
    """Run one provider through the conformance check for one grader role.

    Spawns the provider via the provider-neutral runner **through the shared retry path**
    (so a transient non-JSON reply is re-tried exactly as in real verify — gap 2bbed8d8),
    then validates the parsed verdict against that role's published contract. Returns
    ``{provider, role, passed, unreviewable, is_stub, errors, verdict}``. Any provider (the
    vendor CLI, a stub, a second vendor) is exercised identically — that is the portability
    proof. ``unreviewable`` (empty output) is reported distinctly from a conformance failure
    so an empty reply is not treated as close-blocking (gap 2bbed8d8 / WO-VERIFY-NOSUMMARY).
    """
    from core.adapters.grader_runner import resolve_profile
    from core.work_orders.verify_graders import collect_grader_with_retry

    resolved = resolve_profile(profile)
    is_stub = bool(resolved.get("is_stub"))
    verdict = collect_grader_with_retry(prompt or _conformance_prompt(role), resolved)

    base = {"provider": resolved.get("command"), "role": role, "is_stub": is_stub}
    if isinstance(verdict, dict) and verdict.get("unreviewable"):
        # Empty / no-summary output: unreviewable, distinct from non-conformant.
        return {
            **base,
            "passed": False,
            "unreviewable": True,
            "errors": [str(verdict.get("reason") or "grader returned empty output")],
            "verdict": verdict,
        }
    if isinstance(verdict, dict) and verdict.get("_grader_error"):
        return {
            **base,
            "passed": False,
            "unreviewable": False,
            "errors": [f"provider did not return a parseable verdict: {verdict['_grader_error']}"],
            "verdict": verdict,
        }
    errors = validate_grader_verdict(verdict, role=role)
    return {
        **base,
        "passed": not errors,
        "unreviewable": False,
        "errors": errors,
        "verdict": verdict,
    }


def run_conformance_suite(
    profile: dict[str, Any] | None = None, *, roles: tuple[str, ...] = GRADER_ROLES
) -> dict[str, Any]:
    """Run the full conformance suite: one provider across every grader role.

    Returns ``{provider, is_stub, passed, roles: {role: result, ...}}``. ``passed`` is True
    only if every role returned a schema-valid verdict — the whole-provider portability
    claim (gap 2bbed8d8). Drives each role from the resolved provider *profile* rather than
    an ambient default.
    """
    from core.adapters.grader_runner import resolve_profile

    resolved = resolve_profile(profile)
    per_role = {role: run_grader_conformance(resolved, role=role) for role in roles}
    return {
        "provider": resolved.get("command"),
        "is_stub": bool(resolved.get("is_stub")),
        "passed": all(r["passed"] for r in per_role.values()),
        "roles": per_role,
    }


def run_provider_conformance_or_block(
    provider_name: str, *, roles: tuple[str, ...] = GRADER_ROLES
) -> dict[str, Any]:
    """Run the conformance suite against a NAMED REAL provider, or report it blocked.

    Returns ``{provider, blocked, reason?, suite?}``. The honest handling of gap 930ea6df's
    "second provider" task: a stub profile or a provider that is not invocable on this host
    yields ``blocked=True`` with the reason — never a stub pass recorded as real-provider
    evidence. Only a real, reachable provider is actually exercised.
    """
    from config.grader_profiles import resolve_named_provider
    from core.adapters.grader_runner import grader_provider_available

    profile = resolve_named_provider(provider_name)
    if profile.get("is_stub"):
        return {
            "provider": provider_name,
            "blocked": True,
            "reason": "profile is a stub; a stub run is not real-provider conformance evidence",
        }
    if not grader_provider_available(profile):
        return {
            "provider": provider_name,
            "blocked": True,
            "reason": f"provider command {profile.get('command')!r} is not invocable on this host",
        }
    return {
        "provider": provider_name,
        "blocked": False,
        "suite": run_conformance_suite(profile, roles=roles),
    }


def record_conformance_result(result: dict[str, Any], path: Path) -> Path:
    """Persist a conformance result as an evidence artifact (JSON). Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


class StubConformanceNotProviderEvidence(ValueError):
    """Raised when a stub conformance run is offered as real-provider evidence (gap 930ea6df).

    A stub always returns a canned pass, so recording it as a *provider* conformance pass is
    a false-done. Provider evidence must come from a non-stub profile.
    """


def record_provider_conformance(result: dict[str, Any], path: Path) -> Path:
    """Persist a conformance result as **real-provider** evidence, refusing a stub.

    If ``result['is_stub']`` is truthy this raises ``StubConformanceNotProviderEvidence``
    — a stub run must never be recorded as proof that a second real provider satisfies the
    contract (gap 930ea6df: recording a stub pass as a real-provider pass is a false-done).
    """
    if result.get("is_stub"):
        raise StubConformanceNotProviderEvidence(
            "refusing to record a stub conformance run as real-provider evidence "
            f"(provider={result.get('provider')!r})"
        )
    return record_conformance_result(result, path)


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
