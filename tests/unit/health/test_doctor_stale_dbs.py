"""WO 698e35fc: `_check_stale_dbs` flagged the product's own backups as stale.

The check scans ~/.dream-studio for ``*.db`` and skips ``state/`` and
``diagnostics/``. It did not skip ``backups/`` -- the directory
``core/installed_productization_backup.py`` writes productization snapshots
into (``paths.dream_studio_home / "backups"``). So a healthy install reported
``ds doctor`` status=fail forever, against a backup the product authored
itself, and the operator's only remedies were to delete a real backup or to
learn to ignore a red check. A health check that cries wolf on correct state
is worse than no check: it trains the reader to skip it.

There was no test on this function at all before this file -- `stale_dbs`
appeared nowhere under tests/ -- which is how the omission survived. So these
tests pin both arms deliberately: the exclusions that must stay silent, AND
the true positive that must still fire. Only asserting the exclusions would
pass just as well against a function that returns an empty list unconditionally.

Hermetic: every case builds its own home under tmp_path and never reads the
operator's real ~/.dream-studio.
"""

from __future__ import annotations

from pathlib import Path

from core.health.doctor import _check_stale_dbs


def _db(home: Path, rel: str) -> Path:
    """Create an empty .db file at *rel* under *home* and return it."""
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_backups_dir_is_not_flagged(tmp_path: Path) -> None:
    """A productization backup is expected state, not a ghost.

    This is the arm that fails before the fix.
    """
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    _db(home, "backups/backup-20260914T111854Z/studio.db")

    result = _check_stale_dbs(home)

    assert result["ok"] is True
    assert result["stale_dbs"] == []


def test_ghost_db_at_home_root_is_flagged(tmp_path: Path) -> None:
    """The true positive the check exists for: a stray db at the home root.

    Without this arm the exclusion tests would also pass against a function
    that never flags anything, so this is what makes the file a detector.
    """
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    ghost = _db(home, "authority.db")

    result = _check_stale_dbs(home)

    assert result["ok"] is False
    assert result["stale_dbs"] == [str(ghost)]


def test_state_and_diagnostics_stay_excluded(tmp_path: Path) -> None:
    """The two pre-existing exclusions are not regressed by adding a third."""
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    _db(home, "state/backups/studio-pre-156-20260917T151238.db")
    _db(home, "diagnostics/2026-06-28/dream-studio-clean/batch1/probe.db")

    result = _check_stale_dbs(home)

    assert result["ok"] is True
    assert result["stale_dbs"] == []


def test_ghost_is_still_found_alongside_excluded_dirs(tmp_path: Path) -> None:
    """A real ghost is not masked by the presence of legitimate databases.

    Guards the failure mode where a broadened skip list swallows everything.
    """
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    _db(home, "diagnostics/run/probe.db")
    _db(home, "backups/backup-20260914T111854Z/studio.db")
    ghost = _db(home, "studio.db")

    result = _check_stale_dbs(home)

    assert result["ok"] is False
    assert result["stale_dbs"] == [str(ghost)]


def test_missing_home_is_not_an_error(tmp_path: Path) -> None:
    """A home that does not exist yet reports clean rather than raising."""
    result = _check_stale_dbs(tmp_path / "does-not-exist")

    assert result["ok"] is True
    assert result["stale_dbs"] == []


def test_check_is_read_only_and_leaves_backups_intact(tmp_path: Path) -> None:
    """The check reports; it never touches the databases it inspects.

    The remedy this check recommends is deletion, so the check itself reading
    clean must not be achieved by removing anything. Pins the end-to-end claim
    that a real productization backup survives a doctor run untouched.
    """
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    backup = home / "backups" / "backup-20260914T111854Z" / "studio.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(b"SQLite format 3\x00payload")
    before = backup.read_bytes()

    result = _check_stale_dbs(home)

    assert result["ok"] is True
    assert backup.is_file()
    assert backup.read_bytes() == before


def test_crash_mid_write_partial_db_is_classified_by_location(tmp_path: Path) -> None:
    """A half-written .db is judged by where it landed, not by its contents.

    ``installed_productization_backup.backup_runtime`` copies with shutil.copy2;
    a crash partway through leaves a truncated .db behind. Inside backups/ that
    is a damaged backup and not the stale-ghost condition this check reports.
    The same truncated file at the home root still is, because a database at the
    root is the misconfigured-resolver symptom regardless of how complete it is.
    """
    home = tmp_path / ".dream-studio"
    _db(home, "state/studio.db")
    partial_backup = home / "backups" / "backup-20260920T000000Z" / "studio.db"
    partial_backup.parent.mkdir(parents=True, exist_ok=True)
    partial_backup.write_bytes(b"SQLite format 3\x00trunc")

    assert _check_stale_dbs(home)["ok"] is True

    partial_root = home / "studio.db"
    partial_root.write_bytes(b"SQLite format 3\x00trunc")

    result = _check_stale_dbs(home)

    assert result["ok"] is False
    assert result["stale_dbs"] == [str(partial_root)]
