"""WO-GAP-FANOUT: the verify plane must not create work faster than it can be closed.

MEASURED 2026-08-21 on the live authority, which is why this work order exists:

    work orders created 08-19..08-21 : 118
    closed in the same window        :  43      net +75, 140 open

    duplicate auto-spawned titles:
      x11  "Add missing adversarial tests for durable/reachable failure modes"
      x8   "Add missing test coverage"
    -> 19 of the 25 auto-spawned work orders were the SAME TWO findings.

ROOT CAUSE, proven rather than guessed: ``_gap_key`` returns
``{reviewed_work_order_id}::{category}``, so a generic finding gets a different key on
every reviewed work order. The eleven duplicates carried eleven distinct gap-key
markers, identical after the ``::``. Dedup worked exactly as written; the key was one
field too specific.

A PRIOR WORK ORDER FOUND THIS AND FIXED IT TOO NARROWLY. WO-GAP-DEDUPE-CLASS added
``_ADVISORY_PROJECT_WIDE_CATEGORIES`` — an allowlist that held exactly one entry while
two unlisted phrasings produced the fan-out above. So the allowlist is extended AND
backed by a rule that needs no prediction.

The operator's report was that something else always gets surfaced by the review agent,
and that this is why scheduled work does not get finished. That is not a reviewer being
unreasonable. It is 2.7 work orders created per one closed.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_gaps import (
    _ADVISORY_PROJECT_WIDE_CATEGORIES,
    _ATTACH_ROUNDS_BEFORE_PRESSURE,
    _PROJECT_WIDE_AFTER_N_OPEN_SPAWNS,
    _falsification_to_gaps,
    _gap_key,
    _insert_gap_work_orders,
    _violations_to_gaps,
)

_NOW = "2026-08-21T00:00:00+00:00"

# The exact titles measured in the live authority, so this suite tracks the real classes
# rather than invented ones.
_ADVERSARIAL = "Add missing adversarial tests for durable/reachable failure modes"
_COVERAGE = "Add missing test coverage"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _project(conn: sqlite3.Connection) -> str:
    project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", _NOW, _NOW),
    )
    return project_id


def _reviewed_wo(conn: sqlite3.Connection, project_id: str, status: str = "closed") -> str:
    """A reviewed work order. CLOSED by default, because spawning a sibling only happens
    for a closed reviewed work order — an OPEN one absorbs the gap as a task instead."""
    wo_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'reviewed','d','infrastructure',?,?,?)",
        (wo_id, project_id, status, _NOW, _NOW),
    )
    return wo_id


def _spawn(conn: sqlite3.Connection, project_id: str, reviewed: str, title: str) -> list[dict]:
    return _insert_gap_work_orders(
        conn,
        gaps=[{"title": title, "description": "d", "work_order_type": "cleanup", "tasks": []}],
        project_id=project_id,
        milestone_id=None,
        reviewed_work_order_id=reviewed,
        reviewed_wo_title="reviewed",
        reviewed_wo_sequence=1,
    )


def _open_count(conn: sqlite3.Connection, title: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM business_work_orders"
        " WHERE title = ? AND status IN ('created','in_progress')",
        (title,),
    ).fetchone()[0]


# ── Task 1: the generic class dedups project-wide ─────────────────────────────


def test_a_generic_class_spawns_once_project_wide(db):
    """The x11 case. Eleven different reviewed work orders, one tracking work order.

    Drives the real ``_insert_gap_work_orders`` against a real bootstrapped authority,
    because the defect lived in the interaction between the key and the lookup query — a
    stubbed spawner would have reproduced neither.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)

    for _ in range(11):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), _ADVERSARIAL)
    conn.commit()

    assert (
        _open_count(conn, _ADVERSARIAL) == 1
    ), "eleven reviewed work orders produced eleven duplicates before this fix"
    conn.close()


