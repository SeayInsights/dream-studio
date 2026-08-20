"""Adversarial tests the falsification analyst demanded of its own machinery.

Gap WOs 66e7ebc8 (from WO-FALSIFY-FIRST-PASS) and 72b19987 (from
WO-FALSIFY-TIMEOUT). Both were spawned automatically: the analyst read the
diffs of the falsification stage itself, named five error-severity worst cases
that were testable but untested, and DS turned them into tracked work. Each
scenario below turned out to be a real defect, not merely a coverage hole:

1. version_skew — an authority-first ledger read served the STALE copy when the
   newer one was on disk (the mirror of the skew already fixed in the writer).
2. malformed_input — a grader returning strings instead of scenario objects
   crashed the gap builder INSIDE verify's open authority transaction.
3. empty_absent_state — remediation evidence is appended after the commits, so a
   newest-first budget walk could spend the whole budget on evidence and hand the
   analyst a change set whose actual diff it never saw.
4. partial_failure — the truncation caveat lived only in the verdict, so close
   and project state reported a PARTIAL enumeration as if it were complete.
5. crash_mid_write — a crash between the ledger write and the verdict write could
   pair run N's ledger with run N-1's verdict with nothing to detect it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_gaps import _falsification_to_gaps
from core.work_orders.verify_main import _FALSIFICATION_DIFF_BUDGET, budget_falsification_diff
from core.work_orders.verify_persist import _persist_unverified_ledger, read_unverified_ledger

_SCENARIO = {
    "scenario_class": "crash_mid_write",
    "surface": "core/x.py",
    "scenario": "dies between write and read",
    "status": "PROPOSED",
    "evidence": "test_x",
    "severity": "error",
}


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


# ── 1. version_skew: newest ledger wins, not authority-first ────────────────────


def test_newer_disk_ledger_beats_a_stale_authority_copy(tmp_path):
    """Run 1's ledger lands in the authority; run 2's authority write no-ops
    (locked by verify's own transaction — the fd981a32 case) and writes disk.
    An authority-first reader served the STALE copy. Newest must win."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())

    # Run 1 → authority (one scenario).
    assert (
        _persist_unverified_ledger(wo_id, [_SCENARIO], planning_root=planning, db_path=db) is None
    )

    # Run 2 → authority write no-ops (lock), so it lands on disk with TWO scenarios.
    time.sleep(0.01)  # ensure a strictly later mtime than the authority created_at
    with patch("core.work_orders.artifacts.set_wo_artifact", return_value=False):
        disk_path = _persist_unverified_ledger(
            wo_id,
            [_SCENARIO, {**_SCENARIO, "scenario_class": "race_between_writers"}],
            planning_root=planning,
            db_path=db,
        )
    assert disk_path is not None and disk_path.is_file()
    # Make the disk copy unambiguously newer than the authority envelope.
    future = time.time() + 60
    os.utime(disk_path, (future, future))

    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None
    assert ledger["count"] == 2, "the NEWER (disk) ledger must win, not the stale authority copy"


def test_authority_wins_when_it_is_the_newer_copy(tmp_path):
    """The rule is newest-wins, not disk-wins: a stale disk copy must not shadow a
    fresher authority write (the writer removes it, and the reader agrees)."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())

    with patch("core.work_orders.artifacts.set_wo_artifact", return_value=False):
        disk_path = _persist_unverified_ledger(
            wo_id, [_SCENARIO], planning_root=planning, db_path=db
        )
    assert disk_path is not None
    old = time.time() - 3600
    os.utime(disk_path, (old, old))

    # Authority write lands now, and removes the stale disk copy.
    assert _persist_unverified_ledger(wo_id, [], planning_root=planning, db_path=db) is None
    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None and ledger["count"] == 0


# ── 2. malformed_input: a string-valued scenario list must not crash ────────────


@pytest.mark.parametrize(
    "scenarios",
    [
        ["crash mid write is untested"],  # strings instead of objects
        [_SCENARIO, "and another prose line"],  # mixed
        {
            "scenario_class": "crash_mid_write",
            "status": "PROPOSED",
            "severity": "error",
        },  # bare obj
        "scenarios were not a list at all",
        None,
    ],
)
def test_malformed_scenarios_never_raise(scenarios):
    """A live grader can return prose or a bare object. Calling .get() on those
    raised AttributeError INSIDE verify's open authority transaction, taking the
    whole verify down instead of degrading."""
    gaps = _falsification_to_gaps(scenarios)  # must not raise
    assert isinstance(gaps, list)


def test_malformed_entries_are_reported_not_silently_dropped():
    """Skipping unparseable entries silently would narrow the enumeration
    invisibly — the note makes a malformed grader reply legible."""
    gaps = _falsification_to_gaps([_SCENARIO, "prose", 42])
    assert len(gaps) == 1
    assert "2 scenario entr(ies) were malformed" in gaps[0]["description"]
    # The well-formed actionable scenario still produced its task.
    assert any("crash_mid_write" in t["title"] for t in gaps[0]["tasks"])


@pytest.mark.parametrize(
    ("payload", "expect_well_formed", "expect_malformed"),
    [
        (["crash mid write is untested"], 0, 1),
        ([_SCENARIO, "prose", 42], 1, 2),
        ({"scenario_class": "x", "status": "UNVERIFIED", "severity": "error"}, 1, 0),
        ("not a list", 0, 0),
        (None, 0, 0),
        (42, 0, 0),
        ([None, {"status": "UNVERIFIED"}], 1, 1),
        ([], 0, 0),
    ],
)
def test_the_shared_normaliser_is_the_one_shape_contract(
    payload, expect_well_formed, expect_malformed
):
    """The SECOND surface, found by this WO's own verify — twice.

    First pass: _falsification_to_gaps was hardened while verify_main's
    `_unverified` comprehension read the SAME untrusted payload and still called
    ``.get()`` on every element, so the reply task 2 describes still raised
    AttributeError inside verify's OPEN authority transaction.

    Second pass: the fix guarded verify_main, but the tests written for it COPIED
    the normalisation into the test body — so deleting the production guard would
    not have failed anything. The grader called that out as the exact shape the
    commit message had just criticised, and it was right. The contract now lives
    in one production function that both readers call, and this test calls THAT.
    """
    from core.work_orders.verify_gaps import normalise_falsification_scenarios

    well_formed, malformed = normalise_falsification_scenarios(payload)
    assert [type(s) for s in well_formed] == [dict] * expect_well_formed
    assert malformed == expect_malformed
    # Whatever survives is safe for the .get() both readers perform.
    assert isinstance(_falsification_to_gaps(well_formed), list)
    assert isinstance([s for s in well_formed if s.get("status") == "UNVERIFIED"], list)


def test_verify_main_reads_the_payload_through_the_shared_normaliser():
    """Pins the guard at its real call site rather than re-deriving it.

    ``verify_main`` must obtain its scenario list from the shared normaliser — if
    someone reverts to reading ``falsification["scenarios"]`` directly, the second
    surface is unguarded again and this fails.
    """
    import inspect

    from core.work_orders import verify_gaps, verify_main

    assert verify_main.normalise_falsification_scenarios is (
        verify_gaps.normalise_falsification_scenarios
    ), "verify_main must use the SHARED normaliser, not a private copy"

    source = inspect.getsource(verify_main.verify_work_order)
    assert "normalise_falsification_scenarios(" in source, (
        "verify_work_order must route the grader payload through the shared "
        "normaliser — a direct read of falsification['scenarios'] is the defect"
    )


def test_removing_the_guard_would_break_the_readers():
    """States the failure the guard prevents, so the guard's value is asserted and
    not merely asserted-about: the raw payload really does raise on the operations
    both readers perform."""
    raw_prose = ["crash mid write is untested", 42]
    with pytest.raises(AttributeError):
        [s for s in raw_prose if s.get("status") == "UNVERIFIED"]  # type: ignore[union-attr]

    from core.work_orders.verify_gaps import normalise_falsification_scenarios

    safe, malformed = normalise_falsification_scenarios(raw_prose)
    assert safe == [] and malformed == 2
    assert [s for s in safe if s.get("status") == "UNVERIFIED"] == []


# ── 3. empty_absent_state: evidence must not crowd out the WO's own commits ─────


def _commit(sha: str, size: int) -> str:
    return f"=== commit {sha} ===\n" + ("+x\n" * (size // 3))


def _evidence(wo: str, size: int) -> str:
    return f"=== remediation evidence (closed gap WO {wo}) ===\n" + ("+fix\n" * (size // 5))


def test_remediation_evidence_never_crowds_out_the_wos_own_commits():
    """Evidence sections are appended AFTER the commits, so a plain newest-first
    walk kept the evidence and could spend the whole budget on it — the analyst
    would then enumerate worst cases for a diff it never saw."""
    parent = _commit("parent01", 30_000)
    big_evidence = _evidence("childaaa", _FALSIFICATION_DIFF_BUDGET)
    trimmed, truncated = budget_falsification_diff(parent + big_evidence)

    assert truncated is True
    assert "parent01" in trimmed, "the WO's own commit must survive the budget"
    assert len(trimmed) <= len(parent + big_evidence)


def test_commits_are_budgeted_before_evidence_but_order_is_preserved():
    """Commits win the budget; whatever evidence fits is kept; the reader still
    sees the sections in their original order."""
    old_c = _commit("oldc0001", 20_000)
    new_c = _commit("newc0002", 20_000)
    ev = _evidence("childbbb", 30_000)
    trimmed, truncated = budget_falsification_diff(old_c + new_c + ev)
    assert truncated is True
    assert "newc0002" in trimmed
    if "oldc0001" in trimmed and "newc0002" in trimmed:
        assert trimmed.index("oldc0001") < trimmed.index("newc0002"), "original order preserved"


# ── 4. partial_failure: a truncated analysis says so downstream ─────────────────


def _seed_closeable_wo(db: Path) -> str:
    """A minimal in_progress WO with no tasks, closeable with force=True."""
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-19T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','cleanup','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()
    return wo_id


def test_truncation_caveat_reaches_the_ledger_and_close_note(tmp_path):
    """The caveat used to live only in the verdict, so close and project state
    reported a PARTIAL enumeration as if it were complete.

    This test originally stopped at the ledger despite its name, leaving the close
    note — the operator-visible half, and the whole point of the scenario —
    unpinned. Its own WO's verify caught the overclaim: a test whose name promises
    more than it asserts is worse than a missing test, because the coverage looks
    present. It now drives the real close_work_order.
    """
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = _seed_closeable_wo(db)

    _persist_unverified_ledger(
        wo_id,
        [{**_SCENARIO, "status": "UNVERIFIED"}],
        planning_root=planning,
        db_path=db,
        truncated="diff exceeded the budget; newest commits only",
        verified_at="2026-08-19T20:00:00+00:00",
    )
    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None
    assert "budget" in ledger["truncated"]
    # And the run stamp travels with it (see the pairing test below).
    assert ledger["verified_at"] == "2026-08-19T20:00:00+00:00"

    # The half the name promised: close must say the list may be incomplete.
    from core.work_orders.close import close_work_order

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = close_work_order(
            work_order_id=wo_id,
            force=True,  # gates are not under test; the advisory note is
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )
    assert result["ok"] is True, result
    note = result.get("unverified_risks_note") or ""
    assert note, "close must surface the WO's open UNVERIFIED residual risk"
    assert "PARTIAL" in note, (
        "a truncated enumeration must be declared partial at close — otherwise an "
        f"incomplete list reads as the complete one: {note!r}"
    )


def test_close_note_is_not_marked_partial_when_the_analysis_was_complete(tmp_path):
    """The converse, so PARTIAL means something: a full enumeration must not be
    hedged, or the caveat becomes noise operators learn to skip."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = _seed_closeable_wo(db)

    _persist_unverified_ledger(
        wo_id,
        [{**_SCENARIO, "status": "UNVERIFIED"}],
        planning_root=planning,
        db_path=db,
        verified_at="2026-08-19T20:00:00+00:00",
    )  # no truncated=

    from core.work_orders.close import close_work_order

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = close_work_order(
            work_order_id=wo_id,
            force=True,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )
    note = result.get("unverified_risks_note") or ""
    assert note, "the residual risk itself must still be surfaced"
    assert "PARTIAL" not in note, f"a complete analysis must not be hedged: {note!r}"


# ── 5. crash_mid_write: a mismatched ledger/verdict pair is detectable ──────────


def test_ledger_carries_the_run_stamp_so_a_mismatched_pair_is_detectable(tmp_path):
    """A crash between the ledger write and the verdict write can pair run N's
    ledger with run N-1's verdict. The window cannot be closed without a
    transaction across two stores, so the pair must at least be DETECTABLE —
    an undetectable mismatch is the silent-state class this milestone removes."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())

    # Run N-1 ledger.
    _persist_unverified_ledger(
        wo_id,
        [_SCENARIO],
        planning_root=planning,
        db_path=db,
        verified_at="2026-08-19T10:00:00+00:00",
    )
    first = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert first["verified_at"] == "2026-08-19T10:00:00+00:00"

    # Run N ledger written, then the verdict write "crashes" (never happens).
    _persist_unverified_ledger(
        wo_id,
        [],
        planning_root=planning,
        db_path=db,
        verified_at="2026-08-19T11:00:00+00:00",
    )
    second = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)

    # A reader holding the older verdict can SEE the ledger is from a later run.
    stale_verdict_verified_at = "2026-08-19T10:00:00+00:00"
    assert (
        second["verified_at"] != stale_verdict_verified_at
    ), "the ledger must carry its own run stamp so a mismatched pair is detectable"


def test_ledger_without_a_run_stamp_is_still_readable(tmp_path):
    """Ledgers written before the stamp existed must not become unreadable —
    absence of the field is not corruption."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())
    ledger_dir = planning / "work-orders" / wo_id
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "unverified-risks.json").write_text(
        json.dumps({"work_order_id": wo_id, "unverified": [], "count": 0}), encoding="utf-8"
    )
    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None
    assert ledger.get("verified_at") is None
    assert ledger.get("unreadable") is None
