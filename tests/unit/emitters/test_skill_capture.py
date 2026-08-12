"""WO-SKILL-CAPTURE-REGRESSION: the Claude Code emitter captures native Skill-tool
invocations as skill.invoked events.

Skill telemetry went dark 2026-07-02 when skills moved to the native Skill tool, which
bypassed the DS `ds`-CLI skill-dispatch path (the only emitter of skill.invoked). This
adds capture to normalize_post_tool_use: a Skill tool call emits skill.invoked with the
ds-* skill id in trace.skill_id (mirroring the Task->agent_id block). The ingestor now
reads skill_id from trace, so the event survives validation and the skill_id column
(hence the dashboard Top Skills panel) repopulates.
"""

from __future__ import annotations

import sqlite3


def _skill_envelopes(payload):
    from emitters.claude_code.emitter import normalize_post_tool_use

    envs = normalize_post_tool_use(payload)
    return [e for e in envs if e.event_type == "skill.invoked"]


def test_skill_tool_emits_skill_invoked(spool_root):
    payload = {"tool_name": "Skill", "tool_input": {"skill": "ds-project"}, "is_error": False}
    skill_envs = _skill_envelopes(payload)
    assert len(skill_envs) == 1
    env = skill_envs[0]
    assert env.event_type == "skill.invoked"
    assert env.trace.get("skill_id") == "ds-project"
    assert env.payload.get("skill_id") == "ds-project"
    assert env.payload.get("outcome_status") == "completed"


def test_skill_error_marks_failed(spool_root):
    payload = {"tool_name": "Skill", "tool_input": {"skill": "ds-core"}, "is_error": True}
    env = _skill_envelopes(payload)[0]
    assert env.payload.get("outcome_status") == "failed"


def test_non_ds_skill_not_captured(spool_root):
    # A non-ds skill name would fail the ingestor's ^ds-... validation, so it is skipped
    # at the emitter rather than emitted-then-rejected.
    payload = {"tool_name": "Skill", "tool_input": {"skill": "artifact-design"}}
    assert _skill_envelopes(payload) == []


def test_non_skill_tool_emits_no_skill_event(spool_root):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/x.py"}, "tool_response": "x"}
    assert _skill_envelopes(payload) == []


def test_skill_invoked_round_trips_through_ingest(spool_root):
    """End-to-end: the emitter's trace.skill_id event survives ingestor validation and
    lands in ai_canonical_events with the skill_id column populated."""
    from emitters.claude_code.emitter import normalize_post_tool_use
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "studio.db"
    envelopes = normalize_post_tool_use(
        {"tool_name": "Skill", "tool_input": {"skill": "ds-quality"}, "is_error": False},
        root=spool_root,
    )
    for env in envelopes:
        write_event(env.to_dict(), root=spool_root)
    result = ingest(root=spool_root, db_path=db_path)

    assert result.failed == 0, "skill.invoked with trace.skill_id must not be moved to failed"

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT skill_id FROM ai_canonical_events WHERE event_type = 'skill.invoked'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "skill.invoked event should land in ai_canonical_events"
    assert row[0] == "ds-quality", "trace.skill_id must populate the skill_id column"
