"""The operator-local store may not grow without a retention decision.

Dream Studio reached 10.6 GB on the operator's machine -- 768,572 spool files
and four full copies of a 1.1 GB database -- because every writer worked and no
component owned deletion. These tests exist so that cannot recur silently: a
directory that appears under the store root with no budget and no exemption
fails the suite.
"""

from __future__ import annotations

import os
import time

import pytest

from core.config import paths, retention


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A store root under tmp, so nothing here can touch the real one."""
    root = tmp_path / ".dream-studio"
    root.mkdir()
    monkeypatch.setattr(paths, "user_data_dir", lambda: root)
    return root


def _age(path, days: float) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


# --- the guard -------------------------------------------------------------


def test_new_store_directory_without_a_budget_is_reported(store):
    """This is the whole point: a new store cannot appear unnoticed."""
    (store / "brand-new-cache").mkdir()
    assert "brand-new-cache" in retention.unbudgeted_dirs()


def test_guard_descends_into_delegating_parents(store):
    """events/ is exempt only as a parent; its children each need a decision.

    The first draft exempted events/ outright and so never saw
    events/failed/reasons, which by then held 285,828 files.
    """
    (store / "events" / "unknown-stage").mkdir(parents=True)
    assert "events/unknown-stage" in retention.unbudgeted_dirs()


def test_every_budget_and_exemption_is_a_distinct_decision():
    """A directory must not be both swept whole and exempt -- that hides intent.

    A GLOB-scoped budget inside an exempt directory is different: it is a
    deliberate carve-out (state/ is exempt, but orphaned hookq.*.jsonl in it are
    not), so only unscoped budgets are required to be disjoint from EXEMPT.
    """
    swept_whole = {b.relpath for b in retention.BUDGETS if b.glob == "*"}
    assert not (swept_whole & retention.EXEMPT), "a directory is both swept whole and exempt"


def test_a_carve_out_inside_an_exempt_directory_is_scoped():
    """A budget targeting an exempt directory must narrow itself with a glob."""
    for b in retention.BUDGETS:
        if b.relpath in retention.EXEMPT:
            assert (
                b.glob != "*"
            ), f"{b.name} sweeps all of {b.relpath}, which is exempt; scope it with a glob"


def test_live_spool_stages_are_exempt_not_budgeted():
    """Deleting a pending or in-flight event loses data. Pin that choice."""
    budgeted = {b.relpath for b in retention.BUDGETS}
    for live in ("events/spool", "events/processing"):
        assert live in retention.EXEMPT
        assert live not in budgeted


# --- the executor ----------------------------------------------------------


def test_max_age_removes_only_what_is_older(store):
    d = store / "events" / "processed"
    d.mkdir(parents=True)
    old, new = d / "old.json", d / "new.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    _age(old, 30)

    budget = retention.Budget(name="t", relpath="events/processed", max_age_days=7)
    result = retention.sweep_one(budget)

    assert result.removed == 1
    assert not old.exists()
    assert new.exists(), "a file inside the window must survive"


def test_keep_newest_retains_exactly_n(store):
    d = store / "state" / "backups"
    d.mkdir(parents=True)
    for i in range(5):
        f = d / f"studio-pre-{i}.db"
        f.write_text("x", encoding="utf-8")
        _age(f, 5 - i)

    budget = retention.Budget(
        name="t", relpath="state/backups", glob="studio-pre-*.db", keep_newest=2
    )
    result = retention.sweep_one(budget)

    assert result.removed == 3
    survivors = sorted(p.name for p in d.glob("studio-pre-*.db"))
    assert survivors == ["studio-pre-3.db", "studio-pre-4.db"], "the NEWEST two survive"


def test_glob_confines_the_budget(store):
    """A budget scoped by glob must not touch its neighbours."""
    d = store / "state" / "backups"
    d.mkdir(parents=True)
    (d / "studio-pre-1.db").write_text("x", encoding="utf-8")
    keeper = d / "something-else.db"
    keeper.write_text("x", encoding="utf-8")
    _age(d / "studio-pre-1.db", 99)
    _age(keeper, 99)

    budget = retention.Budget(
        name="t", relpath="state/backups", glob="studio-pre-*.db", keep_newest=0
    )
    retention.sweep_one(budget)

    assert keeper.exists(), "a non-matching file must be untouched"


def test_dry_run_deletes_nothing_but_reports_the_same(store):
    d = store / "events" / "processed"
    d.mkdir(parents=True)
    f = d / "old.json"
    f.write_text("{}", encoding="utf-8")
    _age(f, 30)

    budget = retention.Budget(name="t", relpath="events/processed", max_age_days=7)
    dry = retention.sweep_one(budget, dry_run=True)
    assert dry.removed == 1
    assert f.exists(), "dry run must not delete"

    wet = retention.sweep_one(budget)
    assert wet.removed == dry.removed, "dry run must predict the real sweep"
    assert not f.exists()


def test_directory_entries_are_swept_whole(store):
    """diagnostics/ is one directory per day, so entries are dirs, not files."""
    d = store / "diagnostics" / "2020-01-01"
    d.mkdir(parents=True)
    (d / "capture.txt").write_text("evidence", encoding="utf-8")
    _age(d, 99)

    budget = retention.Budget(name="t", relpath="diagnostics", max_age_days=14, entry_is_dir=True)
    result = retention.sweep_one(budget)

    assert result.removed == 1
    assert not d.exists()


def test_sweep_is_idempotent(store):
    d = store / "events" / "processed"
    d.mkdir(parents=True)
    f = d / "old.json"
    f.write_text("{}", encoding="utf-8")
    _age(f, 30)

    budget = retention.Budget(name="t", relpath="events/processed", max_age_days=7)
    assert retention.sweep_one(budget).removed == 1
    assert retention.sweep_one(budget).removed == 0, "a second sweep must be a no-op"


def test_missing_store_is_not_an_error(store):
    """Retention runs on a fresh install where none of these exist yet."""
    budget = retention.Budget(name="t", relpath="nope/not/here", max_age_days=1)
    result = retention.sweep_one(budget)
    assert result.removed == 0 and result.error is None


def test_sweep_covers_every_declared_budget(store):
    assert len(retention.sweep(dry_run=True)) == len(retention.BUDGETS)


def test_size_cap_drops_oldest_until_under_budget(store):
    """Age alone is not a budget: one recent day reached 1.86 GB and survived it."""
    d = store / "diagnostics"
    d.mkdir(parents=True)
    for i in range(4):
        day = d / f"day-{i}"
        day.mkdir()
        (day / "capture.bin").write_bytes(b"x" * 1000)
        _age(day, 4 - i)  # day-3 is newest

    budget = retention.Budget(name="t", relpath="diagnostics", max_bytes=2500, entry_is_dir=True)
    result = retention.sweep_one(budget)

    assert result.removed == 2, "must drop until under cap, not everything"
    survivors = sorted(p.name for p in d.iterdir())
    assert survivors == ["day-2", "day-3"], "the NEWEST entries survive a size cap"


def test_size_cap_leaves_a_store_under_budget_alone(store):
    d = store / "diagnostics"
    d.mkdir(parents=True)
    day = d / "small"
    day.mkdir()
    (day / "f.bin").write_bytes(b"x" * 10)

    budget = retention.Budget(
        name="t", relpath="diagnostics", max_bytes=1_000_000, entry_is_dir=True
    )
    assert retention.sweep_one(budget).removed == 0
    assert day.exists()


def test_stale_worktrees_are_reported_not_deleted(tmp_path, monkeypatch):
    """Agent worktrees accumulate outside the store, so a budget cannot see them.

    Eleven were found holding 572 MB, all from an ended session. They are
    REPORTED rather than swept: one of the eleven held uncommitted work, and
    deleting someone's checkout is the operator's call.
    """
    import subprocess

    wt = tmp_path / "wt-dead"
    wt.mkdir()
    (wt / "big.bin").write_bytes(b"x" * 2048)
    old = time.time() - 30 * 86400
    os.utime(wt, (old, old))

    def fake_run(cmd, **kwargs):
        class _R:
            stdout = ""

        if "worktree" in cmd:
            _R.stdout = f"worktree {tmp_path}\nworktree {wt}\n"
        elif "--contains" in cmd:
            _R.stdout = "* main\n"  # merged, so genuinely debris
        elif "rev-parse" in cmd:
            _R.stdout = "abc123\n"
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    found = retention.stale_worktrees(repo_root=tmp_path)

    assert [p for p, _ in found] == [str(wt)]
    assert wt.exists(), "audit must never delete a worktree"


def test_a_fresh_worktree_is_not_reported(tmp_path, monkeypatch):
    import subprocess

    wt = tmp_path / "wt-live"
    wt.mkdir()

    class _Out:
        stdout = f"worktree {tmp_path}\nworktree {wt}\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Out())
    assert retention.stale_worktrees(repo_root=tmp_path) == []


def test_an_unmerged_worktree_is_never_called_stale(tmp_path, monkeypatch):
    """The near-miss: age + a clean tree flagged two worktrees holding real work.

    ds-lanes (feat/lane-determinism, three hours old) and ds-push-wt both had
    commits that were not on main. Judging on age and cleanliness alone would
    have recommended deleting them.
    """
    import subprocess

    wt = tmp_path / "wt-unmerged"
    wt.mkdir()
    old = time.time() - 30 * 86400
    os.utime(wt, (old, old))

    def fake_run(cmd, **kwargs):
        class _R:
            stdout = ""

        if "worktree" in cmd:
            _R.stdout = f"worktree {tmp_path}\nworktree {wt}\n"
        elif "status" in cmd:
            _R.stdout = ""  # clean
        elif "rev-parse" in cmd:
            _R.stdout = "deadbeef\n"
        elif "--contains" in cmd:
            _R.stdout = "  feat/lane-determinism\n"  # NOT on main
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert retention.stale_worktrees(repo_root=tmp_path) == []


def test_a_merged_worktree_is_still_reported(tmp_path, monkeypatch):
    """The guard must not become useless -- merged debris is still debris."""
    import subprocess

    wt = tmp_path / "wt-merged"
    wt.mkdir()
    (wt / "f.bin").write_bytes(b"x" * 64)
    old = time.time() - 30 * 86400
    os.utime(wt, (old, old))

    def fake_run(cmd, **kwargs):
        class _R:
            stdout = ""

        if "worktree" in cmd:
            _R.stdout = f"worktree {tmp_path}\nworktree {wt}\n"
        elif "status" in cmd:
            _R.stdout = ""
        elif "rev-parse" in cmd:
            _R.stdout = "cafebabe\n"
        elif "--contains" in cmd:
            _R.stdout = "* main\n  remotes/origin/main\n"
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert [p for p, _ in retention.stale_worktrees(repo_root=tmp_path)] == [str(wt)]
