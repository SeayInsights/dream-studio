"""The stop hook must never prescribe a command the operator cannot run.

WO 2ff38c7e. Operator report: the hook "bothers the shit out of me". It was not noise.

Measured at the moment of the complaint, on WO 789df02b: ten tasks, all complete, zero
incomplete, work order still ``in_progress`` because its close gates refused (a review
verdict gone stale when new commits landed, and a security-scan envelope pinning an older
HEAD). The hook's message offered exactly two remedies -- ``task-done <task_id>`` and
``close`` -- and BOTH were impossible in that state. What remained was inventing a task in
order to mark it done, which is the false-done the hook exists to prevent, or
``DS_ENFORCE=0``. ``runtime/lib/enforcement.py`` names those two outcomes itself as the
bad ones.

A gate whose prescribed remedy cannot be performed drives the operator to exactly what it
was built to stop. Same shape as the security_scan gate prescribing ``security:scan``
(WO cf01cd7d), and worse here, because the impossible remedy pressures a false record.

These load the hook and the enforcement library by path rather than importing them,
because both are copied verbatim into installed hook trees and are not importable as
package modules from the test tree.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-stop-enforce.py"
ENFORCEMENT_PATH = REPO_ROOT / "runtime" / "lib" / "enforcement.py"

FUTURE = "2099-01-01T00:00:00+00:00"  # a window in which nothing can have been written


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def enforcement(tmp_path, monkeypatch):
    """The enforcement library pointed at a throwaway authority.

    Never the operator's real ~/.dream-studio: these tests write task rows, and a test
    that mutates live authority state is a worse defect than the one under test.
    """
    module = _load("enf_under_test", ENFORCEMENT_PATH)
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE business_tasks (task_id TEXT, work_order_id TEXT, status TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE business_work_orders (work_order_id TEXT, status TEXT, closed_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE business_work_order_artifacts (work_order_id TEXT, kind TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE business_canonical_events (work_order_id TEXT, event_type TEXT,"
        " event_timestamp TEXT, received_at TEXT)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(module, "AUTHORITY_DB", db)
    return module


def _add_task(enforcement_module, wo: str, status: str, created: str, updated: str) -> None:
    conn = sqlite3.connect(enforcement_module.AUTHORITY_DB)
    conn.execute(
        "INSERT INTO business_tasks VALUES (?, ?, ?, ?, ?)",
        (f"t-{status}-{created}", wo, status, created, updated),
    )
    conn.commit()
    conn.close()


def test_remedy_is_achievable_when_no_task_remains(enforcement) -> None:
    """With every task complete, the counter must say 0 so the caller can adapt."""
    _add_task(
        enforcement, "wo-1", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )
    _add_task(
        enforcement, "wo-1", "complete", "2020-01-02T00:00:00+00:00", "2020-01-02T00:00:00+00:00"
    )

    assert enforcement.incomplete_task_count("wo-1") == 0


def test_a_work_order_with_tasks_left_still_reports_them(enforcement) -> None:
    """The counterpart. Without it, a counter hard-coded to 0 would pass the case above."""
    _add_task(
        enforcement, "wo-2", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )
    _add_task(
        enforcement, "wo-2", "pending", "2020-01-02T00:00:00+00:00", "2020-01-02T00:00:00+00:00"
    )

    assert enforcement.incomplete_task_count("wo-2") == 1


def test_an_unknown_work_order_is_not_reported_as_finished(enforcement) -> None:
    """None, not 0.

    ``SELECT COUNT(*)`` answers 0 for an unknown work order exactly as readily as for one
    whose tasks are all complete. Returning 0 would let the caller announce "every task is
    already complete" about a work order that has none -- the compared-nothing-reported-
    clean shape this codebase keeps finding.
    """
    assert enforcement.incomplete_task_count("no-such-work-order") is None


def test_registering_a_task_counts_as_an_authority_write(enforcement) -> None:
    """Recording newly discovered work is a write, and the rules require making it.

    The no-deferred-findings rule requires registering a defect the moment it is found, so
    a session whose honest output is "I found and registered three defects" must not read
    as having recorded nothing. It did: the session that produced this fix registered six
    work orders and eight tasks and still tripped the hook.
    """
    window = "2026-01-01T00:00:00+00:00"
    # Created inside the window, still pending -- nothing has been COMPLETED.
    _add_task(
        enforcement, "wo-3", "pending", "2026-06-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00"
    )

    assert enforcement.authority_write_since("wo-3", window) is True


def test_a_task_created_before_the_window_does_not_count(enforcement) -> None:
    """The counterpart, or the check above would pass for any work order with a task."""
    window = "2026-01-01T00:00:00+00:00"
    _add_task(
        enforcement, "wo-4", "pending", "2020-06-01T00:00:00+00:00", "2020-06-01T00:00:00+00:00"
    )

    assert enforcement.authority_write_since("wo-4", window) is False


def test_the_emitted_violation_never_prescribes_an_impossible_command(enforcement) -> None:
    """End to end through the real hook: the message the operator actually reads.

    A unit test on the counter alone would pass while the message stayed impossible, and
    the message IS what the operator hit. Driven with a future window so no write can
    count, which is precisely the state that produced the complaint.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    _add_task(
        enforcement, "wo-5", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )

    session = {"started_at": FUTURE, "source_edits": [{"work_order_id": "wo-5"}]}
    violations = hook._authority_violations(enforcement, session)

    assert len(violations) == 1, f"expected exactly one violation, got {violations}"
    message = violations[0]
    assert "task-done" not in message, (
        "the hook told the operator to mark a task done when none remains; that is the "
        f"trap this work order exists to close: {message}"
    )
    assert "add-task" in message, f"the achievable remedy must be named: {message}"
    assert message.isascii(), (
        "the message goes to stderr, where a non-ASCII character mangles under cp1252 on "
        f"Windows: {message!r}"
    )


