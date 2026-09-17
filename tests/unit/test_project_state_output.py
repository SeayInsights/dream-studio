"""`ds project state` must not dump the whole backlog by default.

get_project_state returns `ready_set` — every unblocked work order on a project.
On a mature project that is the entire backlog. Measured on the operator's own
store on 2026-09-17: 132 entries / 96,106 characters for one project, inside a
151,683-character response, emitted at every session start.

That output is the documented "one command, everything" orientation entry point,
so its size is paid twice: once by the operator trying to read it, and once by
the model, which carries it in context for the rest of the session.

The default now previews the ready set and reports its real size; --full
restores the complete list; --human renders a briefing. The preview must stay
honest — a truncated list that still claims to be the whole set would be worse
than the dump it replaced.
"""

from __future__ import annotations

from interfaces.cli.commands.project import (
    _READY_SET_PREVIEW,
    _preview_ready_sets,
    _render_state_briefing,
)


def _state(n_ready: int = 132) -> dict:
    return {
        "ok": True,
        "projects": [
            {
                "project_id": "p1",
                "name": "Dream Studio",
                "status": "paused",
                "next_work_order": {
                    "work_order_id": "wo1",
                    "title": "Do the thing",
                    "status": "in_progress",
                    "total_tasks": 8,
                    "pending_tasks": 6,
                    "design_brief": {"status": "locked", "fields_filled": 4, "fields_total": 6},
                    "gotchas": ["watch the migration"],
                    "test_execution_warning": "2 TEST-CHECKs never ran",
                },
                "ready_set": [{"work_order_id": f"w{i}", "title": f"t{i}"} for i in range(n_ready)],
                "unverified_risks": {"total": 3},
                "next_action": "Run: ds work-order start wo1",
            }
        ],
        "main_ci": {"red": True, "title": "a failing commit", "run_url": "https://example/run"},
        "bypass_summary": {"last_7d_total": 5},
    }


def test_preview_truncates_and_reports_the_true_total():
    state = _state(132)
    _preview_ready_sets(state)
    project = state["projects"][0]

    assert len(project["ready_set"]) == _READY_SET_PREVIEW
    assert project["ready_set_total"] == 132, "the real size must survive truncation"
    assert project["ready_set_truncated"] is True
    assert "132" in project["ready_set_hint"]
    assert "--full" in project["ready_set_hint"], "the escape hatch must be discoverable"


def test_preview_keeps_ready_set_a_list():
    """Readers iterate this key; truncating must not change its type."""
    state = _state(132)
    _preview_ready_sets(state)
    assert isinstance(state["projects"][0]["ready_set"], list)


def test_short_ready_set_is_untouched_and_not_marked_truncated():
    state = _state(3)
    _preview_ready_sets(state)
    project = state["projects"][0]
    assert len(project["ready_set"]) == 3
    assert project["ready_set_total"] == 3
    assert project["ready_set_truncated"] is False
    assert "ready_set_hint" not in project


def test_preview_is_a_large_reduction():
    """Guard the actual point of the change, not just the mechanics."""
    import json

    full = _state(132)
    before = len(json.dumps(full))
    _preview_ready_sets(full)
    after = len(json.dumps(full))
    assert after < before * 0.35, (
        f"preview only cut {before} -> {after}; the ready-set dump is the "
        "dominant term and must actually shrink"
    )


def test_preview_handles_a_missing_or_malformed_ready_set():
    state = {"projects": [{"name": "x"}, {"name": "y", "ready_set": None}, {}]}
    _preview_ready_sets(state)  # must not raise
    assert state["projects"][0].get("ready_set_total") is None


def test_briefing_surfaces_what_an_operator_needs():
    state = _state(132)
    _preview_ready_sets(state)
    text = _render_state_briefing(state)

    assert "Dream Studio" in text
    assert "Do the thing" in text
    assert "2/8 tasks" in text, "task progress must be visible"
    assert "132" in text, "the briefing must report the TRUE ready-set size, not the preview"
    assert "watch the migration" in text, "gotchas must surface"
    assert "2 TEST-CHECKs never ran" in text
    assert "RED" in text, "a red main CI must be impossible to miss"
    assert "ds work-order start wo1" in text, "the next action must be copy-pasteable"


def test_briefing_is_dramatically_shorter_than_the_json():
    import json

    state = _state(132)
    text = _render_state_briefing(state)
    assert len(text) < len(json.dumps(state, indent=2)) / 10


def test_briefing_handles_no_projects():
    assert _render_state_briefing({"projects": []}) == "No registered projects."


def test_briefing_handles_a_project_with_nothing_ready():
    state = {"projects": [{"name": "Empty", "status": "active", "next_work_order": {}}]}
    text = _render_state_briefing(state)
    assert "nothing ready" in text
