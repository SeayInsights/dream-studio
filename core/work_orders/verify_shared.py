"""Mock grader fixtures shared by verify siblings.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
``DREAM_STUDIO_VERIFY_MOCK`` env-var name and the deterministic mock fixtures
substituted for the real graders in CI. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

from typing import Any

_MOCK_ENV = "DREAM_STUDIO_VERIFY_MOCK"

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