def test_the_ordinary_message_still_prescribes_task_done(enforcement) -> None:
    """When a task IS markable, the original guidance must survive.

    Without this, deleting the branch entirely would pass every assertion above while
    removing the guidance that is correct in the common case.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    _add_task(
        enforcement, "wo-6", "pending", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )

    session = {"started_at": FUTURE, "source_edits": [{"work_order_id": "wo-6"}]}
    message = hook._authority_violations(enforcement, session)[0]

    assert "task-done" in message, f"a markable task must still be offered: {message}"


def test_the_multi_claimant_message_is_also_achievable(enforcement) -> None:
    """The same rule on the ambiguous-claimant path.

    The first cut of this fix patched only the single-claimant branch. Two work orders
    that both declare a boundary over the edited file and both have every task complete
    -- the exact state this hook was corrected for -- still met the old impossible
    message. ``in_progress_work_order``'s own docstring calls concurrent work orders
    normal (three were in progress on the live authority when it was written), so this
    path is reachable, not a corner. Found by an independent verifier, after the author
    had already marked the work complete on his own passing run.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    _add_task(
        enforcement, "wo-a", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )
    _add_task(
        enforcement, "wo-b", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )

    session = {
        "started_at": FUTURE,
        "source_edits": [{"work_order_id": "wo-a", "claimants": ["wo-a", "wo-b"]}],
    }
    message = hook._authority_violations(enforcement, session)[0]

    assert "task-done" not in message, (
        "the ambiguous-claimant path told the operator to mark a task done when no "
        f"claimant has one: {message}"
    )
    assert "add-task" in message, f"the achievable remedy must be named: {message}"
    assert message.isascii(), f"stderr message must survive cp1252: {message!r}"


