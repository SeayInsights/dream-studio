"""`ds pulse` measures storage, instead of being silent about it.

THE DEFECT. The pulse ran nine checks — branches, milestones, pull requests, CI, drafts,
corrections, escalations, agents, skill health — and **not one looked at storage**. So
when the runtime reached 10.6 GB on disk with a 444 MB write-ahead log, the pulse
reported healthy for months.

`--refresh` would not have helped, and that is the part worth being precise about. A
snapshot can only be stale about something it records; this one was silent about
something it never recorded at all, which from the outside is indistinguishable from
"fine".
"""

from __future__ import annotations

import json

import pytest

from interfaces.cli import pulse_collector
from interfaces.cli.pulse_collector import STORAGE_LIMITS, check_storage


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    (tmp_path / "state").mkdir()
    (tmp_path / "events" / "spool").mkdir(parents=True)
    monkeypatch.setattr(pulse_collector.paths, "user_data_dir", lambda: tmp_path)
    return tmp_path


def _spool(home, count: int) -> None:
    for i in range(count):
        (home / "events" / "spool" / f"{i}.json").write_text(json.dumps({"i": i}), encoding="utf-8")


def test_a_quiet_runtime_reports_nothing(fake_home):
    """A check that always fires is a check people stop reading."""
    assert check_storage() == []


def test_a_large_write_ahead_log_is_reported(fake_home):
    """The measured incident: 444 MB of WAL, unnoticed for months. A log that large means
    a checkpoint is not happening, which is a different fault from a big database."""
    wal = fake_home / "state" / "studio.db-wal"
    wal.write_bytes(b"\0" * (STORAGE_LIMITS["wal_bytes"] + 1))
    issues = check_storage()
    assert any("write-ahead log" in i for i in issues), issues
    assert any("checkpoint" in i for i in issues), "the reason is not named"


def test_a_spool_backlog_is_reported(fake_home):
    """The leading indicator. Events accumulate first, the database and its log grow
    second, the disk fills third — so a spool that is not draining says something is
    wrong earliest."""
    _spool(fake_home, STORAGE_LIMITS["spool_files"] + 1)
    issues = check_storage()
    assert any("unprocessed in the spool" in i for i in issues), issues


def test_a_spool_under_the_limit_is_not_reported(fake_home):
    _spool(fake_home, 5)
    assert check_storage() == []


def test_total_size_is_reported(fake_home):
    big = fake_home / "state" / "blob.bin"
    big.write_bytes(b"\0" * (STORAGE_LIMITS["total_bytes"] + 1))
    issues = check_storage()
    assert any("on disk" in i for i in issues), issues


def test_an_unreadable_home_is_not_the_pulse_s_finding(monkeypatch, tmp_path):
    """The doctor owns a broken runtime. A pulse that raised here would take the whole
    report down over a permissions problem it cannot fix."""
    monkeypatch.setattr(pulse_collector.paths, "user_data_dir", lambda: tmp_path / "gone")
    assert check_storage() == []


def test_the_limits_come_from_the_incident_not_from_taste():
    """1 GB and 100 MB sit under the measured 10.6 GB and 444 MB, so the condition that
    motivated the check would have fired well before it got that far."""
    assert STORAGE_LIMITS["total_bytes"] < 10_600_000_000
    assert STORAGE_LIMITS["wal_bytes"] < 444_000_000


def test_storage_reaches_the_report_and_the_verdict():
    """THE WIRING. A check that measures and is read by nothing is the same silence in a
    new place — and this whole item exists because a number nobody looked at was
    indistinguishable from a healthy one."""
    import inspect

    source = inspect.getsource(pulse_collector.generate_pulse)
    assert "storage_issues = check_storage()" in source, "the check is never called"
    assert "+ len(storage_issues)" in source, "storage does not count toward the verdict"
    assert "### Storage" in source, "storage has no section in the report"
    assert '"storage_issues": len(storage_issues)' in source, "the stats omit it"
