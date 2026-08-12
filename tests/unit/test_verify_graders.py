"""WO-GRADER-PROVIDER-NEUTRAL: verify_graders no longer hardcodes a vendor CLI argv;
it delegates the spawn to the provider-neutral grader runner.
"""

from __future__ import annotations

from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[2] / "core" / "work_orders" / "verify_graders.py"
).read_text(encoding="utf-8")


def test_no_hardcoded_provider_argv():
    assert '["claude", "--print"]' not in _SRC
    assert "['claude', '--print']" not in _SRC


def test_delegates_to_grader_runner():
    assert "from core.adapters.grader_runner import spawn_grader" in _SRC
