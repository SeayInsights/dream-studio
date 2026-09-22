"""The prompt chain is delivered to the executor, not only stored.

A project is the goal its milestones answer to, a milestone the goal its work orders
answer to, a work order the goal its tasks answer to. That hierarchy is the point of the
authority, and every layer's prompt is now mandatory at creation.

NONE OF IT REACHED THE EXECUTOR. `read_work_order_brief` ran four queries against four
tables and selected four titles:

    business_projects     SELECT name                    -- not description
    business_milestones   SELECT title                   -- not description
    business_work_orders  SELECT ... title ...           -- not description
    business_tasks        SELECT title                   -- not acceptance_criteria

So `ds work-order start` handed an agent the NAME of the work, the name of the milestone
above it and a list of task names, and not one statement of what any of it was for. The
chain was written into SQLite, made mandatory, and delivered to nobody.

These tests assert both halves — the brief fetches it, and the context artifact the
executor actually reads renders it — because a value fetched into a dict nobody prints is
the same defect one step earlier.
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.start_brief import read_work_order_brief
from core.work_orders.start_context import write_work_order_context

NOW = "2026-09-22T00:00:00+00:00"

PROJECT_PROMPT = "A local-first AI orchestration platform that runs entirely on one machine."
MILESTONE_PROMPT = "Make the dashboard able to answer what a single feature cost to build."
WORK_ORDER_PROMPT = "Open the DuckDB analytics connection and hand it to the projection engine."
TASK_CRITERION = "TEST-CHECK: tests/unit/test_duckdb_runner_wiring.py"


@pytest.fixture
def authority(tmp_path: Path) -> tuple[Path, str]:
    """A real bootstrapped authority carrying one full chain, project to task."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)

    pid, mid, wid, tid = (str(uuid.uuid4()) for _ in range(4))
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, "Dream Studio", PROJECT_PROMPT, "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones (milestone_id, project_id, title, description,"
            " status, order_index, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (mid, pid, "Reporting", MILESTONE_PROMPT, "pending", 0, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id,"
            " title, description, work_order_type, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                wid,
                pid,
                mid,
                "Wire the projection",
                WORK_ORDER_PROMPT,
                "infrastructure",
                "created",
                NOW,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title,"
            " description, acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (tid, wid, pid, "Open the connection", "", TASK_CRITERION, "pending", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return db, wid


def _brief(authority, monkeypatch):
    db, wid = authority
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    return read_work_order_brief(
        work_order_id=wid,
        source_root=Path(__file__).resolve().parents[2],
        dream_studio_home=db.parent.parent,
    )


# --------------------------------------------------------------------------
# The brief fetches every layer's prompt
# --------------------------------------------------------------------------


def test_the_brief_carries_the_work_orders_own_prompt(authority, monkeypatch):
    """The one an executor most obviously needs, and the one most obviously missing:
    `business_work_orders.description` was selected by nothing."""
    assert _brief(authority, monkeypatch)["description"] == WORK_ORDER_PROMPT


def test_the_brief_carries_the_milestone_prompt_above_it(authority, monkeypatch):
    """A work order derives its goal from its milestone's. Handing over the milestone's
    TITLE and withholding its statement gives the executor a label, not a reason."""
    assert _brief(authority, monkeypatch)["milestone_description"] == MILESTONE_PROMPT


def test_the_brief_carries_the_project_prompt_above_that(authority, monkeypatch):
    assert _brief(authority, monkeypatch)["project_description"] == PROJECT_PROMPT


def test_the_brief_carries_each_tasks_acceptance_criterion(authority, monkeypatch):
    """The criterion is the half that decides whether the task is done. The title alone
    is the name of the work without the definition of finished."""
    tasks = _brief(authority, monkeypatch)["pending_tasks"]
    assert tasks == [{"title": "Open the connection", "acceptance_criteria": TASK_CRITERION}]


# --------------------------------------------------------------------------
# The artifact the executor actually reads renders it
# --------------------------------------------------------------------------


def _rendered(brief: dict, db: Path) -> str:
    """The context artifact's text, read from wherever it actually landed.

    `write_work_order_context` is authority-first: it returns None when the artifact
    table took the content, and a Path only on the disk fallback. Which branch runs
    depends on whether that table is reachable — so an earlier version of this helper
    assumed the fallback, passed when run alone, and failed all seven of its callers
    under the wider suite. That is the exact shape this file exists to fix, committed
    into its own test. `db_path` is passed explicitly rather than resolved from ambient
    state, so the answer does not depend on what ran before.
    """
    out = write_work_order_context(brief, planning_root=Path(tempfile.mkdtemp()), db_path=db)
    if out is not None:
        return out.read_text(encoding="utf-8")

    from core.work_orders.artifacts import get_wo_artifact

    stored = get_wo_artifact(brief["work_order_id"], "context", db_path=db)
    assert stored, "the context reached neither the authority nor the disk fallback"
    return stored


