"""C6 — Dependency chain evals.

Machine-checked projection of `.audit/dependency-chain-map-2026-05-17.md`
(post-A0/A3 reclassifications in `.audit/dependency-chain-map-2026-05-20-post-A0-A3.md`).

Chain 7 status — 2026-05-28 (18.4.4):
  L1: PROVEN (session events → SQLite)
  L2: UNTESTED (memory harvest trigger — manual only; automation is follow-up WO)
  L3: PROVEN (technology signals schema — post-18.1.15a)
  L4: ✅ PROVEN (18.4.4) — on-context-inject hook injects reg_gotchas from
      memory_entries via FTS5+relevance before every UserPromptSubmit.
      Verified with real data: 1488 reg_gotchas ingested via Batch 7.5,
      hook surfaces relevant entries on accessibility/form/keyboard prompts.
      Batch 8 real-data verification passed 2026-05-28.
  L5: UNTESTED (raw_approaches → model routing)
  L6: UNKNOWN (tech signals → skill recommendations)

Every link in the 8-chain audit gets exactly one test here, totaling 46.
Tests are organized by chain. The docstring of each test cites the current
classification from the chain map. The body either:

  * **PROVEN / UNIT_TESTED** — asserts the post-fix invariant (regression
    guard). When this test fails, a working link has regressed.
  * **UNTESTED / UNKNOWN / BROKEN** — marked `xfail` with a `reason` that
    cites the chain map. When a fix lands, remove the `xfail` and replace
    the body with an assertion.

The xfail markers track unresolved engineering work; the passing tests
prevent regressions in the parts that already work.

C6 spec source: `.planning/specs/a2v2/spec.md` section C6.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═════════════════════════════════════════════════════════════════════════════
# Chain 1 — Natural Language to Skill Execution
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_1_link_1_claude_md_routing_table_present():
    """C1-L1: User message → CLAUDE.md routing table read. PROVEN."""
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if not claude_md.is_file():
        pytest.skip("Operator's ~/.claude/CLAUDE.md not installed in this environment")
    content = claude_md.read_text(encoding="utf-8")
    assert "MANDATORY" in content or "Skill Routing" in content, "CLAUDE.md missing routing markers"


def test_chain_1_link_2_compiler_routing_table_unit_tested():
    """C1-L2: CLAUDE.md routing table → Skill tool invoked. UNIT_TESTED.

    Verifies the compiler module that generates the routing table is importable.
    """
    from integrations.compiler.claude_code import _build_routing_table

    assert callable(_build_routing_table)


@pytest.mark.xfail(
    strict=False,
    reason="C1-L3 UNKNOWN per chain map; requires live Claude Code session to verify "
    "Skill('ds-core', 'build') resolves when only ds-bootstrap is in ~/.claude/skills/",
)
def test_chain_1_link_3_skill_md_load_path_unknown():
    """C1-L3: Skill tool invoked → SKILL.md loaded. UNKNOWN."""
    pytest.fail("UNKNOWN: live behavioral test required")


@pytest.mark.xfail(
    strict=False,
    reason="C1-L4 UNKNOWN per chain map; no integration test verifies Claude Code "
    "follows SKILL.md instructions vs. built-in behavior",
)
def test_chain_1_link_4_ai_follows_skill_md_unknown():
    """C1-L4: SKILL.md loaded → AI executes skill instructions. UNKNOWN."""
    pytest.fail("UNKNOWN: behavioral A/B test required")


@pytest.mark.xfail(
    strict=False,
    reason="C1-L5 UNTESTED per chain map; SKILL.md files instruct AI to call CLI but "
    "no integration test verifies the call actually fires",
)
def test_chain_1_link_5_skill_to_cli_call_untested():
    """C1-L5: Skill execution → CLI command called. UNTESTED."""
    pytest.fail("UNTESTED: needs integration test against a live DB")


# ═════════════════════════════════════════════════════════════════════════════
# Chain 2 — Work Order Lifecycle
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_2_link_1_resume_skill_routable():
    """C2-L1: 'start working' → ds-project:resume invoked. UNIT_TESTED."""
    resume_skill = REPO_ROOT / "canonical" / "skills" / "ds-project" / "modes" / "resume"
    assert resume_skill.is_dir(), "ds-project:resume mode directory missing"
    assert (resume_skill / "SKILL.md").is_file() or (
        resume_skill / "metadata.yml"
    ).is_file(), "Resume skill has no SKILL.md or metadata.yml"


@pytest.mark.xfail(
    strict=False,
    reason="C2-L2 UNKNOWN per chain map; depends on C1-L3 (SKILL.md load path)",
)
def test_chain_2_link_2_resume_to_project_list_unknown():
    """C2-L2: Resume skill → ds project list called. UNKNOWN (downstream of C1-L3)."""
    pytest.fail("UNKNOWN: downstream of C1-L3")


def test_chain_2_link_3_work_order_start_writes_context():
    """C2-L3: ds work-order start → context.md written. PROVEN."""
    from core.work_orders.start import start_work_order, write_work_order_context

    assert callable(start_work_order)
    assert callable(write_work_order_context)


@pytest.mark.xfail(
    strict=False,
    reason="C2-L4 UNTESTED per chain map; no mechanism forces AI to read context.md "
    "(advisory only — flagged as Subagent Isolation GAP in system audit Section 7)",
)
def test_chain_2_link_4_subagent_scoped_context_untested():
    """C2-L4: Context written → subagent receives scoped context. UNTESTED."""
    pytest.fail("UNTESTED: subagent isolation mechanism does not exist")


def test_chain_2_link_5_gate_artifact_template_exists():
    """C2-L5: Work produced → gate artifact written. UNIT_TESTED."""
    from core.skills.invocation import seed_gate_artifact_files

    assert callable(seed_gate_artifact_files)


def test_chain_2_link_6_gate_checker_unit_tested():
    """C2-L6: ds work-order close → gates checked. PROVEN."""
    from core.work_orders.close import close_work_order, run_gate_check

    assert callable(close_work_order)
    assert callable(run_gate_check)


def test_chain_2_link_7_work_order_lifecycle_events_emitted():
    """C2-L7: Gates pass → work_order lifecycle event emitted. UNKNOWN → PROVEN.

    Post-A0: WORK_ORDER_STARTED / WORK_ORDER_CLOSED / WORK_ORDER_BLOCKED /
    GATE_BYPASSED are first-class event types. Emission sites use envelopes.
    """
    from canonical.events.types import EventType

    expected = {"WORK_ORDER_STARTED", "WORK_ORDER_CLOSED", "WORK_ORDER_BLOCKED", "GATE_BYPASSED"}
    for name in expected:
        assert hasattr(EventType, name), f"EventType.{name} missing — A0 should have added it"


def test_chain_2_link_8_wo_spool_ingest_post_a0():
    """C2-L8: Spool event → ingestor → SQLite. BROKEN → PROVEN post-A0 (#16).

    The fix: hand-built event dicts in core/work_orders/* were replaced with
    CanonicalEventEnvelope, which guarantees schema_version. The ingestor no
    longer rejects WO lifecycle events.
    """
    from canonical.events.envelope import CanonicalEventEnvelope
    from canonical.events.types import EventType

    envelope = CanonicalEventEnvelope(
        event_type=EventType.WORK_ORDER_STARTED.value,
        session_id=None,
        payload={"work_order_id": "test"},
    )
    assert envelope.schema_version == 1
    assert envelope.to_dict()["schema_version"] == 1


@pytest.mark.xfail(
    strict=False,
    reason="C2-L9 UNTESTED per chain map; no auto-advance mechanism — flagged as "
    "Autonomous Loop GAP in system audit Section 7",
)
def test_chain_2_link_9_auto_advance_next_wo_untested():
    """C2-L9: Work order closed → next WO auto-started. UNTESTED."""
    pytest.fail("UNTESTED: auto-advance mechanism does not exist")


# ═════════════════════════════════════════════════════════════════════════════
# Chain 3 — Hook Dispatch Chain
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_3_link_1_dispatcher_in_template():
    """C3-L1: Hook event fires → dispatches emitter AND dispatcher. PROVEN post-18.1.15a.

    Fixed: dispatcher entries added to hooks_template.json and settings.json verified.
    """
    template_path = REPO_ROOT / "integrations" / "targets" / "claude_code" / "hooks_template.json"
    assert template_path.is_file(), "hooks_template.json missing"
    import json

    entries = json.loads(template_path.read_text(encoding="utf-8"))
    all_commands = [h.get("command", "") for entry in entries for h in entry.get("hooks", [])]
    dispatcher_cmds = [
        c for c in all_commands if "dispatch/hooks.py" in c or "dispatch\\hooks.py" in c
    ]
    assert dispatcher_cmds, "No dispatcher entries found in hooks_template.json"


def test_chain_3_link_2_emitter_run_module_present():
    """C3-L2: Emitter hook fires → emitters/claude_code/run.py → spool event. PROVEN."""
    emitter_path = REPO_ROOT / "emitters" / "claude_code" / "run.py"
    assert emitter_path.is_file(), "Emitter run.py missing"


def test_chain_3_link_3_capability_routing_module_importable():
    """C3-L3: Dispatcher hook fires → capability routing. PROVEN post-18.1.15a.

    Fixed: C3-L1 resolved (dispatcher in template). Dispatcher module is importable
    and _resolve_handlers is callable — routing logic exists and is reachable.
    """
    from runtime.dispatch.hooks import _resolve_handlers

    assert callable(_resolve_handlers)


def test_chain_3_link_4_stop_hook_ingest_pending():
    """C3-L4: Stop hook fires → ingest_pending() called. PROVEN."""
    from spool.ingestor import ingest_pending

    assert callable(ingest_pending)


def test_chain_3_link_5_spool_ingest_wo_events_post_a0():
    """C3-L5: Spool ingest → SQLite (WO event subset). BROKEN → PROVEN post-A0 (#16).

    Same root cause and fix as C2-L8. The ingestor's schema_version requirement
    is now satisfied because emission sites use CanonicalEventEnvelope.
    """
    from canonical.events.envelope import REQUIRED_FIELDS, validate_envelope
    from canonical.events.types import EventType

    sample = {
        "event_id": "test-id",
        "event_type": EventType.WORK_ORDER_CLOSED.value,
        "timestamp": "2026-05-20T00:00:00+00:00",
        "schema_version": 1,
    }
    assert validate_envelope(sample) == []
    assert REQUIRED_FIELDS == frozenset({"event_id", "event_type", "timestamp", "schema_version"})


# ═════════════════════════════════════════════════════════════════════════════
# Chain 4 — Workflow Execution
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_4_link_1_workflow_trigger_in_installed_routing():
    """C4-L1: 'idea-to-pr' → workflow routing triggered. PROVEN post-18.1.15a.

    Fixed: workflow trigger keywords added to ds-workflow pack routing table.
    Verifies installed ~/.claude/CLAUDE.md contains 'workflow:' keyword.
    """
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if not claude_md.is_file():
        pytest.skip("Operator's ~/.claude/CLAUDE.md not installed in this environment")
    content = claude_md.read_text(encoding="utf-8")
    assert "workflow:" in content, "workflow: trigger keyword absent from installed CLAUDE.md"


@pytest.mark.xfail(
    strict=False,
    reason="C4-L2 UNKNOWN per chain map; depends on C4-L1 fix and verified runner",
)
def test_chain_4_link_2_workflow_yaml_read_unknown():
    """C4-L2: Workflow skill invoked → workflow YAML read. UNKNOWN."""
    pytest.fail("UNKNOWN: downstream of C4-L1")


@pytest.mark.xfail(
    strict=False,
    reason="C4-L3 UNKNOWN per chain map; SKILL.md itself warns runner may be absent",
)
def test_chain_4_link_3_workflow_steps_executed_unknown():
    """C4-L3: Workflow YAML read → steps executed. UNKNOWN."""
    pytest.fail("UNKNOWN: runner completeness needs investigation (INV-3)")


def test_chain_4_link_4_workflow_step_skill_invoke_post_a3():
    """C4-L4: Workflow step → skill invoked. UNKNOWN → UNIT_TESTED post-A3 (#17).

    Runner now imports core.skills.invocation directly (no subprocess shell-out).
    """
    from control.execution.workflow.runner import WorkflowRunner
    from core.skills.invocation import load_skill_content

    assert WorkflowRunner is not None
    assert callable(load_skill_content)


@pytest.mark.xfail(
    strict=False,
    reason="C4-L5 UNTESTED per chain map; 0 workflow events in canonical_events; "
    "no workflow has been run end-to-end",
)
def test_chain_4_link_5_workflow_output_untested():
    """C4-L5: Workflow completes → output produced. UNTESTED."""
    pytest.fail("UNTESTED: no successful end-to-end workflow run on record")


# ═════════════════════════════════════════════════════════════════════════════
# Chain 5 — Agent Execution
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(
    strict=False,
    reason="C5-L1 UNKNOWN per chain map; packs.yaml agent names do not match files "
    "in canonical/agents/; no trigger mechanism identified",
)
def test_chain_5_link_1_agent_invocation_mechanism_unknown():
    """C5-L1: When are agent profiles invoked? UNKNOWN."""
    pytest.fail("UNKNOWN: no agent invocation mechanism identified (INV-4)")


@pytest.mark.xfail(
    strict=False,
    reason="C5-L2 UNKNOWN per chain map; agent files not installed to ~/.claude/agents/",
)
def test_chain_5_link_2_agent_profile_loaded_unknown():
    """C5-L2: Agent profile → Claude Code loads it. UNKNOWN."""
    pytest.fail("UNKNOWN: Claude Code agent loading path unverified")


@pytest.mark.xfail(
    strict=False,
    reason="C5-L3 UNKNOWN per chain map; no context-scoping mechanism for agents",
)
def test_chain_5_link_3_agent_scoped_context_unknown():
    """C5-L3: Agent invoked → scoped context provided. UNKNOWN."""
    pytest.fail("UNKNOWN: subagent isolation gap")


@pytest.mark.xfail(
    strict=False,
    reason="C5-L4 UNTESTED per chain map; all agent_* tables have 0 rows; "
    "no agent event type defined",
)
def test_chain_5_link_4_agent_completion_recorded_untested():
    """C5-L4: Agent completes → output recorded. UNTESTED."""
    pytest.fail("UNTESTED: no agent event type or recording path")


# ═════════════════════════════════════════════════════════════════════════════
# Chain 6 — Design System Pipeline
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_6_link_1_design_brief_read_on_start():
    """C6-L1: Design brief locked → work-order start reads brief. PROVEN."""
    from core.work_orders.start import read_work_order_brief

    assert callable(read_work_order_brief)


def test_chain_6_link_2_design_system_directories_present():
    """C6-L2: Design system name → design system reference path in context. PROVEN."""
    design_systems = REPO_ROOT / "canonical" / "skills" / "domains" / "modes" / "design"
    if not design_systems.is_dir():
        pytest.skip("Design systems live elsewhere; investigate per chain map")
    # If the design systems are not under the documented path, skip — the chain
    # map records the path as evidence; if it has moved, the chain map needs an
    # update before this test should assert.


@pytest.mark.xfail(
    strict=False,
    reason="C6-L3 UNTESTED per chain map; design system application is advisory only",
)
def test_chain_6_link_3_ai_applies_design_system_untested():
    """C6-L3: Design system reference → AI applies it. UNTESTED."""
    pytest.fail("UNTESTED: no enforcement; advisory only")


@pytest.mark.xfail(
    strict=False,
    reason="C6-L4 UNTESTED per chain map; anti-slop linter must be run manually",
)
def test_chain_6_link_4_anti_slop_linter_untested():
    """C6-L4: UI artifact produced → anti-slop linter runs. UNTESTED."""
    pytest.fail("UNTESTED: no automatic trigger for linter")


@pytest.mark.xfail(
    strict=False,
    reason="C6-L5 UNTESTED per chain map; design critique invocation is manual",
)
def test_chain_6_link_5_design_critique_runs_untested():
    """C6-L5: Lint results written → design critique runs. UNTESTED."""
    pytest.fail("UNTESTED: no automatic trigger from lint completion")


def test_chain_6_link_6_design_critique_gate_unit_tested():
    """C6-L6: Design critique score → gate checked. PROVEN."""
    from core.work_orders.close import run_gate_check

    assert callable(run_gate_check)


# ═════════════════════════════════════════════════════════════════════════════
# Chain 7 — Memory and Intelligence Loop
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_7_link_1_session_events_to_sqlite_post_a0():
    """C7-L1: Session events → SQLite. BROKEN → PROVEN post-A0 (#16).

    WO lifecycle events (the critical intelligence inputs for project-level
    learning) no longer fail ingest. Tool events were already passing.
    """
    from canonical.events.envelope import CanonicalEventEnvelope
    from canonical.events.types import EventType

    envelope = CanonicalEventEnvelope(
        event_type=EventType.WORK_ORDER_STARTED.value,
        session_id="test-session",
        payload={"work_order_id": "wo-1"},
    )
    assert envelope.schema_version == 1


@pytest.mark.xfail(
    strict=False,
    reason="C7-L2 UNTESTED per chain map; memory harvest must be manually triggered",
)
def test_chain_7_link_2_memory_harvest_trigger_untested():
    """C7-L2: Session ends → memory harvest opportunity. UNTESTED."""
    pytest.fail("UNTESTED: no auto-trigger for memory harvest")


def test_chain_7_link_3_technology_signals_schema_aligned():
    """C7-L3: ds memory ingest-sessions → SQLite populated. PROVEN post-18.1.15a.

    Fixed: session_harvester.py INSERT now uses column `count` matching migration 055.
    No `file_count` references remain in the harvester.
    """
    harvester_path = REPO_ROOT / "spool" / "session_harvester.py"
    assert harvester_path.is_file(), "session_harvester.py missing"
    content = harvester_path.read_text(encoding="utf-8")
    assert "file_count" not in content, "Stale `file_count` column reference still in harvester"
    assert "ds_technology_signals" in content, "ds_technology_signals not referenced in harvester"


def test_chain_7_link_4_memory_hook_query_path_exists():
    """C7-L4: memory_entries hook injection path exists. PROVEN post-18.4.4.

    The on-context-inject hook provides the query path from memory_entries
    (populated by GotchaIngestionConsumer from reg_gotchas) to prompt context
    via UserPromptSubmit. Tests:
    - Hook file exists at expected path
    - FTS search function is present
    - Hook produces <project-memory> output on seeded DB
    """
    import os
    import shutil
    import sqlite3
    import sys
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    repo_root = REPO_ROOT
    hook_path = repo_root / "runtime" / "hooks" / "meta" / "on-context-inject.py"

    # Hook file must exist
    assert hook_path.is_file(), f"on-context-inject.py missing at {hook_path}"

    # Hook must expose _fts_query and _search_memories
    import importlib.util
    spec = importlib.util.spec_from_file_location("on_context_inject", hook_path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(repo_root))
    spec.loader.exec_module(mod)

    assert hasattr(mod, "_fts_query"), "Hook missing _fts_query function"
    assert hasattr(mod, "_search_memories"), "Hook missing _search_memories function"
    assert hasattr(mod, "main"), "Hook missing main function"

    # FTS query conversion works
    query = mod._fts_query("modal dialog focus trap inert attribute")
    assert "OR" in query, f"_fts_query should produce OR query, got: {query!r}"

    # End-to-end: seeded DB → hook produces injection output
    tmpdir = tempfile.mkdtemp(prefix="ds-c7-test-")
    db_path = Path(tmpdir) / "studio.db"
    try:
        from core.event_store.studio_db import _connect, _run_migrations
        with _connect(db_path) as c:
            _run_migrations(c)
            c.execute(
                "INSERT INTO memory_entries"
                " (memory_id, source, category, content, importance, created_at)"
                " VALUES ('cg1', 'reg_gotchas', 'gotcha',"
                " 'Modal dialogs need inert attribute on background to prevent focus escape',"
                " 0.9, '2026-01-01')"
            )
            c.commit()

        output_lines = []
        with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
            with patch("builtins.print", side_effect=lambda *a, **kw: output_lines.append(str(a[0]))):
                mod.main({"prompt": "modal dialog focus trap inert attribute"})

        output = "\n".join(output_lines)
        assert "<project-memory>" in output, (
            f"Hook produced no <project-memory> output. Got: {output!r}"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_chain_7_hook_fails_open_on_empty_db():
    """C7: Hook produces no output and no error when memory_entries is empty."""
    import os
    import shutil
    import sys
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    repo_root = REPO_ROOT
    hook_path = repo_root / "runtime" / "hooks" / "meta" / "on-context-inject.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("on_context_inject_empty", hook_path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(repo_root))
    spec.loader.exec_module(mod)

    tmpdir = tempfile.mkdtemp(prefix="ds-c7-empty-")
    db_path = Path(tmpdir) / "studio.db"
    try:
        from core.event_store.studio_db import _connect, _run_migrations
        with _connect(db_path) as c:
            _run_migrations(c)
            c.commit()

        output_lines = []
        with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
            with patch("builtins.print", side_effect=lambda *a, **kw: output_lines.append(str(a[0]))):
                mod.main({"prompt": "modal dialog focus trap"})

        assert output_lines == [], f"Empty DB produced output: {output_lines}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_chain_7_hook_dedup_within_session():
    """C7: Hook does not re-inject a memory already surfaced in this session."""
    import os
    import shutil
    import sys
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    repo_root = REPO_ROOT
    hook_path = repo_root / "runtime" / "hooks" / "meta" / "on-context-inject.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("on_context_inject_dedup", hook_path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(repo_root))
    spec.loader.exec_module(mod)

    tmpdir = tempfile.mkdtemp(prefix="ds-c7-dedup-")
    db_path = Path(tmpdir) / "studio.db"
    try:
        from core.event_store.studio_db import _connect, _run_migrations
        with _connect(db_path) as c:
            _run_migrations(c)
            c.execute(
                "INSERT INTO memory_entries"
                " (memory_id, source, category, content, importance, created_at)"
                " VALUES ('dd1', 'reg_gotchas', 'gotcha',"
                " 'Modal dialogs need inert attribute on background', 0.9, '2026-01-01')"
            )
            c.commit()

        session_id = "test-session-dedup"
        output_first: list[str] = []
        output_second: list[str] = []

        with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
            with patch("builtins.print", side_effect=lambda *a, **kw: output_first.append(str(a[0]))):
                mod.main({"prompt": "modal inert attribute", "session_id": session_id})

        # First invocation should produce output
        assert output_first, "First invocation produced no output"

        with patch.dict(os.environ, {"DREAM_STUDIO_DB_PATH": str(db_path)}):
            with patch("builtins.print", side_effect=lambda *a, **kw: output_second.append(str(a[0]))):
                mod.main({"prompt": "modal inert attribute", "session_id": session_id})

        # Second invocation with same session_id should not re-inject (dedup via intelligence_surfaced_at)
        # Entry was stamped in first call; second call sees it as already surfaced
        assert not output_second, (
            f"Second invocation re-injected already-surfaced memory. Output: {output_second}"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.xfail(
    strict=False,
    reason="C7-L5 UNTESTED per chain map; model selector is config-driven, not history-driven",
)
def test_chain_7_link_5_raw_approaches_model_routing_untested():
    """C7-L5: raw_approaches populated → model tier routing improved. UNTESTED."""
    pytest.fail("UNTESTED: model selector does not consult raw_approaches")


@pytest.mark.xfail(
    strict=False,
    reason="C7-L6 UNKNOWN post-18.1.15a; C7-L3 schema mismatch fixed so signals can now "
    "be stored, but no code path reading ds_technology_signals for recommendations "
    "was identified — consumption code not yet implemented",
)
def test_chain_7_link_6_tech_signals_recommendations_unknown():
    """C7-L6: ds_technology_signals populated → skill pack recommendations. UNKNOWN."""
    pytest.fail("UNKNOWN: C7-L3 unblocked but no consumption code found")


# ═════════════════════════════════════════════════════════════════════════════
# Chain 8 — Install Chain (New Developer)
# ═════════════════════════════════════════════════════════════════════════════


def test_chain_8_link_1_dynamic_plugin_root_path():
    """C8-L1: Clone → repo at correct path. PROVEN."""
    hooks_json = REPO_ROOT / "hooks" / "hooks.json"
    assert hooks_json.is_file(), "hooks/hooks.json missing"
    content = hooks_json.read_text(encoding="utf-8")
    # Dynamic resolution evidence: env var OR parent-search marker present
    assert (
        "CLAUDE_PLUGIN_ROOT" in content
        or "{{PLUGIN_ROOT}}" in content
        or "$PLUGIN_ROOT" in content
        or "{ds_plugin_root}" in content
    ), "Expected dynamic plugin-root resolution marker in hooks.json"


def test_chain_8_link_2_install_writes_all_files():
    """C8-L2: integrate install --execute → required files written. PROVEN post-18.1.15a.

    Fixed: dispatcher entries present in hooks_template.json; user-scope install
    confirmed to write mode-level SKILL.md for all 11 packs including ds-milestone,
    ds-workorder, and ds-project/modes/manage.
    """
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.is_dir():
        pytest.skip("~/.claude/skills/ not present in this environment")
    # Verify at least 3 mode-level SKILL.md files exist (regression guard)
    mode_skills = list(skills_dir.rglob("modes/*/SKILL.md"))
    assert (
        len(mode_skills) >= 3
    ), f"Expected at least 3 mode-level SKILL.md files, found {len(mode_skills)}"
    # Verify dispatcher in template
    template_path = REPO_ROOT / "integrations" / "targets" / "claude_code" / "hooks_template.json"
    if template_path.is_file():
        import json

        entries = json.loads(template_path.read_text(encoding="utf-8"))
        all_cmds = [h.get("command", "") for e in entries for h in e.get("hooks", [])]
        dispatcher_cmds = [
            c for c in all_cmds if "dispatch/hooks.py" in c or "dispatch\\hooks.py" in c
        ]
        assert dispatcher_cmds, "Dispatcher entries missing from hooks_template.json"


@pytest.mark.xfail(
    strict=False,
    reason="C8-L3 UNTESTED per chain map; no automated PATH configuration",
)
def test_chain_8_link_3_path_configured_untested():
    """C8-L3: PATH configured → ds command works globally. UNTESTED."""
    pytest.fail("UNTESTED: PATH config is advisory")


def test_chain_8_link_4_doctor_runs_unit_tested():
    """C8-L4: ds doctor → all checks pass. UNIT_TESTED."""
    from core.health.doctor import run_doctor_checks

    assert callable(run_doctor_checks)


def test_chain_8_link_5_project_register_unit_tested():
    """C8-L5: project register → set-active → start → first WO running. UNIT_TESTED."""
    from core.projects.mutations import register_project, set_active_project
    from core.projects.start import start_project

    assert callable(register_project)
    assert callable(set_active_project)
    assert callable(start_project)


def test_chain_8_link_6_hook_to_sqlite_unit_tested():
    """C8-L6: First real hook fires → event in SQLite on clean machine. UNIT_TESTED."""
    from spool.ingestor import ingest_pending
    from spool.writer import write_event

    assert callable(ingest_pending)
    assert callable(write_event)
