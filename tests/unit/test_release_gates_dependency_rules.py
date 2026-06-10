"""Tests for core/gates/dependency_rules.py — layer boundary enforcement gates.

Each rule has three tests:
  1. Clean directory passes (no false positives on clean tree).
  2. Synthetic violation fires the gate.
  3. Excluded paths (tests/, .planning/) are ignored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates.dependency_rules import (
    REPO_ROOT,
    check_rule1,
    check_rule2,
    check_rule3,
    check_rule4,
    main,
)


# ---------------------------------------------------------------------------
# Rule 1 — adapters-no-authority
# ---------------------------------------------------------------------------


def test_rule1_clean_on_current_tree() -> None:
    violations = check_rule1()
    assert violations == [], (
        f"rule1: unexpected violations in runtime/:\n"
        + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
    )


def test_rule1_fires_on_synthetic_violation(tmp_path: Path) -> None:
    bad_file = tmp_path / "runtime" / "hooks" / "on_bad.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("INSERT INTO business_work_orders (id) VALUES (?)", (wid,))\n',
        encoding="utf-8",
    )
    violations = check_rule1(repo_root=tmp_path)
    assert len(violations) == 1
    assert violations[0][0] == bad_file
    assert "INSERT INTO business_work_orders" in violations[0][2]


def test_rule1_comment_lines_are_ignored(tmp_path: Path) -> None:
    safe_file = tmp_path / "runtime" / "hooks" / "on_safe.py"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text(
        "# INSERT INTO business_work_orders -- this is a comment only\n",
        encoding="utf-8",
    )
    violations = check_rule1(repo_root=tmp_path)
    assert violations == []


# ---------------------------------------------------------------------------
# Rule 2 — projections-readonly
# ---------------------------------------------------------------------------


def test_rule2_clean_on_current_tree() -> None:
    violations = check_rule2()
    assert violations == [], (
        f"rule2: unexpected violations in projections/api/ or projections/core/:\n"
        + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
    )


def test_rule2_fires_on_synthetic_violation(tmp_path: Path) -> None:
    bad_file = tmp_path / "projections" / "api" / "routes" / "bad_route.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("INSERT INTO raw_sessions (session_id) VALUES (?)", (sid,))\n',
        encoding="utf-8",
    )
    violations = check_rule2(repo_root=tmp_path)
    assert len(violations) == 1
    assert violations[0][0] == bad_file


def test_rule2_excludes_projections_tests_dir(tmp_path: Path) -> None:
    # Test fixtures legitimately INSERT data — they must not be flagged.
    test_file = tmp_path / "projections" / "tests" / "test_collectors.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'db.execute("INSERT INTO raw_sessions (session_id) VALUES (?)", (sid,))\n',
        encoding="utf-8",
    )
    violations = check_rule2(repo_root=tmp_path)
    assert violations == []


# ---------------------------------------------------------------------------
# Rule 3 — cli-business-state-writer (advisory)
# ---------------------------------------------------------------------------


def test_rule3_clean_on_current_tree() -> None:
    violations = check_rule3()
    assert violations == [], (
        f"rule3: unexpected business_* writes in projections/api/routes/:\n"
        + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
    )


def test_rule3_fires_on_synthetic_violation(tmp_path: Path) -> None:
    bad_file = tmp_path / "projections" / "api" / "routes" / "bad_route.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("UPDATE business_work_orders SET status=? WHERE id=?", (s, wid))\n',
        encoding="utf-8",
    )
    violations = check_rule3(repo_root=tmp_path)
    assert len(violations) == 1
    assert "UPDATE business_work_orders" in violations[0][2]


def test_rule3_is_advisory_via_main(tmp_path: Path, monkeypatch) -> None:
    # Even with a violation, main() exits 0 for rule3 (advisory).
    bad_file = tmp_path / "projections" / "api" / "routes" / "bad_route.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("UPDATE business_tasks SET status=? WHERE id=?", (s, tid))\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("core.gates.dependency_rules.REPO_ROOT", tmp_path)
    result = main(["rule3"])
    assert result == 0, "rule3 is advisory — must not block (exit 0) even with violations"


# ---------------------------------------------------------------------------
# Rule 4 — ingestor-sole-event-writer
# ---------------------------------------------------------------------------


def test_rule4_clean_on_current_tree() -> None:
    violations = check_rule4()
    assert violations == [], (
        f"rule4: unexpected INSERT INTO canonical_events in production source:\n"
        + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
    )


def test_rule4_fires_on_synthetic_violation(tmp_path: Path) -> None:
    bad_file = tmp_path / "core" / "bad_module.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("INSERT INTO canonical_events VALUES (?,?,?,?)", (e,t,ts,p))\n',
        encoding="utf-8",
    )
    violations = check_rule4(repo_root=tmp_path)
    assert len(violations) == 1
    assert violations[0][0] == bad_file


def test_rule4_excludes_tests_dir(tmp_path: Path) -> None:
    # Test fixtures build canonical_events as a regular table — must be ignored.
    test_file = tmp_path / "tests" / "unit" / "test_something.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'db.execute("INSERT INTO canonical_events VALUES (?,?,?,?)", (e,t,ts,p))\n',
        encoding="utf-8",
    )
    violations = check_rule4(repo_root=tmp_path)
    assert violations == []


def test_rule4_excludes_planning_dir(tmp_path: Path) -> None:
    planning_file = tmp_path / ".planning" / "debug_patterns.py"
    planning_file.parent.mkdir(parents=True)
    planning_file.write_text(
        'conn.execute("INSERT INTO canonical_events VALUES (?,?,?,?)", (e,t,ts,p))\n',
        encoding="utf-8",
    )
    violations = check_rule4(repo_root=tmp_path)
    assert violations == []


# ---------------------------------------------------------------------------
# Gate registration in pre-push manifest
# ---------------------------------------------------------------------------


def test_dependency_rule_gates_registered_in_pre_push_manifest() -> None:
    manifest_path = REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"
    assert manifest_path.is_file(), "pre-push.yaml must exist"
    content = manifest_path.read_text(encoding="utf-8")
    assert "rule1-adapters-no-authority" in content
    assert "rule2-projections-readonly" in content
    assert "rule3-cli-business-state-writer" in content
    assert "rule4-ingestor-sole-event-writer" in content


def test_blocking_rules_exit_nonzero_on_violation(tmp_path: Path, monkeypatch) -> None:
    bad_file = tmp_path / "projections" / "api" / "routes" / "bad_route.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'db.execute("INSERT INTO raw_sessions (session_id) VALUES (?)", (sid,))\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("core.gates.dependency_rules.REPO_ROOT", tmp_path)
    result = main(["rule2"])
    assert result == 1, "rule2 is blocking — must exit 1 on violation"