def test_the_second_measured_class_also_dedups(db):
    """The x8 case. Its producer (``coverage_gaps`` from the correctness grader) emits no
    severity field at all, so there is nothing to filter on — project-wide dedup is the
    correct control there rather than an invented severity filter."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    for _ in range(8):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), _COVERAGE)
    conn.commit()
    assert _open_count(conn, _COVERAGE) == 1
    conn.close()


def test_a_third_occurrence_self_corrects_without_an_allowlist_entry(db):
    """THE BACKSTOP, and the reason the allowlist alone cannot hold.

    WO-GAP-DEDUPE-CLASS added the allowlist with one entry; two later phrasings sailed
    past it and fanned out nineteen times. A class the grader has not phrased yet will do
    the same. So a category with N open spawns across different reviewed work orders
    becomes project-wide whatever it is called — bounding an unknown future class at N
    instead of leaving it unbounded.
    """
    unlisted = "Some phrasing nobody has predicted yet"
    assert "some-phrasing-nobody-has-predicted-yet" not in _ADVISORY_PROJECT_WIDE_CATEGORIES

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    for _ in range(6):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), unlisted)
    conn.commit()

    open_now = _open_count(conn, unlisted)
    assert open_now == _PROJECT_WIDE_AFTER_N_OPEN_SPAWNS, (
        f"an unlisted class must self-correct at {_PROJECT_WIDE_AFTER_N_OPEN_SPAWNS},"
        f" got {open_now} open after six reviews"
    )
    conn.close()


# ── Task 2: a content-specific gap must STILL scope to its work order ─────────


def test_a_content_specific_gap_stays_scoped_to_its_work_order(db):
    """The converse, and the reason the key was written this way in the first place.

    A finding like "task 3 was never implemented" is about ONE work order. Widening
    everything to dedup project-wide would merge distinct per-WO findings and hide real
    work — strictly worse than the fan-out. The backstop only fires on a class that has
    demonstrably repeated, so a genuine per-WO gap is never merged on first appearance.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    wo_a, wo_b = _reviewed_wo(conn, project_id), _reviewed_wo(conn, project_id)

    gap_a = {"title": "Implement task 3 of the delivery boundary", "category": "task-3-boundary"}
    gap_b = {"title": "Implement task 3 of the hook accounting", "category": "task-3-hooks"}
    key_a = _gap_key(wo_a, gap_a, conn=conn, project_id=project_id)
    key_b = _gap_key(wo_b, gap_b, conn=conn, project_id=project_id)

    assert key_a.startswith(wo_a), "a content-specific gap keeps its reviewed-WO scope"
    assert key_b.startswith(wo_b)
    assert key_a != key_b, "two different per-WO findings must not collapse into one"
    conn.close()


