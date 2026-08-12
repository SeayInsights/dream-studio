"""WO-GRADER-PROVIDER-NEUTRAL: eval live mode spawns through the provider-neutral
grader runner, not a hardcoded vendor CLI argv.
"""

from __future__ import annotations

from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "core" / "eval" / "runner_process.py").read_text(
    encoding="utf-8"
)


def test_live_mode_uses_grader_runner():
    assert "run_generation" in _SRC
    assert "from core.adapters.grader_runner import" in _SRC


def test_no_hardcoded_print_flag():
    # The vendor one-shot flag must be gone from the live-eval spawn.
    assert "--print" not in _SRC
