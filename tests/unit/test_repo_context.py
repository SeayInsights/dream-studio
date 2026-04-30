"""Tests for hooks/lib/repo_context.py — stack detection, schema, edge cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.repo_context import (  # noqa: E402
    _detect_stack,
    _git_hash,
    generate_snapshot,
)


# ---------------------------------------------------------------------------
# Stack detection — language heuristics
# ---------------------------------------------------------------------------


def test_typescript_detected_when_package_json_and_tsconfig(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["language"] == "typescript"


def test_javascript_detected_when_package_json_only(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["language"] == "javascript"


def test_python_detected_from_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["language"] == "python"


def test_rust_detected_from_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["language"] == "rust"


def test_go_detected_from_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/m\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["language"] == "go"


def test_empty_directory_has_all_null_stack_fields(tmp_path):
    stack = _detect_stack(tmp_path)
    assert stack["language"] is None
    assert stack["framework"] is None
    assert stack["runtime"] is None
    assert stack["db"] is None
    assert stack["orm"] is None


# ---------------------------------------------------------------------------
# Stack detection — framework / runtime heuristics
# ---------------------------------------------------------------------------


def test_astro_framework_detected_from_config_file(tmp_path):
    (tmp_path / "astro.config.mjs").write_text("export default {}\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["framework"] == "astro"


def test_wrangler_toml_sets_cloudflare_workers_runtime(tmp_path):
    (tmp_path / "wrangler.toml").write_text("[main]\nname = 'worker'\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["runtime"] == "cloudflare-workers"


def test_wrangler_toml_with_d1_databases_sets_db(tmp_path):
    content = "[main]\nname = 'worker'\n[[d1_databases]]\nbinding = 'DB'\n"
    (tmp_path / "wrangler.toml").write_text(content, encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["db"] == "d1"


def test_next_framework_detected_from_config_file(tmp_path):
    (tmp_path / "next.config.js").write_text("module.exports = {}\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["framework"] == "next"


def test_vite_framework_detected_from_config_file(tmp_path):
    (tmp_path / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["framework"] == "vite"


def test_prisma_orm_detected_from_schema_file(tmp_path):
    prisma_dir = tmp_path / "prisma"
    prisma_dir.mkdir()
    (prisma_dir / "schema.prisma").write_text("datasource db {}\n", encoding="utf-8")
    stack = _detect_stack(tmp_path)
    assert stack["orm"] == "prisma"


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------


def test_generate_snapshot_has_all_required_fields(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert "tree" in snapshot
    assert "stack" in snapshot
    assert "entry_points" in snapshot
    assert "dependencies" in snapshot
    assert "file_count" in snapshot
    assert "loc" in snapshot
    assert "git_hash" in snapshot


def test_snapshot_tree_is_string(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["tree"], str)


def test_snapshot_stack_is_dict(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["stack"], dict)


def test_snapshot_entry_points_is_list(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["entry_points"], list)


def test_snapshot_dependencies_is_dict(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["dependencies"], dict)


def test_snapshot_file_count_is_int(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["file_count"], int)


def test_snapshot_loc_is_int(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert isinstance(snapshot["loc"], int)


def test_snapshot_git_hash_is_string_or_none(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["git_hash"] is None or isinstance(snapshot["git_hash"], str)


def test_snapshot_is_json_serializable(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    # Must not raise
    serialized = json.dumps(snapshot)
    assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# generate_snapshot — counts source files correctly
# ---------------------------------------------------------------------------


def test_file_count_counts_source_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("x = 1\n", encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["file_count"] == 2


def test_loc_counts_lines_in_source_files(tmp_path):
    (tmp_path / "main.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["loc"] == 3


def test_non_source_files_not_counted(tmp_path):
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    # .md is NOT in SOURCE_EXTENSIONS — file_count must be 0
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["file_count"] == 0


def test_skipped_dirs_excluded_from_count(tmp_path):
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "dep.js").write_text("module.exports = {}\n", encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["file_count"] == 0


# ---------------------------------------------------------------------------
# generate_snapshot — entry point detection
# ---------------------------------------------------------------------------


def test_entry_point_main_py_detected(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert "main.py" in snapshot["entry_points"]


def test_entry_point_src_index_detected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text("", encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert "src/index.ts" in snapshot["entry_points"]


def test_no_entry_points_in_empty_directory(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["entry_points"] == []


# ---------------------------------------------------------------------------
# generate_snapshot — dependency parsing
# ---------------------------------------------------------------------------


def test_dependencies_parsed_from_package_json(tmp_path):
    pkg = {
        "dependencies": {"react": "^18.0.0", "hono": "^3.0.0"},
        "devDependencies": {"typescript": "^5.0.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["dependencies"]["prod"] == 2
    assert snapshot["dependencies"]["dev"] == 1


def test_heavy_packages_identified_in_dependencies(tmp_path):
    pkg = {"dependencies": {"react": "^18.0.0", "astro": "^4.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    snapshot = generate_snapshot(tmp_path)
    assert "react" in snapshot["dependencies"]["heavy"]
    assert "astro" in snapshot["dependencies"]["heavy"]


def test_empty_directory_returns_zero_dependency_counts(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    assert snapshot["dependencies"]["prod"] == 0
    assert snapshot["dependencies"]["dev"] == 0
    assert snapshot["dependencies"]["heavy"] == []


# ---------------------------------------------------------------------------
# git hash
# ---------------------------------------------------------------------------


def test_git_hash_is_none_in_non_git_directory(tmp_path):
    # tmp_path is guaranteed not to be a git repo
    result = _git_hash(tmp_path)
    assert result is None


def test_git_hash_returns_none_when_git_not_found(tmp_path):
    with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
        result = _git_hash(tmp_path)
    assert result is None


def test_git_hash_returns_none_on_nonzero_returncode(tmp_path):
    import subprocess
    mock_result = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        result = _git_hash(tmp_path)
    assert result is None


def test_git_hash_returns_sha_on_success(tmp_path):
    import subprocess
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc1234\n", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        result = _git_hash(tmp_path)
    assert result == "abc1234"


def test_snapshot_git_hash_field_present_even_in_non_git_dir(tmp_path):
    snapshot = generate_snapshot(tmp_path)
    # Key must exist regardless of git availability
    assert "git_hash" in snapshot