def test_every_layers_prompt_reaches_the_context_artifact(authority, monkeypatch):
    """A value fetched into a dict nobody prints is the same defect one step earlier."""
    text = _rendered(_brief(authority, monkeypatch), authority[0])
    for prompt in (PROJECT_PROMPT, MILESTONE_PROMPT, WORK_ORDER_PROMPT, TASK_CRITERION):
        assert prompt in text, f"missing from the context artifact: {prompt[:50]}"


def test_the_chain_reads_top_down(authority, monkeypatch):
    """Project, then milestone, then work order. An executor reading downward meets the
    widest goal first, which is the order the hierarchy is built in."""
    text = _rendered(_brief(authority, monkeypatch), authority[0])
    assert text.index(PROJECT_PROMPT) < text.index(MILESTONE_PROMPT) < text.index(WORK_ORDER_PROMPT)


def test_the_chain_comes_before_the_gates(authority, monkeypatch):
    """The first question is what this work is for, not which gates will judge it."""
    text = _rendered(_brief(authority, monkeypatch), authority[0])
    assert text.index(WORK_ORDER_PROMPT) < text.index("## Gates")


def test_a_criterion_is_rendered_under_its_own_task(authority, monkeypatch):
    text = _rendered(_brief(authority, monkeypatch), authority[0])
    task_line = text.index("- [ ] Open the connection")
    assert task_line < text.index(TASK_CRITERION)


# --------------------------------------------------------------------------
# Absence is quiet, not an empty heading
# --------------------------------------------------------------------------


def test_a_layer_with_no_prompt_prints_no_empty_heading(authority, monkeypatch):
    """Older records predate the floors and carry nothing. An empty section teaches the
    reader that the section is noise, which is how a real one gets skipped later."""
    brief = _brief(authority, monkeypatch)
    brief["project_description"] = None
    brief["milestone_description"] = "   "
    text = _rendered(brief, authority[0])
    assert "Why this project exists" not in text
    assert "What this milestone delivers" not in text
    assert WORK_ORDER_PROMPT in text, "the layer that DOES carry one must still show"


def test_no_chain_at_all_prints_no_section(authority, monkeypatch):
    brief = _brief(authority, monkeypatch)
    brief["project_description"] = None
    brief["milestone_description"] = None
    brief["description"] = None
    text = _rendered(brief, authority[0])
    assert "## The prompt chain" not in text
    assert "## Gates" in text, "the rest of the artifact must be unaffected"


def test_a_task_with_no_criterion_still_renders_its_title(authority, monkeypatch):
    brief = _brief(authority, monkeypatch)
    brief["pending_tasks"] = [{"title": "An older task", "acceptance_criteria": None}]
    text = _rendered(brief, authority[0])
    assert "- [ ] An older task" in text


# --------------------------------------------------------------------------
# The other door: `ds project state`, where an operator orients
# --------------------------------------------------------------------------


def test_project_state_carries_the_next_work_orders_prompt(authority, monkeypatch, tmp_path):
    """`ds project state` is the one command an operator runs to pick up work. It showed
    the next work order's TITLE and its milestone's TITLE and neither statement of intent
    -- the same gap the executor had at start, at the other entry point. Deciding whether
    to start a work order is exactly when its prompt matters."""
    db, wid = authority
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))

    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE business_projects SET status = 'active' WHERE project_id ="
            " (SELECT project_id FROM business_work_orders WHERE work_order_id = ?)",
            (wid,),
        )
        conn.commit()
    finally:
        conn.close()

    from core.projects.queries import get_project_state

    state = get_project_state(
        source_root=Path(__file__).resolve().parents[2],
        dream_studio_home=db.parent.parent,
        planning_root=tmp_path / "planning",
    )
    # The state is a list of projects, each with its own next work order -- a single
    # top-level `next_work_order` is what this test first looked for and there is none.
    projects = state.get("projects") or []
    assert projects, f"no projects in the state: {state.get('next_action')}"
    nxt = projects[0].get("next_work_order")
    assert nxt, f"no next work order under the project: {projects[0]}"
    assert nxt["description"] == WORK_ORDER_PROMPT
    assert nxt["milestone_description"] == MILESTONE_PROMPT