def test_the_same_specific_gap_on_the_same_work_order_still_dedups(db):
    """Re-reviewing one work order must not duplicate its own findings — the original
    guarantee, unchanged by this fix."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id)  # closed: exercises the spawn path
    title = "Wire the specific thing this one work order missed"
    _spawn(conn, project_id, reviewed, title)
    _spawn(conn, project_id, reviewed, title)
    conn.commit()
    assert _open_count(conn, title) == 1
    conn.close()


def test_the_backstop_cannot_break_a_verify(db):
    """A dedup backstop that raises would take verify down with it, which is a worse
    outcome than the fan-out it prevents. An unusable connection degrades to the
    original per-WO key rather than erroring."""

    class Hostile:
        def execute(self, *_a, **_k):
            raise sqlite3.OperationalError("no such table")

    reviewed = str(uuid.uuid4())
    key = _gap_key(
        reviewed,
        {"title": "anything", "category": "anything"},
        conn=Hostile(),
        project_id="p",
    )
    assert key.startswith(reviewed), "it falls back to the scoped key instead of raising"


# ── Task 4: severity floor ────────────────────────────────────────────────────


def test_a_warning_severity_finding_does_not_spawn_a_work_order():
    """Already true for every producer that HAS a severity field, and pinned here because
    nothing asserted it.

    A warning that becomes a work order is how a reviewer's observation turns into
    scheduling debt. Warning-severity falsification scenarios stay in the
    unverified-risk ledger, which already exists and already surfaces at close.
    """
    warning_only = [
        {"status": "PROPOSED", "severity": "warning", "scenario": "a milder worst case"},
        {"status": "UNVERIFIED", "severity": "error", "scenario": "cannot be tested yet"},
    ]
    assert (
        _falsification_to_gaps(warning_only) == []
    ), "only error-severity PROPOSED scenarios may spawn work"

    with_error = [
        {"status": "PROPOSED", "severity": "error", "scenario": "crash mid-write is untested"},
    ]
    assert _falsification_to_gaps(with_error), "an error-severity testable gap still spawns"


# ── Gaps belong on the work order they were found in ──────────────────────────


def test_a_gap_on_an_open_work_order_becomes_a_task_on_it(db):
    """Operator ruling: stop registering work orders where tasks belong.

    Measured on the ten open reviewer spawns: five were findings about the very work
    order under review — its own unfinished work. Spawning a sibling declares the
    reviewed work order complete and re-homes its remainder, routing AROUND the
    tasks_done gate that already refuses to close a work order with open tasks.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")

    before = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=?", (reviewed,)
    ).fetchone()[0]
    result = _insert_gap_work_orders(
        conn,
        gaps=[
            {
                "title": "Task 3 was never implemented",
                "description": "d",
                "work_order_type": "cleanup",
                "tasks": [{"title": "Implement task 3", "description": "the remainder"}],
            }
        ],
        project_id=project_id,
        milestone_id=None,
        reviewed_work_order_id=reviewed,
        reviewed_wo_title="reviewed",
        reviewed_wo_sequence=1,
        reviewed_wo_incomplete=True,  # the verdict said the work is not done
    )
    conn.commit()

    assert result and result[0]["attached_to_reviewed"] is True
    assert result[0]["work_order_id"] == reviewed, "the task lands on the reviewed work order"

    after = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=?", (reviewed,)
    ).fetchone()[0]
    assert after == before + 1, "one task added to the reviewed work order"

    siblings = conn.execute(
        "SELECT COUNT(*) FROM business_work_orders WHERE project_id=? AND work_order_id != ?",
        (project_id, reviewed),
    ).fetchone()[0]
    assert siblings == 0, "and NO sibling work order was created"
    conn.close()


def test_a_gap_on_a_closed_work_order_still_spawns_a_sibling(db):
    """The converse, and the reason the spawning path must stay: a closed work order has
    nowhere to put a task, so its findings need somewhere to live."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id)  # closed by default

    result = _spawn(conn, project_id, reviewed, "A finding on already-closed work")
    conn.commit()

    assert not result[0].get("attached_to_reviewed")
    assert result[0]["work_order_id"] != reviewed, "a closed WO cannot absorb the task"
    assert _open_count(conn, "A finding on already-closed work") == 1
    conn.close()


def test_re_reviewing_does_not_duplicate_an_attached_task(db):
    """Re-running verify on the same open work order must not accumulate copies of the
    same finding — the per-work-order equivalent of the gap-key dedup one level up."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    gap = {
        "title": "A repeated finding",
        "description": "d",
        "work_order_type": "cleanup",
        "tasks": [{"title": "Do the missing thing", "description": ""}],
    }
    for _ in range(4):
        _insert_gap_work_orders(
            conn,
            gaps=[gap],
            project_id=project_id,
            milestone_id=None,
            reviewed_work_order_id=reviewed,
            reviewed_wo_title="reviewed",
            reviewed_wo_sequence=1,
            reviewed_wo_incomplete=True,
        )
    conn.commit()

    n = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=? AND title=?",
        (reviewed, "Do the missing thing"),
    ).fetchone()[0]
    assert n == 1, f"four reviews, one task — got {n}"
    conn.close()


# ── An unreviewable finding is not work ───────────────────────────────────────


