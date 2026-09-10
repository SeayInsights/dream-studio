"""The ceiling on tasks nobody can check, and the honest failures around it.

Measured on the live authority when this landed: 1767 tasks with no acceptance criterion
and no declared reason, out of 3298. Admission stops the number growing at the doors; this
gate is what proves it, and WO 09a00064 burns the backlog down.

EVERY TEST HERE DRIVES A THROWAWAY AUTHORITY. `measure` takes a `db_path` precisely so it
can be pointed at one -- a test that read the operator's live database would be measuring
whatever they did this morning, which is the defect WO 8bd297f1 fixed on a different path.
"""

from __future__ import annotations

import json
import sqlite3

from core.gates import task_criteria_baseline as tcb
from core.work_orders.admission import DECLARED_PREFIX

SCHEMA = """
CREATE TABLE business_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    acceptance_criteria TEXT
);
"""


def _authority(tmp_path, rows):
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO business_tasks (task_id, title, description, acceptance_criteria)"
        " VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def test_the_ceiling_refuses_a_new_criterion_less_task(tmp_path, monkeypatch):
    """THE RATCHET. One more uncheckable task than the baseline fails, and the message names
    the number and the remedy -- a gate that reports only "failed" gets bypassed."""
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"uncheckable": 1}), encoding="utf-8")
    monkeypatch.setattr(tcb, "BASELINE_PATH", baseline)

    at_ceiling = _authority(tmp_path, [("t1", "one", "", None)])
    assert tcb.run(at_ceiling)["ok"] is True

    over = (
        _authority(tmp_path / "over", [("t1", "one", "", None), ("t2", "two", "", "   ")])
        if (tmp_path / "over").mkdir() or True
        else None
    )
    report = tcb.run(over)
    assert report["ok"] is False
    assert report["uncheckable"] == 2, report
    assert "against a ceiling of 1" in str(report["reason"])
    assert "TEST-CHECK" in str(report["reason"]), "the failure must name the remedy"


def test_a_declared_reason_is_not_a_stub(tmp_path, monkeypatch):
    """The escape hatch, and the reason it has to be PERSISTED to work.

    This gate reads the marker `admission.DECLARED_PREFIX` out of the description, and the
    CLI writes it there. They agreed on a hardcoded phrase for about ten minutes -- the
    Warden's lane -- so the marker has one definition and both sites import it. Using the
    imported constant here means a test cannot pass against a marker the writer stopped
    writing.
    """
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"uncheckable": 0}), encoding="utf-8")
    monkeypatch.setattr(tcb, "BASELINE_PATH", baseline)

    db = _authority(
        tmp_path,
        [("t1", "attested", f"{DECLARED_PREFIX} only a person can confirm this", None)],
    )
    report = tcb.run(db)

    assert report["without_criterion"] == 1
    assert report["of_those_declared"] == 1
    assert report["uncheckable"] == 0, "a recorded declaration is not a stub"
    assert report["ok"] is True


def test_an_unreadable_authority_fails_rather_than_reporting_zero(tmp_path, monkeypatch):
    """A COUNT THAT COULD NOT BE TAKEN IS NOT A COUNT OF ZERO.

    The fail-open shape this repo keeps producing: a checker that cannot see its subject
    reports clean, and "nobody looked" becomes indistinguishable from "nothing found". So a
    missing database blocks, and says which.
    """
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"uncheckable": 5}), encoding="utf-8")
    monkeypatch.setattr(tcb, "BASELINE_PATH", baseline)

    report = tcb.run(tmp_path / "does-not-exist.db")
    assert report["status"] == "unknown"
    assert report["ok"] is False
    assert "not a count of" in str(report["reason"])

    # An empty-but-real authority is a genuine zero, and must NOT be conflated with it.
    empty = _authority(tmp_path / "empty", []) if (tmp_path / "empty").mkdir() or True else None
    good = tcb.run(empty)
    assert good["status"] == "computed"
    assert good["uncheckable"] == 0
    assert good["ok"] is True


def test_no_recorded_baseline_fails_rather_than_passing(tmp_path, monkeypatch):
    """A ratchet with no ceiling has nothing to hold. Passing in that state would make the
    gate silently inert for exactly as long as nobody noticed."""
    monkeypatch.setattr(tcb, "BASELINE_PATH", tmp_path / "absent.json")
    report = tcb.run(_authority(tmp_path, [("t1", "one", "", None)]))
    assert report["ok"] is False
    assert "no baseline recorded" in str(report["reason"])
    assert "--update" in str(report["reason"]), "it must name how to record one"


def test_the_report_states_its_count_even_when_clean(tmp_path, monkeypatch):
    """A clean run that prints nothing is indistinguishable from a run that measured
    nothing. Asserted on the RENDERED text, because that is what a person reads."""
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"uncheckable": 3}), encoding="utf-8")
    monkeypatch.setattr(tcb, "BASELINE_PATH", baseline)

    rendered = tcb._render(tcb.run(_authority(tmp_path, [("t1", "one", "", None)])))
    assert "1 uncheckable of 1 task" in rendered, rendered
    assert "ceiling 3" in rendered
    assert "OK" in rendered


def test_the_shipped_baseline_is_recorded_and_holds():
    """The real repository, against its real ceiling.

    A POSITIVE CONTROL RIDES ALONG, because "the shipped baseline passes its own gate" is a
    tautology otherwise -- it would stay green under a `measure` mutated to return nothing,
    which is exactly how two lanes' tests passed under a neutered checker in WO 5db3755e.
    """
    report = tcb.run()
    if report["status"] != "computed":
        import pytest

        pytest.skip(f"no authority on this machine: {report.get('reason')}")

    assert report["ceiling"] is not None, "the shipped baseline must be recorded"
    assert report["ok"] is True, report.get("reason")

    # The control: the measurement is non-trivial, so a checker returning nothing fails here.
    assert report["total_tasks"] > 0, "a zero-task authority would make the pass meaningless"
