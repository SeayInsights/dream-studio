"""Integration tests for cloud backup (T025): local backup/restore, export, cloud config, auto-push."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.studio_backup import (  # noqa: E402
    backup, restore, export, main,
    _load_backup_config, _save_backup_config, _backup_config_path,
    cloud_auto,
)
from hooks.lib.studio_db import _connect  # noqa: E402
from hooks.lib.state import backup_db, _maybe_cloud_push  # noqa: E402


def _seed_db(path: Path) -> Path:
    """Create a minimal studio.db with data for round-trip testing."""
    conn = _connect(path)
    conn.execute(
        "INSERT OR IGNORE INTO reg_skills (skill_id, pack, mode, skill_path, updated_at) "
        "VALUES ('core:build', 'core', 'build', 'skills/core/modes/build/SKILL.md', '2026-05-01')"
    )
    conn.commit()
    conn.close()
    return path


# ── Local backup + restore ────────────────────────────────────────────


class TestLocalBackup:
    def test_backup_creates_bak(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)

        result = backup(db_path)
        assert result.exists()
        assert result.suffix == ".bak"
        assert result.stat().st_size > 0

    def test_backup_missing_db_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: tmp_path / "nope.db")
        with pytest.raises(SystemExit):
            backup()

    def test_restore_round_trip(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)

        bak = backup(db_path)

        # Corrupt the original to prove restore works
        db_path.unlink()
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.close()

        restore(bak, db_path)

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT pack FROM reg_skills WHERE skill_id='core:build'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "core"

    def test_restore_creates_safety_copy(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)

        bak = backup(db_path)
        restore(bak, db_path)

        safety = db_path.with_suffix(".db.pre-restore.bak")
        assert safety.exists()

    def test_restore_invalid_file_exits(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.bak"
        bad.write_text("not a database")
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: tmp_path / "studio.db")
        with pytest.raises(SystemExit):
            restore(bad)

    def test_restore_missing_bak_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup._default_bak_path", lambda: tmp_path / "nope.bak")
        with pytest.raises(SystemExit):
            restore()


# ── Export ─────────────────────────────────────────────────────────────


class TestExport:
    def test_export_to_directory(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        backup(db_path)

        target_dir = tmp_path / "exports"
        target_dir.mkdir()
        result = export(target_dir, db_path)
        assert result.exists()
        assert result.parent == target_dir
        assert "studio-" in result.name

    def test_export_to_file_path(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        backup(db_path)

        target = tmp_path / "my-backup.db"
        result = export(target, db_path)
        assert result == target
        assert result.exists()

    def test_export_creates_backup_if_missing(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        monkeypatch.setattr("scripts.studio_backup._default_bak_path", lambda: db_path.with_suffix(".db.bak"))

        target = tmp_path / "out.bak"
        result = export(target, db_path)
        assert result.exists()


# ── Cloud config ───────────────────────────────────────────────────────


class TestCloudConfig:
    def test_save_and_load_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._backup_config_path", lambda: tmp_path / "backup-config.json")

        _save_backup_config({"remote": "gdrive:backups", "auto_push": True})
        loaded = _load_backup_config()
        assert loaded["remote"] == "gdrive:backups"
        assert loaded["auto_push"] is True

    def test_load_missing_config_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup._backup_config_path", lambda: tmp_path / "nope.json")
        assert _load_backup_config() == {}

    def test_cloud_auto_toggles(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "backup-config.json"
        cfg_path.write_text(json.dumps({"remote": "test:bak"}), encoding="utf-8")
        monkeypatch.setattr("scripts.studio_backup._backup_config_path", lambda: cfg_path)
        monkeypatch.setattr("scripts.studio_backup._load_backup_config", lambda: json.loads(cfg_path.read_text(encoding="utf-8")))
        monkeypatch.setattr("scripts.studio_backup._save_backup_config", lambda d: cfg_path.write_text(json.dumps(d), encoding="utf-8"))

        cloud_auto()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["auto_push"] is True

        cloud_auto()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["auto_push"] is False


# ── Cloud push/pull with mock rclone ───────────────────────────────────


class TestCloudWithMockRclone:
    def test_cloud_push_calls_rclone(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        bak_path = db_path.with_suffix(".db.bak")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        monkeypatch.setattr("scripts.studio_backup._default_bak_path", lambda: bak_path)
        backup(db_path)

        cfg_path = tmp_path / "backup-config.json"
        cfg_path.write_text(json.dumps({"remote": "test:backups"}), encoding="utf-8")
        monkeypatch.setattr("scripts.studio_backup._backup_config_path", lambda: cfg_path)

        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        monkeypatch.setattr("scripts.studio_backup._has_rclone", lambda: True)
        monkeypatch.setattr("scripts.studio_backup._rclone_run", lambda args: mock_result)

        from scripts.studio_backup import cloud_push
        cloud_push()

        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "last_push" in data

    def test_cloud_push_no_rclone_exits(self, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup._has_rclone", lambda: False)
        with pytest.raises(SystemExit):
            from scripts.studio_backup import cloud_push
            cloud_push()

    def test_cloud_push_no_config_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.studio_backup._has_rclone", lambda: True)
        monkeypatch.setattr("scripts.studio_backup._backup_config_path", lambda: tmp_path / "nope.json")
        with pytest.raises(SystemExit):
            from scripts.studio_backup import cloud_push
            cloud_push()


# ── Auto-push integration with pulse ──────────────────────────────────


class TestAutoPushIntegration:
    def test_maybe_cloud_push_fires_when_enabled(self, tmp_path, monkeypatch):
        cfg = {"remote": "test:bak", "auto_push": True}
        cfg_path = tmp_path / "backup-config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        monkeypatch.setattr("hooks.lib.state.paths.state_dir", lambda: tmp_path)

        mock_popen = MagicMock()
        monkeypatch.setattr("hooks.lib.state.subprocess.Popen", mock_popen)

        from hooks.lib import studio_db
        monkeypatch.setattr(studio_db, "set_sentinel", lambda *a, **kw: True)

        _maybe_cloud_push()
        mock_popen.assert_called_once()

    def test_maybe_cloud_push_skips_when_disabled(self, tmp_path, monkeypatch):
        cfg = {"remote": "test:bak", "auto_push": False}
        cfg_path = tmp_path / "backup-config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        monkeypatch.setattr("hooks.lib.state.paths.state_dir", lambda: tmp_path)

        mock_popen = MagicMock()
        monkeypatch.setattr("hooks.lib.state.subprocess.Popen", mock_popen)

        _maybe_cloud_push()
        mock_popen.assert_not_called()

    def test_maybe_cloud_push_skips_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hooks.lib.state.paths.state_dir", lambda: tmp_path)

        mock_popen = MagicMock()
        monkeypatch.setattr("hooks.lib.state.subprocess.Popen", mock_popen)

        _maybe_cloud_push()
        mock_popen.assert_not_called()

    def test_backup_db_triggers_auto_push(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("hooks.lib.state.paths.state_dir", lambda: tmp_path)

        push_called = []
        monkeypatch.setattr("hooks.lib.state._maybe_cloud_push", lambda: push_called.append(True))

        result = backup_db()
        assert result is not None
        assert len(push_called) == 1


# ── CLI argument parsing ──────────────────────────────────────────────


class TestCLI:
    def test_default_runs_backup(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)

        main([])
        assert db_path.with_suffix(".db.bak").exists()

    def test_restore_flag(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        monkeypatch.setattr("scripts.studio_backup._default_bak_path", lambda: db_path.with_suffix(".db.bak"))
        backup(db_path)

        main(["--restore"])
        assert db_path.with_suffix(".db.pre-restore.bak").exists()

    def test_export_flag(self, tmp_path, monkeypatch):
        db_path = _seed_db(tmp_path / "studio.db")
        monkeypatch.setattr("scripts.studio_backup.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("scripts.studio_backup._db_path", lambda: db_path)
        monkeypatch.setattr("scripts.studio_backup._default_bak_path", lambda: db_path.with_suffix(".db.bak"))
        backup(db_path)

        target = tmp_path / "exported.bak"
        main(["--export", str(target)])
        assert target.exists()

    def test_cloud_no_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main(["--cloud"])

    def test_cloud_invalid_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main(["--cloud", "bogus"])