def test_an_unlocatable_violation_does_not_become_work():
    """THE MEASURED NONSENSE CASE, verbatim from the authority.

    The correctness grader reported "independent review unverifiable — no diff
    provided" because it could not reach the target repo. The spawner turned that into
    work order 58e21003, "Fix architectural violations flagged by correctness grader",
    whose single task read "Fix N/A: independent review unverifiable — no diff provided
    in N/A". The reviewer's INABILITY to review was laundered into scheduled work.
    """
    unlocatable = [
        {"rule": "N/A", "file": "N/A", "detail": "independent review unverifiable — no diff"},
        {"rule": "", "file": None, "detail": "could not read the repo"},
    ]
    assert (
        _violations_to_gaps(unlocatable, [], []) == []
    ), "a grader reporting it could not judge must not create work"


def test_a_locatable_violation_still_becomes_work():
    """The converse — this filter must not swallow real findings."""
    real = [{"rule": "Rule 3: business_* writes", "file": "core/x.py", "detail": "ad-hoc write"}]
    gaps = _violations_to_gaps(real, [], [])
    assert len(gaps) == 1
    assert gaps[0]["tasks"][0]["title"] == "Fix Rule 3: business_* writes in core/x.py"


def test_a_partially_locatable_violation_is_kept():
    """A rule with no file, or a file with no rule, still points somewhere. Only BOTH
    missing means the grader could not judge."""
    assert _violations_to_gaps([{"rule": "SECURITY", "file": "N/A", "detail": "d"}], [], [])
    assert _violations_to_gaps([{"rule": "", "file": "core/y.py", "detail": "d"}], [], [])


def test_a_passing_verdicts_advisory_gap_does_not_block_the_close_it_approved(db):
    """Caught by an EXISTING test, not by me: the first cut attached tasks whenever the
    reviewed work order was open, so a PASSING verify carrying a warning-severity gap
    would have added blocking tasks to the work order it had just certified — the
    review's own approval could not then be acted on. Attaching is for work the verdict
    says is NOT done."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")

    result = _insert_gap_work_orders(
        conn,
        gaps=[
            {
                "title": "An advisory note about finished work",
                "description": "d",
                "work_order_type": "documentation",
                "tasks": [{"title": "Consider documenting this", "description": ""}],
            }
        ],
        project_id=project_id,
        milestone_id=None,
        reviewed_work_order_id=reviewed,
        reviewed_wo_title="reviewed",
        reviewed_wo_sequence=1,
        reviewed_wo_incomplete=False,  # the verdict PASSED
    )
    conn.commit()

    assert not result[0].get(
        "attached_to_reviewed"
    ), "a passing verdict must not add blocking tasks"
    assert result[0]["work_order_id"] != reviewed
    blocking = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=? AND status='pending'",
        (reviewed,),
    ).fetchone()[0]
    assert blocking == 0, "the certified work order stays closable"
    conn.close()


# ── The attach loop is bounded, and the bound is visible ──────────────────────


def _attach(conn, project_id, reviewed, gap_title, task_title):
    return _insert_gap_work_orders(
        conn,
        gaps=[
            {
                "title": gap_title,
                "description": "d",
                "work_order_type": "cleanup",
                "tasks": [{"title": task_title, "description": ""}],
            }
        ],
        project_id=project_id,
        milestone_id=None,
        reviewed_work_order_id=reviewed,
        reviewed_wo_title="reviewed",
        reviewed_wo_sequence=1,
        reviewed_wo_incomplete=True,
    )


def test_attached_tasks_carry_their_gap_key(db):
    """Rounds have to be countable, and title dedup cannot count them: it stops the SAME
    finding repeating and says nothing about a NEW finding each round. The key rides the
    task so the loop can be measured."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    _attach(conn, project_id, reviewed, "Finding one", "Do thing one")
    conn.commit()

    desc = conn.execute(
        "SELECT description FROM business_tasks WHERE work_order_id=? AND title=?",
        (reviewed, "Do thing one"),
    ).fetchone()[0]
    assert "[gap-attached: " in desc, f"the attached task must carry its gap key; got {desc!r}"
    assert reviewed in desc or "::" in desc
    conn.close()


