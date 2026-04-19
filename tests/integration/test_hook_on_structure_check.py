"""Integration tests for on-structure-check."""

from __future__ import annotations

import io
import json


def _payload(file_path: str) -> str:
    return json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}})


def test_warns_on_root_level_source_file(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Write of mymodule.py at a project root with no pyproject.toml ancestors → nudge fires."""
    # tmp_path has no .git or pyproject.toml, so it becomes the project root
    file_path = str(tmp_path / "mymodule.py")

    monkeypatch.setattr("sys.stdin", io.StringIO(_payload(file_path)))

    mod = handler("on-structure-check")
    # Patch _find_project_root to return tmp_path directly to avoid walking filesystem
    monkeypatch.setattr(mod, "_find_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Structure" in out
    assert "mymodule.py" in out


def test_no_warn_for_allowlisted_root_files(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Write of setup.py at project root → no nudge (it's in the allowlist)."""
    file_path = str(tmp_path / "setup.py")

    monkeypatch.setattr("sys.stdin", io.StringIO(_payload(file_path)))

    mod = handler("on-structure-check")
    monkeypatch.setattr(mod, "_find_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Structure" not in out


def test_no_warn_for_standard_dir(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Write of src/app.py → no nudge (src/ is a standard dir)."""
    src = tmp_path / "src"
    src.mkdir()
    file_path = str(src / "app.py")

    monkeypatch.setattr("sys.stdin", io.StringIO(_payload(file_path)))

    mod = handler("on-structure-check")
    monkeypatch.setattr(mod, "_find_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Structure" not in out


def test_no_warn_for_non_source_ext(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Write of README.md at project root → no nudge (not a source extension)."""
    file_path = str(tmp_path / "README.md")

    monkeypatch.setattr("sys.stdin", io.StringIO(_payload(file_path)))

    mod = handler("on-structure-check")
    monkeypatch.setattr(mod, "_find_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Structure" not in out


def test_warns_on_nonstandard_dir(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Write of utils/helper.py → nudge fires (utils/ is a non-standard dir name)."""
    utils = tmp_path / "utils"
    utils.mkdir()
    file_path = str(utils / "helper.py")

    monkeypatch.setattr("sys.stdin", io.StringIO(_payload(file_path)))

    mod = handler("on-structure-check")
    monkeypatch.setattr(mod, "_find_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Structure" in out
    assert "utils" in out
