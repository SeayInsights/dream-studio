"""WO-HOOK-WRITE-ACCOUNTING: the stop hook must see the writes that happened.

Registered on the operator's instruction to make it trustworthy — "yes, register that
so we can trust it" — after the hook blocked sessions that had complied.

TWO DEFECTS, both observed repeatedly on 2026-08-19/20:

1. ``authority_write_since`` asked ``business_tasks`` for ``status = 'done'`` while
   ``ds work-order task-done`` writes ``'complete'``. Live counts: 2,058 complete
   against 27 done, all legacy, last written 2026-06-29 — so that fallback had
   matched nothing for months. Four consecutive successful task-done calls on
   befde290 were then reported as "no authority write was recorded this session".

2. ``ds work-order affirm-impact`` stores an ``impact_affirmation`` artifact and
   satisfies the ``change_impact_affirmed`` close gate, but did not count. A session
   whose only honest remaining write was an affirmation therefore had NO truthful way
   to satisfy the hook: every task already complete, close blocked on a gate. Hit on
   758fbedd, c14c2eea, 66e7ebc8.

The hook fails SAFE — it blocks rather than permits — so nothing false-done got
through. That is exactly why this matters: an enforcement surface that reports a
violation where none exists teaches operators to route around it, and the escape
hatches (DS_ENFORCE=0, a lower tier) are what a false positive pushes people toward.

The last test here is the one that must never be softened: a work order edited with
no task-done, no close and no affirmation is still reported. Trading a false positive
for a false negative would be strictly worse — catching unrecorded work is the whole
job.
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from runtime.lib import enforcement  # noqa: E402

# Written as byte values, not escapes: an escaped form of these two literals was
# mangled twice by shell quoting while this file was being authored.
CRLF = bytes([13, 10])
LF = bytes([10])

# The session started an hour ago; "since" is that instant.
_SESSION_START = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
_SINCE = _SESSION_START.isoformat()
_DURING = (_SESSION_START + timedelta(minutes=5)).isoformat()
_BEFORE = (_SESSION_START - timedelta(days=3)).isoformat()

_DDL = """
CREATE TABLE business_work_orders (
    work_order_id TEXT, project_id TEXT, title TEXT, status TEXT,
    started_at TEXT, closed_at TEXT, created_at TEXT
);
CREATE TABLE business_tasks (
    task_id TEXT, work_order_id TEXT, status TEXT, updated_at TEXT
);
CREATE TABLE business_work_order_artifacts (
    work_order_id TEXT, kind TEXT, instance_key TEXT, content TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE business_canonical_events (
    event_id TEXT, work_order_id TEXT, event_type TEXT,
    event_timestamp TEXT, received_at TEXT
);
"""


@pytest.fixture
def authority(tmp_path, monkeypatch) -> tuple[Path, str]:
    """A hermetic authority with one in_progress WO and nothing recorded yet."""
    db = tmp_path / "studio.db"
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(db)
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, started_at, created_at)"
        " VALUES (?, 'p', 'WO', 'in_progress', ?, ?)",
        (wo_id, _BEFORE, _BEFORE),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(enforcement, "AUTHORITY_DB", db)
    return db, wo_id


def _exec(db: Path, sql: str, params: tuple) -> None:
    conn = sqlite3.connect(db)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


# ── Task 1: the status literal the writer actually uses ───────────────────────


def test_a_completed_task_counts_as_an_authority_write(authority):
    """The observed false positive: four task-done calls, all landed, all invisible."""
    db, wo_id = authority
    assert enforcement.authority_write_since(wo_id, _SINCE) is False, "precondition: nothing yet"

    _exec(
        db,
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'complete',?)",
        (str(uuid.uuid4()), wo_id, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_a_legacy_done_task_still_counts(authority):
    """27 historical rows carry 'done'. Swapping one hard-coded literal for another
    would have silently stopped counting them."""
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'done',?)",
        (str(uuid.uuid4()), wo_id, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_the_reader_accepts_the_status_the_real_writer_produces():
    """THE DRIFT PIN, and the reason this defect could exist at all.

    The reader's accepted set is asserted against what the WRITER actually writes —
    ``TaskProjection`` handling a ``task.completed`` event, the code path
    ``ds work-order task-done`` goes through. Not a grep of the projection source and
    not a hand-copied literal: those are how the reader drifted from the writer for
    months in the first place.

    This module is copied verbatim into the installed hook trees and may only use the
    stdlib, so it cannot import a shared constant from ``core``. A test that runs the
    writer is the enforcement available across that boundary.
    """
    from core.projections.task_projection import TaskProjection

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE business_tasks ("
        " task_id TEXT PRIMARY KEY, work_order_id TEXT, project_id TEXT, title TEXT,"
        " description TEXT, status TEXT, created_at TEXT, updated_at TEXT,"
        " last_event_id TEXT, acceptance_criteria TEXT);"
        "CREATE TABLE projection_offsets (projection TEXT, last_event_id TEXT);"
    )
    task_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES (?, 'wo', 'p', 't', 'pending', ?, ?)",
        (task_id, _BEFORE, _BEFORE),
    )

    projection = TaskProjection()
    applied = projection.handle(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "task.completed",
            "event_timestamp": _DURING,
            "task_id": task_id,
            "work_order_id": "wo",
            "project_id": "p",
            "payload": {},
        },
        conn,
    )
    assert applied == 1, "precondition: the writer applied the completion"
    written = conn.execute(
        "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()[0]
    conn.close()

    assert written in enforcement.TASK_DONE_STATUSES, (
        f"the writer produces status {written!r} and the stop hook accepts "
        f"{enforcement.TASK_DONE_STATUSES} — they have drifted apart again"
    )


# ── Task 2: an impact affirmation is an authority write ───────────────────────


def test_an_impact_affirmation_counts_as_an_authority_write(authority):
    """The second false positive, and the crueller one: the session had NO truthful
    way to comply — every task complete, close blocked on a gate, and the one write
    left to make did not count."""
    db, wo_id = authority
    assert enforcement.authority_write_since(wo_id, _SINCE) is False

    _exec(
        db,
        "INSERT INTO business_work_order_artifacts"
        " (work_order_id, kind, instance_key, content, created_at, updated_at)"
        " VALUES (?,'impact_affirmation','','{}',?,?)",
        (wo_id, _DURING, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_an_affirmation_from_a_previous_session_does_not_count(authority):
    """Otherwise the hook would go permanently quiet for any WO ever affirmed —
    trading the false positive for a false negative on every later session."""
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_work_order_artifacts"
        " (work_order_id, kind, instance_key, content, created_at, updated_at)"
        " VALUES (?,'impact_affirmation','','{}',?,?)",
        (wo_id, _BEFORE, _BEFORE),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is False


def test_a_verdict_artifact_is_not_counted_as_recorded_work(authority):
    """Deliberately narrow. A review verdict is evidence ABOUT work, not a record
    that work was completed — counting every artifact kind would let a session that
    only ran verify satisfy a hook whose question is "did you record what you did"."""
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_work_order_artifacts"
        " (work_order_id, kind, instance_key, content, created_at, updated_at)"
        " VALUES (?,'review_verdict','','{}',?,?)",
        (wo_id, _DURING, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is False


# ── Task 3: the check must not depend on ingestion having run ─────────────────


def test_a_write_counts_before_the_spool_is_ingested(authority):
    """The rows are written by the mutation; the canonical events arrive only once
    spool ingestion runs. Asking the event stream first made this check partly measure
    "did ingestion keep up" rather than "did the operator record work", so a compliant
    session was blocked whenever ingestion lagged.

    Here the durable row exists and the event stream is entirely empty — the exact
    state of an un-ingested spool.
    """
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'complete',?)",
        (str(uuid.uuid4()), wo_id, _DURING),
    )
    conn = sqlite3.connect(db)
    events = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
    conn.close()
    assert events == 0, "precondition: nothing has been ingested"

    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_the_event_stream_still_counts_on_its_own(authority):
    """Demoted to reinforcement, not removed: an ingested event with a lagging row
    (the other lag direction) must still count."""
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_canonical_events"
        " (event_id, work_order_id, event_type, event_timestamp, received_at)"
        " VALUES (?,?,'task.completed',?,?)",
        (str(uuid.uuid4()), wo_id, _DURING, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_an_authority_missing_the_artifacts_table_does_not_block(tmp_path, monkeypatch):
    """An older authority has no artifacts table. A missing table is a fact about the
    schema, not evidence the operator recorded nothing — and this reader must never
    turn a query error into a violation."""
    db = tmp_path / "old.db"
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE business_work_orders ("
        " work_order_id TEXT, project_id TEXT, title TEXT, status TEXT,"
        " started_at TEXT, closed_at TEXT, created_at TEXT);"
        "CREATE TABLE business_tasks ("
        " task_id TEXT, work_order_id TEXT, status TEXT, updated_at TEXT);"
        "CREATE TABLE business_canonical_events ("
        " event_id TEXT, work_order_id TEXT, event_type TEXT,"
        " event_timestamp TEXT, received_at TEXT);"
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, started_at, created_at)"
        " VALUES (?, 'p', 'WO', 'in_progress', ?, ?)",
        (wo_id, _BEFORE, _BEFORE),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'complete',?)",
        (str(uuid.uuid4()), wo_id, _DURING),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(enforcement, "AUTHORITY_DB", db)

    assert enforcement.authority_write_since(wo_id, _SINCE) is True


# ── Task 4: the true positive survives ───────────────────────────────────────


def test_unrecorded_work_is_still_reported(authority):
    """THE TEST THAT MUST NOT BE SOFTENED. A work order with no task-done, no close
    and no affirmation is unrecorded work, and the hook exists to say so. Every fix
    above widens what counts as a write; if any of them widened it to "anything at
    all", the hook would be decorative."""
    db, wo_id = authority

    # Everything present but STALE — from before this session's window.
    _exec(
        db,
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'complete',?)",
        (str(uuid.uuid4()), wo_id, _BEFORE),
    )
    _exec(
        db,
        "INSERT INTO business_canonical_events"
        " (event_id, work_order_id, event_type, event_timestamp, received_at)"
        " VALUES (?,?,'task.completed',?,?)",
        (str(uuid.uuid4()), wo_id, _BEFORE, _BEFORE),
    )
    # And a pending task, which is not a write at all.
    _exec(
        db,
        "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
        " VALUES (?,?,'pending',?)",
        (str(uuid.uuid4()), wo_id, _DURING),
    )

    assert (
        enforcement.authority_write_since(wo_id, _SINCE) is False
    ), "a session that recorded nothing must still be reported"