def test_the_multi_claimant_message_names_a_claimant_that_has_work(enforcement) -> None:
    """When only ONE claimant has a markable task, name that one.

    Naming ``claimants[0]`` unconditionally would send the operator to a work order with
    nothing to mark while its sibling had the real task, which is the impossible remedy
    again wearing a different hat.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    _add_task(
        enforcement, "wo-c", "complete", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )
    _add_task(
        enforcement, "wo-d", "pending", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"
    )

    session = {
        "started_at": FUTURE,
        "source_edits": [{"work_order_id": "wo-c", "claimants": ["wo-c", "wo-d"]}],
    }
    message = hook._authority_violations(enforcement, session)[0]

    assert "task-done wo-d" in message, (
        "the remedy must name the claimant that actually has a markable task, not the "
        f"first one in the list: {message}"
    )


def test_an_unreadable_authority_keeps_the_ordinary_guidance(enforcement, monkeypatch) -> None:
    """None must not be read as "everything is complete".

    An unreadable authority and a work order with no tasks both answer None. Treating
    either as zero-remaining would have the hook confidently announce that all work is
    recorded on the strength of a query that answered nothing -- the shape this codebase
    keeps finding. The fallback is the ordinary task-done guidance.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    monkeypatch.setattr(enforcement, "incomplete_task_count", lambda *_a, **_k: None)

    session = {"started_at": FUTURE, "source_edits": [{"work_order_id": "wo-unknown"}]}
    message = hook._authority_violations(enforcement, session)[0]

    assert "task-done" in message, (
        "an unreadable count must fall back to the familiar guidance, never to a claim "
        f"that nothing remains: {message}"
    )
    assert (
        "already complete" not in message
    ), f"the hook claimed completion on the strength of an unreadable query: {message}"


class _NoDocstoreRecord:
    """An enforcement stand-in for which no artifact is ever registered."""

    @staticmethod
    def docstore_record_since(_name_hint: str, _since: str) -> bool:
        return False


