"""Tests: WO-RT runtime self-containment.

Verifies:
1. _get_plugin_root() resolves from .plugin-root sidecar (not CLAUDE_PLUGIN_ROOT or parents[N])
2. _get_source_root() resolves from .ds-source-root sidecar
3. All four handler packs are projected by _collect_hook_file_ops()
4. ds work-order next <project_id> CLI delegates to get_next_work_order
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# _get_plugin_root / _get_source_root (emitters/claude_code/run.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
def hooks_sandbox(tmp_path: Path) -> Path:
    """Simulate an installed ~/.claude/hooks/ directory with sidecars."""
    installed_dir = tmp_path / "hooks"
    installed_dir.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (installed_dir / ".plugin-root").write_text(str(installed_dir) + "\n", encoding="utf-8")
    (installed_dir / ".ds-source-root").write_text(str(repo_dir) + "\n", encoding="utf-8")
    return installed_dir


def _load_run_py_from(hooks_dir: Path) -> ModuleType:
    """Load emitters/claude_code/run.py as if it were installed at hooks_dir/run.py."""
    repo_run = Path(__file__).resolve().parents[3] / "emitters" / "claude_code" / "run.py"
    spec = importlib.util.spec_from_file_location("_run_installed", str(repo_run))
    mod = importlib.util.module_from_spec(spec)
    # Patch __file__ so sidecar lookups resolve relative to hooks_dir
    mod.__file__ = str(hooks_dir / "run.py")
    # We don't exec_module because _get_plugin_root reads __file__ dynamically
    spec.loader.exec_module(mod)
    return mod


def test_get_plugin_root_reads_sidecar(hooks_sandbox: Path) -> None:
    """_get_plugin_root() uses .plugin-root sidecar, not CLAUDE_PLUGIN_ROOT."""
    with patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": "/should/not/be/used"}):
        mod = _load_run_py_from(hooks_sandbox)
        result = mod._get_plugin_root()
    assert result == hooks_sandbox.resolve()


def test_get_plugin_root_no_env_needed(hooks_sandbox: Path) -> None:
    """_get_plugin_root() works without CLAUDE_PLUGIN_ROOT set."""
    env = {k: v for k, v in __import__("os").environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    with patch.dict("os.environ", env, clear=True):
        mod = _load_run_py_from(hooks_sandbox)
        result = mod._get_plugin_root()
    assert result == hooks_sandbox.resolve()


def test_get_plugin_root_fallback_when_sidecar_missing(tmp_path: Path) -> None:
    """Without sidecar, _get_plugin_root() falls back to the file's parent dir."""
    empty_dir = tmp_path / "hooks"
    empty_dir.mkdir()
    mod = _load_run_py_from(empty_dir)
    result = mod._get_plugin_root()
    assert result == empty_dir.resolve()


def test_get_source_root_reads_sidecar(hooks_sandbox: Path) -> None:
    """_get_source_root() returns the repo root from .ds-source-root sidecar."""
    repo_dir = hooks_sandbox.parent / "repo"
    mod = _load_run_py_from(hooks_sandbox)
    result = mod._get_source_root()
    assert result == repo_dir.resolve()


def test_get_source_root_returns_none_when_missing(tmp_path: Path) -> None:
    """_get_source_root() returns None when .ds-source-root is absent."""
    empty_dir = tmp_path / "hooks"
    empty_dir.mkdir()
    mod = _load_run_py_from(empty_dir)
    assert mod._get_source_root() is None


# ---------------------------------------------------------------------------
# Installer: _collect_hook_file_ops projects all four packs
# ---------------------------------------------------------------------------


def test_installer_projects_all_packs(tmp_path: Path) -> None:
    """_collect_hook_file_ops projects meta, quality, domains, core (and security if present)."""
    repo_root = Path(__file__).resolve().parents[3]
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    backup_base = tmp_path / "backup"
    backup_base.mkdir()

    from integrations.installer.claude_code import _collect_hook_file_ops

    ops = _collect_hook_file_ops(
        source_root=repo_root,
        hooks_dir=hooks_dir,
        repo_root=repo_root,
        backup_base=backup_base,
    )

    targets = {op.target for op in ops}
    packs_with_handlers = set()
    for t in targets:
        try:
            rel = t.relative_to(hooks_dir)
            parts = rel.parts
            if len(parts) >= 4 and parts[0] == "runtime" and parts[1] == "hooks":
                packs_with_handlers.add(parts[2])
        except ValueError:
            pass

    for required_pack in ("meta", "quality", "domains", "core"):
        if (repo_root / "runtime" / "hooks" / required_pack).is_dir():
            assert (
                required_pack in packs_with_handlers
            ), f"Pack '{required_pack}' not projected. Got: {packs_with_handlers}"


def test_installer_plugin_root_sidecar_points_to_hooks_dir(tmp_path: Path) -> None:
    """.plugin-root sidecar content must be hooks_dir, not repo_root."""
    repo_root = Path(__file__).resolve().parents[3]
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    backup_base = tmp_path / "backup"
    backup_base.mkdir()

    from integrations.installer.claude_code import _collect_hook_file_ops

    ops = _collect_hook_file_ops(
        source_root=repo_root,
        hooks_dir=hooks_dir,
        repo_root=repo_root,
        backup_base=backup_base,
    )

    plugin_root_op = next((op for op in ops if op.target == hooks_dir / ".plugin-root"), None)
    assert plugin_root_op is not None, ".plugin-root op not found"
    content = plugin_root_op.source_content.strip()
    assert content == str(
        hooks_dir
    ), f".plugin-root must point to hooks_dir={hooks_dir}, got: {content!r}"
    assert content != str(
        repo_root
    ), ".plugin-root must NOT point to repo_root — breaks self-containment"


def test_installer_ds_source_root_sidecar_points_to_repo(tmp_path: Path) -> None:
    """.ds-source-root sidecar content must be repo_root."""
    repo_root = Path(__file__).resolve().parents[3]
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    backup_base = tmp_path / "backup"
    backup_base.mkdir()

    from integrations.installer.claude_code import _collect_hook_file_ops

    ops = _collect_hook_file_ops(
        source_root=repo_root,
        hooks_dir=hooks_dir,
        repo_root=repo_root,
        backup_base=backup_base,
    )

    source_root_op = next((op for op in ops if op.target == hooks_dir / ".ds-source-root"), None)
    assert source_root_op is not None, ".ds-source-root op not found"
    assert source_root_op.source_content.strip() == str(repo_root)


# ---------------------------------------------------------------------------
# ds work-order next CLI
# ---------------------------------------------------------------------------


def test_work_order_next_cli_delegates_to_query(tmp_path: Path) -> None:
    """ds work-order next calls get_next_work_order with the given project_id."""
    called_with: dict = {}

    def fake_get_next(*, project_id, source_root, dream_studio_home):
        called_with["project_id"] = project_id
        return {"ok": True, "work_order": None, "message": "No open work orders"}

    repo_root = Path(__file__).resolve().parents[3]

    with patch("core.projects.queries.get_next_work_order", fake_get_next):
        from interfaces.cli.commands.work_order import _work_order_next

        result = _work_order_next(
            project_id="test-proj-id",
            source_root=repo_root,
            dream_studio_home=None,
        )

    assert called_with["project_id"] == "test-proj-id"
    assert result == 0
