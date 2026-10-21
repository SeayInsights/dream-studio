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


def test_atomic_write_writes_lf_by_default_on_every_os(tmp_path):
    target = tmp_path / "lf.txt"
    atomic_write(target, "a\nb\n")
    assert target.read_bytes() == b"a\nb\n"


def test_atomic_write_writes_the_newline_it_is_given(tmp_path):
    """`newline` is the file's own line ending, for a merge into an operator's file."""
    target = tmp_path / "crlf.txt"
    atomic_write(target, "a\nb\n", newline="\r\n")
    assert target.read_bytes() == b"a\r\nb\r\n"
    atomic_write(target, "a\nb\n", newline="\n")
    assert target.read_bytes() == b"a\nb\n"


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


def test_integration_backups_keep_their_relative_paths(tmp_path):
    """Seven __init__.py files backed up by basename left one."""
    root = tmp_path / "root"
    a, b = root / "x" / "__init__.py", root / "y" / "__init__.py"
    for f, text in ((a, "a"), (b, "b")):
        f.parent.mkdir(parents=True)
        f.write_text(text, encoding="utf-8")
    backups = tmp_path / "backups"
    first = backup_before_write(a, backups, relative_to=root)
    second = backup_before_write(b, backups, relative_to=root)
    assert first != second
    assert first.read_text(encoding="utf-8") == "a" and second.read_text(encoding="utf-8") == "b"
