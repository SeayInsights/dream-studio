"""A mode's declared write_posture reaches the enforcement hooks.

write_posture records what a mode may do unattended, which capabilities_required cannot say:
a mode listing Bash is either running the test suite or deploying. Declaring it on the card
is only half the job -- the hooks had no way to know which mode was active, so the field
could not influence anything.

The signal is deliberately ADVISORY. on-skill-load knows which mode's SKILL.md was read most
recently, which is how a mode is entered, but a session may also read one for reference and
nothing forces the model to act under the mode it last read. That is enough to record a
contradiction (a read-only mode producing source writes) and not enough to refuse an edit on,
so this observes and never denies -- the same call module_boundary made when it was added.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from runtime.lib import enforcement

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_LOAD_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-skill-load.py"
COACH_CARD = REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "coach" / "SKILL.md"


@pytest.fixture
def session_id():
    sid = "test-posture-" + os.urandom(4).hex()
    yield sid
    enforcement.delete_session(sid)


def test_an_unknown_session_has_no_posture(session_id):
    assert enforcement.active_skill_posture(session_id) is None


def test_a_missing_session_id_is_not_an_error():
    assert enforcement.active_skill_posture(None) is None
    assert enforcement.active_skill_posture("") is None


def test_the_posture_round_trips_through_session_state(session_id):
    enforcement.record_skill_posture(session_id, "quality:coach", "read-only")
    assert enforcement.active_skill_posture(session_id) == ("quality:coach", "read-only")


def test_the_most_recently_loaded_mode_wins(session_id):
    enforcement.record_skill_posture(session_id, "quality:coach", "read-only")
    enforcement.record_skill_posture(session_id, "core:build", "independent")
    assert enforcement.active_skill_posture(session_id) == ("core:build", "independent")


def test_recording_an_incomplete_posture_is_a_no_op(session_id):
    enforcement.record_skill_posture(session_id, "quality:coach", "")
    enforcement.record_skill_posture("", "quality:coach", "read-only")
    assert enforcement.active_skill_posture(session_id) is None


def test_on_skill_load_captures_the_posture_off_a_real_card(session_id):
    """Drive the hook the way the harness does: a Read payload on stdin."""
    assert COACH_CARD.is_file()
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(COACH_CARD)}})
    env = {
        **os.environ,
        "CLAUDE_SESSION_ID": session_id,
        # What the installed hook is given; its parents[4] fallback targets the
        # installed layout (.claude/hooks/runtime/hooks/meta), not the repo.
        "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
    }
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SKILL_LOAD_HOOK)],
        input=payload,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    # quality:coach declares read-only; the hook should have carried that through.
    assert enforcement.active_skill_posture(session_id) == ("quality:coach", "read-only")


def test_a_non_skill_read_records_nothing(session_id):
    payload = json.dumps(
        {"tool_name": "Read", "tool_input": {"file_path": str(REPO_ROOT / "README.md")}}
    )
    env = {
        **os.environ,
        "CLAUDE_SESSION_ID": session_id,
        # What the installed hook is given; its parents[4] fallback targets the
        # installed layout (.claude/hooks/runtime/hooks/meta), not the repo.
        "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
    }
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SKILL_LOAD_HOOK)],
        input=payload,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert enforcement.active_skill_posture(session_id) is None