def test_a_first_attachment_raises_no_pressure_warning(db):
    """A work order absorbing its own first finding is normal. Warning on it would make
    the signal noise, which is the failure mode this whole work order is about."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    result = _attach(conn, project_id, reviewed, "Finding one", "Do thing one")
    conn.commit()
    assert "attachment_pressure" not in result[0]
    conn.close()


def test_repeated_attachment_rounds_are_counted_and_surfaced(db):
    """THE TRADEOFF THIS BOUNDS. Attaching makes a failing verdict block the close via
    tasks_done -- honest, because the work order genuinely is not done. But
    verify -> attach -> fix -> verify -> attach a NEW finding is the original complaint
    ("something else always gets surfaced") wearing a blocking face instead of an
    inflating one.

    Attaching still happens; the growth stops being silent, and the honest exit is
    named.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")

    results = []
    for i in range(_ATTACH_ROUNDS_BEFORE_PRESSURE):
        results.append(_attach(conn, project_id, reviewed, f"Finding {i}", f"Do thing {i}"))
        conn.commit()

    early = [r[0] for r in results[:-1]]
    assert all("attachment_pressure" not in r for r in early), "quiet below the bound"

    final = results[-1][0]
    assert (
        "attachment_pressure" in final
    ), f"round {_ATTACH_ROUNDS_BEFORE_PRESSURE} must surface the loop; got {final}"
    message = final["attachment_pressure"]
    assert str(_ATTACH_ROUNDS_BEFORE_PRESSURE) in message, "name how many rounds"
    assert "carry" in message.lower(), "and name the honest exit"

    # Attaching CONTINUES -- this bounds visibility, it does not block the work.
    assert final["tasks_added"] == 1
    total = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=?", (reviewed,)
    ).fetchone()[0]
    assert total == _ATTACH_ROUNDS_BEFORE_PRESSURE
    conn.close()


