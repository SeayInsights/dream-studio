"""WO 19a20150: the pulse hook wrote prose and JSON to the same stdout.

Claude Code reads hook stdout. Seeing an opening brace it treats the whole stream
as JSON, so a human banner printed alongside ``json.dumps`` made every pulse fire
surface as "Hook output looks like a JSON object but is not valid JSON" — an
unrecognized-token error when a project-memory block shared the batch, a backslash
escape error when a Windows path appeared in the prose.

The pulse data is already persisted to the authority, so the banner on stdout was
a redundant copy that broke the contract. The contract these tests pin is simply:
**stdout carries exactly one JSON object, every human line goes to stderr.**

The banner is rerouted, not deleted — the second test exists so a later "cleanup"
cannot quietly drop the operator's visibility and still pass.
"""

from __future__ import annotations

import json

import pytest

import interfaces.cli.pulse_collector as pc

CACHED_PULSE = {
    "health": "ATTENTION",
    "stale_branches": 0,
    "overdue_milestones": 0,
    "open_prs": 0,
    "pending_drafts": 43,
    "stale_agents": 0,
    "degraded_skills": 0,
}


@pytest.fixture
def cached_pulse_run(monkeypatch):
    """Drive run_pulse_check down its cached branch without touching the authority."""
    monkeypatch.setattr(pc.paths, "warn_version_mismatch", lambda: None, raising=False)
    monkeypatch.setattr(pc.paths, "check_for_update", lambda: None, raising=False)
    monkeypatch.setattr(pc.state, "get_quiet_mode", lambda: 0, raising=False)
    monkeypatch.setattr(pc, "_cooldown_active", lambda: True, raising=False)
    monkeypatch.setattr(pc.state, "read_pulse", lambda: dict(CACHED_PULSE), raising=False)
    return pc.run_pulse_check


def test_stdout_is_exactly_one_json_object(cached_pulse_run, capsys) -> None:
    """The pulse contributes NOTHING to stdout.

    Named for the contract it originally pinned, which was wrong. stdout is not
    this hook's private channel: on-prompt-dispatch concatenates every handler's
    stdout into one shared text stream of <xml> blocks. A lone JSON object is
    still enough to make that whole stream look like JSON and fail to parse, so
    "one valid object" was never sufficient — the pulse has to stay out of it.
    """
    cached_pulse_run()
    out, _ = capsys.readouterr()

    assert out == ""
    assert "{" not in out


def test_banner_still_goes_to_stderr(cached_pulse_run, capsys) -> None:
    """Rerouted, not deleted — the operator keeps their visibility."""
    cached_pulse_run()
    out, err = capsys.readouterr()

    assert "Pulse check complete" in err
    assert "Pending draft lessons: 43" in err
    assert "Pulse check complete" not in out

    # the machine payload moved with it, and is still well-formed
    status = json.loads(next(ln for ln in err.splitlines() if ln.startswith("{")))
    assert status["hook"] == "on-pulse"
    assert status["status"] == "ok"
