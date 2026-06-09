from __future__ import annotations

from pathlib import Path

from integrations.installer.file_ops import atomic_write, backup_before_write


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "output.txt"
    atomic_write(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "subdir" / "nested" / "file.txt"
    atomic_write(target, "content")
    assert target.exists()


def test_atomic_write_no_temp_file_left_on_success(tmp_path):
    target = tmp_path / "file.txt"
    atomic_write(target, "data")
    assert not (tmp_path / "file.txt.tmp").exists()


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    atomic_write(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_backup_before_write_copies_existing_file(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text('{"key": "value"}', encoding="utf-8")
    backup_dir = tmp_path / "backups"
    backup_path = backup_before_write(target, backup_dir)
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == '{"key": "value"}'


def test_backup_before_write_creates_backup_dir(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("original", encoding="utf-8")
    backup_dir = tmp_path / "new_backup_dir"
    backup_path = backup_before_write(target, backup_dir)
    assert backup_dir.exists()
    assert backup_path.exists()


def test_backup_before_write_returns_path_even_if_no_source(tmp_path):
    target = tmp_path / "nonexistent.txt"
    backup_dir = tmp_path / "backups"
    backup_path = backup_before_write(target, backup_dir)
    assert isinstance(backup_path, Path)
    assert not backup_path.exists()


def test_backup_path_contains_timestamp(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    backup_path = backup_before_write(target, backup_dir)
    assert "T" in backup_path.name
    assert ".bak" in backup_path.name