def test_the_observed_false_positive_case_end_to_end(authority):
    """Reconstructs befde290's state: every task complete this session and an impact
    affirmation recorded, with the spool un-ingested. That session was blocked; it
    must not be."""
    db, wo_id = authority
    for _ in range(4):
        _exec(
            db,
            "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
            " VALUES (?,?,'complete',?)",
            (str(uuid.uuid4()), wo_id, _DURING),
        )
    _exec(
        db,
        "INSERT INTO business_work_order_artifacts"
        " (work_order_id, kind, instance_key, content, created_at, updated_at)"
        " VALUES (?,'impact_affirmation','','{}',?,?)",
        (wo_id, _DURING, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_a_closed_work_order_counts(authority):
    """Unchanged behaviour, pinned because the reordering moved it."""
    db, wo_id = authority
    _exec(
        db,
        "UPDATE business_work_orders SET status = 'closed', closed_at = ? WHERE work_order_id = ?",
        (_DURING, wo_id),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is True


def test_an_unusable_window_fails_open(authority):
    """Enforcement must never brick an adapter: an unparseable timestamp yields the
    permissive result rather than an unsatisfiable block."""
    _db, wo_id = authority
    assert enforcement.authority_write_since(wo_id, "not-a-timestamp") is True


def test_a_missing_authority_fails_open(tmp_path, monkeypatch):
    monkeypatch.setattr(enforcement, "AUTHORITY_DB", tmp_path / "absent.db")
    assert enforcement.authority_write_since(str(uuid.uuid4()), _SINCE) is True


# ── Task 4 (completed): the widened reader still rejects what it must ─────────


def test_a_non_counting_event_in_the_window_is_not_a_write(authority):
    """The gap this WO's own verify named: the true-positive test only exercised
    STALE rows, so nothing proved the widened reader still rejects an in-window state
    it must not admit. `work_order.started` lands inside the session window and is not
    a record that work was completed."""
    db, wo_id = authority
    _exec(
        db,
        "INSERT INTO business_canonical_events"
        " (event_id, work_order_id, event_type, event_timestamp, received_at)"
        " VALUES (?,?,'work_order.started',?,?)",
        (str(uuid.uuid4()), wo_id, _DURING, _DURING),
    )
    assert enforcement.authority_write_since(wo_id, _SINCE) is False


def test_an_in_window_artifact_of_a_non_counting_kind_is_not_a_write(authority):
    """Same shape on the artifact side. Every fix in this WO widens what counts; if
    any widened it to "anything in the window", the hook would be decorative."""
    db, wo_id = authority
    for kind in ("report", "context", "review_verdict"):
        _exec(
            db,
            "INSERT INTO business_work_order_artifacts"
            " (work_order_id, kind, instance_key, content, created_at, updated_at)"
            " VALUES (?,?,?,'{}',?,?)",
            (wo_id, kind, kind, _DURING, _DURING),
        )
    assert enforcement.authority_write_since(wo_id, _SINCE) is False


def test_an_in_window_task_in_a_non_done_status_is_not_a_write(authority):
    """And on the task side: a task touched this session but not COMPLETED is work in
    progress, not recorded work."""
    db, wo_id = authority
    for status in ("pending", "in_progress", "blocked"):
        _exec(
            db,
            "INSERT INTO business_tasks (task_id, work_order_id, status, updated_at)"
            " VALUES (?,?,?,?)",
            (str(uuid.uuid4()), wo_id, status, _DURING),
        )
    assert enforcement.authority_write_since(wo_id, _SINCE) is False


# ── Task 5: the fix must exist where the hooks actually run ───────────────────


def test_the_projected_hook_copies_carry_this_fix():
    """``runtime/lib/enforcement.py`` is COPIED into the installed hook trees, and
    ``ds update`` is version-gated, so a canonical fix does not auto-propagate — the
    WO 46fe128b lesson, where deployed copies had silently gone stale. A fix that
    exists only in canonical/ is a fix that never fires.

    EXISTENCE OF A PROJECTION CANNOT BE ASSERTED. ``.gitignore`` line 150 ignores
    ``.claude/`` outright — ``git ls-files .claude/hooks`` returns nothing — so a fresh
    checkout has no projected tree at all, and the first version of this test
    (``assert repo_copy.is_file()``) would have hard-failed in Full CI on main while
    passing here, on the one machine that had already been projected. Caught by static
    review, not by running it: executing this suite on a projected machine can never
    reveal it. Same shape as the gitignored ``verify_*.py`` siblings that made a
    committed facade import phantom modules.

    So the portable guarantees are asserted hard, and the machine-local one only where
    it exists:

    1. canonical carries the fix;
    2. the file is in the projection MANIFEST, so any install will carry it;
    3. every projection tree present on this machine matches canonical byte-for-byte.
    """
    from core.health.doctor_shared import projected_hook_relpaths

    def _norm(path: Path) -> bytes:
        return path.read_bytes().replace(CRLF, LF)

    canonical = _norm(_REPO / "runtime" / "lib" / "enforcement.py")
    assert b"TASK_DONE_STATUSES" in canonical, "the fix must be in the canonical module"
    assert b"AUTHORITY_ARTIFACT_KINDS" in canonical

    # (2) The projection manifest is the mechanism that carries it to an install.
    # Without this the fix could be correct, tracked, and deployed nowhere.
    rels = {r.replace("\\", "/") for r in projected_hook_relpaths(_REPO)}
    assert "runtime/lib/enforcement.py" in rels, (
        "enforcement.py is not in the hook projection manifest — the fix would never"
        f" reach an install (manifest has {len(rels)} paths)"
    )

    # (3) Whatever IS deployed here must match. Both trees fire, so both are checked.
    checked = 0
    for tree in (_REPO / ".claude" / "hooks", Path.home() / ".claude" / "hooks"):
        deployed = tree / "runtime" / "lib" / "enforcement.py"
        if not deployed.is_file():
            continue
        checked += 1
        assert _norm(deployed) == canonical, (
            f"the hook projection at {deployed} is STALE and it fires — re-project it."
            " Note `ds doctor --fix` only re-projects the project scope"
            " (WO-HOOK-SCOPE-BLINDSPOT)."
        )
    if not checked:
        pytest.skip(
            "no hook projection on this machine (.claude/ is gitignored, so a fresh"
            " checkout has none) — the manifest assertion above is the portable guard"
        )