def test_the_same_finding_repeating_does_not_count_as_a_new_round(db):
    """Pressure must measure DISTINCT findings. Re-running verify on an unchanged work
    order re-reports the same gap; counting that as escalation would fire the warning on
    a work order nobody added anything to."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    for _ in range(_ATTACH_ROUNDS_BEFORE_PRESSURE + 2):
        result = _attach(conn, project_id, reviewed, "One finding", "Do the one thing")
        conn.commit()
    assert "attachment_pressure" not in result[0], "one finding re-reported is not N rounds"
    total = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE work_order_id=?", (reviewed,)
    ).fetchone()[0]
    assert total == 1, "and it stays one task"
    conn.close()


def test_the_verdict_carries_the_pressure_signal():
    """A bound nobody can see is the same defect as no bound. verify_main must compute it
    unconditionally and record it, or this is a value with no reader -- the exact shape
    this milestone keeps finding."""
    import inspect

    from core.work_orders import verify_main

    # deterministic-first: structural assertion -- driving verify_work_order needs four
    # grader subprocesses, a live authority and a git history; the wiring is what is
    # under test.
    src = inspect.getsource(verify_main)
    assert "attachment_pressure = _pressure[0] if _pressure else None" in src
    assert '"attachment_pressure": attachment_pressure,' in src, "it must ride the verdict"


def test_the_verify_cli_says_attached_not_created(db):
    """The reviewer caught this on my own code: after gap-as-task the CLI still printed
    "Gap work orders created (N)" and listed ids for gaps that were ATTACHED, naming work
    orders that were never created and hiding where the work actually went."""
    import inspect

    from interfaces.cli.commands import work_order_query

    # deterministic-first: structural assertion — the print path needs a completed verify
    # with four grader subprocesses; the branch selection is what is under test.
    src = inspect.getsource(work_order_query)
    assert "Gaps added as tasks on this work order" in src
    assert "attached_to_reviewed" in src, "the two cases must be distinguished"
    assert "ATTACHMENT PRESSURE" in src, "the bound must reach the operator"


def test_the_pressure_signal_reaches_close_through_the_shared_reader(db):
    """A bound nobody can see is not a bound. Close reads it via verdict_state — the same
    reader the merge check uses — rather than a second implementation that could
    disagree."""
    from core.gates.merge_readiness import work_order_attachment_pressure
    from core.work_orders.artifacts import set_wo_artifact

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    wo = _reviewed_wo(conn, project_id, status="in_progress")
    conn.commit()
    conn.close()

    assert work_order_attachment_pressure(wo, db_path=db) is None, "silent with no verdict"

    set_wo_artifact(
        wo,
        "review_verdict",
        json.dumps({"passed": False, "attachment_pressure": "absorbed gaps on 3 reviews"}),
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )
    assert work_order_attachment_pressure(wo, db_path=db) == "absorbed gaps on 3 reviews"


# ── Adversarial: the four worst cases the falsification analyst found in this diff ──
#
# All four were REAL defects in code written the same night, and two were severe. The
# analyst read the diff; running the suite would not have found any of them.


def test_an_attached_task_emits_a_canonical_event_so_it_survives_a_rebuild(db, monkeypatch):
    """partial_failure. business_tasks is a PROJECTION:
    TaskProjection.target_tables == ["business_tasks"], and the framework's default
    pre_rebuild does `DELETE FROM business_tasks` before replaying canonical events.

    _attach_gap_tasks wrote rows DIRECTLY with no event, so every attached gap task would
    have been permanently deleted by the next projection rebuild — silently taking the
    reviewed work order's remaining work with it. Normal task creation has always emitted
    task.created (mutations.py); I copied the sibling-spawn INSERT instead.
    """
    emitted: list[dict] = []

    import spool.writer as _writer

    monkeypatch.setattr(
        _writer, "write_event", lambda envelope: emitted.append({"type": envelope.event_type})
    )

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    _attach(conn, project_id, reviewed, "A finding", "Do the thing")
    conn.commit()

    assert any(
        e["type"] == "task.created" for e in emitted
    ), f"an attached task must emit task.created or a rebuild deletes it; got {emitted}"
    conn.close()


def test_a_task_whose_event_could_not_be_emitted_says_it_is_rebuild_fragile(db, monkeypatch):
    """The converse: if the spool cannot be written, the row is still created (losing the
    task would be worse) but must not LOOK durable."""
    import spool.writer as _writer

    def _boom(_envelope):
        raise OSError("spool unwritable")

    monkeypatch.setattr(_writer, "write_event", _boom)

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id, status="in_progress")
    _attach(conn, project_id, reviewed, "A finding", "Do the thing")
    conn.commit()

    desc = conn.execute(
        "SELECT description FROM business_tasks WHERE work_order_id=? AND title=?",
        (reviewed, "Do the thing"),
    ).fetchone()[0]
    assert "will not survive a projection rebuild" in desc, desc
    conn.close()


def test_the_real_unreviewable_value_does_not_become_work():
    """malformed_input, and the sharpest miss of the night. The first filter matched
    sentinels EXACTLY. The live grader writes the sentinel as the start of a SENTENCE —
    the stored value was rule="N/A: independent review unverifiable - no diff provided",
    file="N/A" — so it passed and the nonsense work order stayed reachable.

    Driven against that exact stored value, the old filter reproduced work order
    58e21003's task title verbatim: "Fix N/A: independent review unverifiable - no diff
    provided in N/A". My own test had used rule="N/A", a simplification I invented, which
    is precisely the derive-the-fixture-from-the-real-artifact rule I had been enforcing
    on everyone else.
    """
    real = {
        "rule": "N/A: independent review unverifiable - no diff provided",
        "file": "N/A",
        "detail": "The review input contained no git diff or code content",
    }
    assert (
        _violations_to_gaps([real], [], []) == []
    ), "the grader reporting its own inability must not become scheduled work"

    for rule, file in [
        ("unknown - could not read the repo", "none"),
        ("", None),
        ("N/A", "N/A"),
    ]:
        assert _violations_to_gaps([{"rule": rule, "file": file}], [], []) == []


def test_a_locatable_violation_survives_the_stricter_filter():
    """The filter must not swallow real findings — a rule name, a path, or either alone."""
    for rule, file in [
        ("Rule 3: business_* writes", "core/x.py"),
        ("SECURITY", "N/A"),
        ("", "core/y.py"),
        ("N/A", "core\\gates\\z.py"),
    ]:
        assert _violations_to_gaps(
            [{"rule": rule, "file": file, "detail": "d"}], [], []
        ), f"real finding dropped: rule={rule!r} file={file!r}"


def test_a_closed_project_wide_tracker_does_not_swallow_a_new_occurrence(db):
    """empty_absent_state. Once a category is project-wide the lookup matches ANY status,
    so as soon as its single tracking work order was CLOSED every future gap of that class
    took the respawn_suppressed branch — tasks inserted nowhere, finding silently lost.

    Before the project-wide key existed the reviewed-WO id kept keys distinct and a new
    occurrence always spawned; making the class dedup project-wide opened the hole. A
    resolution is only true for the instance that closed it.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)

    first = _spawn(conn, project_id, _reviewed_wo(conn, project_id), _ADVERSARIAL)
    conn.commit()
    tracker = first[0]["work_order_id"]
    conn.execute(
        "UPDATE business_work_orders SET status='closed' WHERE work_order_id=?", (tracker,)
    )
    conn.commit()
    assert _open_count(conn, _ADVERSARIAL) == 0, "precondition: the only tracker is closed"

    again = _spawn(conn, project_id, _reviewed_wo(conn, project_id), _ADVERSARIAL)
    conn.commit()

    assert not again[0].get("respawn_suppressed"), "a new occurrence must not be swallowed"
    assert _open_count(conn, _ADVERSARIAL) == 1, "a fresh tracker exists for the new finding"
    conn.close()


