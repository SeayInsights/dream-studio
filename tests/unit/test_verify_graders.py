"""WO-GRADER-PROVIDER-NEUTRAL (+ gap 0e06d71a): verify_graders carries no vendor literal
anywhere — not the bracketed argv, not the binary name, not the vendor one-shot flag.
"""

from __future__ import annotations

from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[2] / "core" / "work_orders" / "verify_graders.py"
).read_text(encoding="utf-8")


def test_no_hardcoded_provider_argv():
    # Widened guard: fail on ANY occurrence of a provider binary name or the vendor
    # one-shot flag, not just the two exact bracketed spellings.
    assert "claude" not in _SRC, "verify_graders must name no vendor binary"
    assert "--print" not in _SRC, "verify_graders must name no vendor one-shot flag"


def test_delegates_to_grader_runner_and_profiles():
    assert "from core.adapters.grader_runner import spawn_grader" in _SRC
    assert "resolve_grader_profile" in _SRC  # per-role profile wiring