def test_the_docstore_remedy_is_not_prescribed_for_a_missing_file(tmp_path) -> None:
    """`ds files add` cannot register a file that is gone, so do not prescribe it.

    Third instance of this work order's own rule, found by independent review in the
    sibling function. ``cmd_files_add`` hard-requires ``path.is_file()`` and otherwise
    returns ``{"ok": false, "error": "not a file: ..."}``. A Bash ``rm``/``mv`` never
    reaches the PreToolUse Write|Edit hook, so a session can genuinely record an edit to
    a document that no longer exists when the stop runs.

    Before this, ``_docstore_violations`` had no tests of any kind while its sibling had
    ten.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    missing = tmp_path / "docs" / "gone.md"  # deliberately never created

    session = {
        "started_at": FUTURE,
        "doc_edits": [{"path": str(missing), "project_id": "p-1", "ts": FUTURE}],
    }
    message = hook._docstore_violations(_NoDocstoreRecord, session)[0]

    assert f'files add "{missing}"' not in message, (
        "the hook prescribed registering a file that is not on disk; that command "
        f"returns 'not a file' and cannot succeed: {message}"
    )
    assert "no longer on disk" in message, f"the real position must be stated: {message}"
    assert "clears once" not in message, (
        "the message promised the violation would clear; nothing in the repo removes an "
        f"entry from doc_edits, so that reassurance is false: {message}"
    )
    assert (
        "recorded bypass" in message
    ), f"what actually happens -- block, then a recorded bypass -- must be said: {message}"
    assert message.isascii(), f"stderr message must survive cp1252: {message!r}"


def test_the_docstore_remedy_is_prescribed_when_the_file_exists(tmp_path) -> None:
    """The counterpart, or deleting the branch entirely would pass the case above.

    An unregistered document that IS on disk must still draw the ordinary, runnable
    registration command.
    """
    hook = _load("stop_hook_under_test", HOOK_PATH)
    present = tmp_path / "docs" / "real.md"
    present.parent.mkdir(parents=True)
    present.write_text("# real\n", encoding="utf-8")

    session = {
        "started_at": FUTURE,
        "doc_edits": [{"path": str(present), "project_id": "p-1", "ts": FUTURE}],
    }
    message = hook._docstore_violations(_NoDocstoreRecord, session)[0]

    assert (
        f'files add "{present}"' in message
    ), f"an existing unregistered document must still be registerable: {message}"
    assert "no longer on disk" not in message, f"the file is present: {message}"


def test_a_registered_document_raises_no_violation(tmp_path) -> None:
    """Guards against a check that reports every document.

    Without this, a function that always appended a violation would satisfy both cases
    above -- the discriminates-nothing shape this suite exists to refuse.
    """

    class _AlreadyRecorded:
        @staticmethod
        def docstore_record_since(_name_hint: str, _since: str) -> bool:
            return True

    hook = _load("stop_hook_under_test", HOOK_PATH)
    present = tmp_path / "docs" / "real.md"
    present.parent.mkdir(parents=True)
    present.write_text("# real\n", encoding="utf-8")

    session = {
        "started_at": FUTURE,
        "doc_edits": [{"path": str(present), "project_id": "p-1", "ts": FUTURE}],
    }
    assert hook._docstore_violations(_AlreadyRecorded, session) == []


def _schema_for_next_wo(db) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS business_milestones (milestone_id TEXT, order_index INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS work_order_dependencies "
        "(work_order_id TEXT, depends_on_id TEXT, created_at TEXT)"
    )
    conn.execute("DROP TABLE IF EXISTS business_work_orders")
    conn.execute(
        "CREATE TABLE business_work_orders (work_order_id TEXT, project_id TEXT, title TEXT,"
        " status TEXT, milestone_id TEXT, sequence_order INTEGER, created_at TEXT)"
    )
    conn.commit()
    conn.close()


def _add_wo(db, wo: str, status: str, seq: int) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO business_work_orders VALUES (?, 'p-1', ?, ?, 'm-1', ?, '2020-01-01')",
        (wo, f"title {wo}", status, seq),
    )
    conn.commit()
    conn.close()


def _add_dep(db, wo: str, depends_on: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO work_order_dependencies VALUES (?, ?, '2020-01-01')", (wo, depends_on)
    )
    conn.commit()
    conn.close()


def test_next_work_order_skips_one_blocked_by_an_open_dependency(enforcement) -> None:
    """The DENY must not name a work order `start` would refuse.

    Fourth instance of the achievable-remedy shape, found by independent review in the
    edit hook. This selector checked ``status='created'`` alone, so the DENY could name a
    work order sitting behind an unclosed dependency -- and ``start_work_order`` refuses
    exactly that with "N declared dependenc(y/ies) are not closed yet". The operator was
    denied an edit and handed a command that would also refuse, leaving no forward path.

    The two candidates differ ONLY in whether their dependency is closed, so nothing but
    the dependency check can separate them.
    """
    db = enforcement.AUTHORITY_DB
    _schema_for_next_wo(db)
    _add_wo(db, "wo-blocked", "created", 10)  # earlier in sequence, but blocked
    _add_wo(db, "wo-ready", "created", 20)
    _add_wo(db, "wo-open-dep", "in_progress", 0)
    _add_dep(db, "wo-blocked", "wo-open-dep")

    nxt = enforcement.next_created_work_order("p-1")

    assert nxt is not None, "a startable work order exists and must be offered"
    assert nxt["work_order_id"] == "wo-ready", (
        "the selector offered a work order blocked behind an unclosed dependency; "
        f"`work-order start` would refuse it: {nxt}"
    )


def test_next_work_order_offers_one_whose_dependency_is_closed(enforcement) -> None:
    """The counterpart. Without it, a selector that excluded every dependent work order
    would pass the case above while hiding startable work."""
    db = enforcement.AUTHORITY_DB
    _schema_for_next_wo(db)
    _add_wo(db, "wo-dependent", "created", 10)
    _add_wo(db, "wo-done", "closed", 0)
    _add_dep(db, "wo-dependent", "wo-done")

    nxt = enforcement.next_created_work_order("p-1")

    assert (
        nxt is not None and nxt["work_order_id"] == "wo-dependent"
    ), f"a dependency that is closed must not block the suggestion: {nxt}"


def test_next_work_order_returns_none_when_everything_is_blocked(enforcement) -> None:
    """Naming nothing is correct when nothing is startable.

    The caller omits the `Run:` line entirely rather than suggesting a refusal.
    """
    db = enforcement.AUTHORITY_DB
    _schema_for_next_wo(db)
    _add_wo(db, "wo-blocked", "created", 10)
    _add_wo(db, "wo-open-dep", "in_progress", 0)
    _add_dep(db, "wo-blocked", "wo-open-dep")

    assert enforcement.next_created_work_order("p-1") is None