def test_a_closed_work_order_specific_finding_is_still_suppressed(db):
    """The half of the respawn cap that must survive: THIS work order's finding was
    resolved and closed, so re-reporting it is not new information."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id)
    title = "A finding specific to one work order"
    first = _spawn(conn, project_id, reviewed, title)
    conn.commit()
    conn.execute(
        "UPDATE business_work_orders SET status='closed' WHERE work_order_id=?",
        (first[0]["work_order_id"],),
    )
    conn.commit()

    again = _spawn(conn, project_id, reviewed, title)
    assert again[0].get("respawn_suppressed") is True
    conn.close()


# ── The drain, repeatable ─────────────────────────────────────────────────────


def test_the_drain_previews_before_it_changes_anything(db):
    """The first drain was a one-off script run by hand. A destructive maintenance action
    should be previewable, and re-runnable when the next class fans out before the
    backstop trips."""
    from core.work_orders.verify_gaps import drain_fanned_out_categories

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    # Two open spawns of one category, as a pre-backstop fan-out would leave them.
    for _ in range(2):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), "Some fanned out class")
    conn.commit()
    before = _open_count(conn, "Some fanned out class")
    assert before == 2, f"precondition: two open spawns, got {before}"

    preview = drain_fanned_out_categories(conn, project_id, apply=False)
    assert preview["applied"] is False
    assert preview["categories_fanned_out"] == 1
    assert preview["would_cancel"] == 1
    assert _open_count(conn, "Some fanned out class") == 2, "preview must change nothing"

    applied = drain_fanned_out_categories(conn, project_id, apply=True)
    conn.commit()
    assert applied["applied"] is True
    assert applied["cancelled"] == 1
    assert _open_count(conn, "Some fanned out class") == 1, "collapsed to the earliest"
    conn.close()


def test_the_drain_is_idempotent_and_records_why(db):
    """Re-running must be safe, and a cancelled duplicate must say what absorbed it —
    a consolidation nobody can trace is indistinguishable from lost work."""
    from core.work_orders.verify_gaps import drain_fanned_out_categories

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    for _ in range(3):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), "Another fanned out class")
    conn.commit()

    drain_fanned_out_categories(conn, project_id, apply=True)
    conn.commit()
    second = drain_fanned_out_categories(conn, project_id, apply=True)
    conn.commit()
    assert second["categories_fanned_out"] == 0, "nothing left to drain"

    row = conn.execute(
        "SELECT description FROM business_work_orders"
        " WHERE title='Another fanned out class' AND status='cancelled' LIMIT 1"
    ).fetchone()
    assert row and "[DRAINED" in row[0]
    assert "consolidated into" in row[0]
    conn.close()
