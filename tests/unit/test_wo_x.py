"""Tests for WO-X: acquisition surface facade + setup overhead analyzer.

Verifies:
- acquire_project() registers via the unified write path (mutations.register_project)
- detect_stack and scan/delta reachable through the facade
- overhead analyzer flags: heavy Python MCP, permission sprawl, skill missing YAML
- ds doctor includes the overhead check in its output
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Acquisition facade tests ──────────────────────────────────────────────────


def _make_intake_result(project_id: str = "pid-test-001") -> dict:
    return {"ok": True, "project_id": project_id, "name": "test-project"}


def _make_stack_result() -> dict:
    return {"detected_stack": "python", "confidence": 0.9, "signals": []}


def test_acquire_project_registers_via_unified_path(tmp_path: Path) -> None:
    """acquire_project() must call register_project_for_intake (unified path) and not a legacy path."""
    target = tmp_path / "myrepo"
    target.mkdir()

    with (
        patch("core.projects.acquisition.register_project_for_intake") as mock_intake,
        patch("core.projects.acquisition.detect_and_persist_stack") as mock_stack,
    ):
        mock_intake.return_value = _make_intake_result()
        mock_stack.return_value = _make_stack_result()

        from core.projects.acquisition import acquire_project

        result = acquire_project(target, source_root=tmp_path)

    mock_intake.assert_called_once()
    call_kwargs = mock_intake.call_args
    # Must use write_marker=False by default (intake-lite pattern)
    assert call_kwargs.kwargs.get("write_marker") is False
    assert result["ok"] is True
    assert result["project_id"] == "pid-test-001"


def test_acquire_project_detects_stack(tmp_path: Path) -> None:
    target = tmp_path / "repo2"
    target.mkdir()

    with (
        patch("core.projects.acquisition.register_project_for_intake") as mock_intake,
        patch("core.projects.acquisition.detect_and_persist_stack") as mock_stack,
    ):
        mock_intake.return_value = _make_intake_result("pid-002")
        mock_stack.return_value = _make_stack_result()

        from core.projects.acquisition import acquire_project

        result = acquire_project(target, source_root=tmp_path)

    mock_stack.assert_called_once()
    assert result["detected_stack"] == "python"
    assert result["stack_confidence"] == 0.9


def test_acquire_project_no_scan_by_default(tmp_path: Path) -> None:
    """Without run_scan=True, no scan_id or delta_id in result."""
    target = tmp_path / "repo3"
    target.mkdir()

    with (
        patch("core.projects.acquisition.register_project_for_intake") as mock_intake,
        patch("core.projects.acquisition.detect_and_persist_stack") as mock_stack,
    ):
        mock_intake.return_value = _make_intake_result()
        mock_stack.return_value = _make_stack_result()

        from core.projects.acquisition import acquire_project

        result = acquire_project(target, source_root=tmp_path)

    assert "scan_id" not in result
    assert "delta_id" not in result


def test_acquire_project_fails_gracefully_on_bad_intake(tmp_path: Path) -> None:
    target = tmp_path / "repo4"
    target.mkdir()

    with patch("core.projects.acquisition.register_project_for_intake") as mock_intake:
        mock_intake.return_value = {"ok": False, "error": "duplicate project"}

        from core.projects.acquisition import acquire_project

        result = acquire_project(target, source_root=tmp_path)

    assert result["ok"] is False
    assert "duplicate project" in result["error"]


# ── Overhead analyzer tests ───────────────────────────────────────────────────


def test_overhead_flags_heavy_python_mcp(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = {
        "mcpServers": {
            "my-py-server": {"command": "python", "args": ["server.py"]},
            "node-server": {"command": "node", "args": ["index.js"]},
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(source_root=tmp_path, claude_dir=claude_dir)

    assert result["ok"] is True
    mcp_findings = [f for f in result["findings"] if f["check"] == "mcp_heavy_python"]
    assert len(mcp_findings) == 1
    assert mcp_findings[0]["server"] == "my-py-server"


def test_overhead_does_not_flag_node_mcp(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = {"mcpServers": {"node-server": {"command": "node", "args": ["index.js"]}}}
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(source_root=tmp_path, claude_dir=claude_dir)
    mcp_findings = [f for f in result["findings"] if f["check"] == "mcp_heavy_python"]
    assert mcp_findings == []


def test_overhead_flags_permission_sprawl(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = {"permissions": {"allow": ["Bash", "Read"], "deny": []}}
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(source_root=tmp_path, claude_dir=claude_dir)
    sprawl_findings = [f for f in result["findings"] if f["check"] == "permission_sprawl"]
    assert len(sprawl_findings) == 1
    assert "Bash" in sprawl_findings[0]["rule"]


def test_overhead_does_not_flag_specific_permissions(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = {"permissions": {"allow": ["Read", "Edit"], "deny": []}}
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(source_root=tmp_path, claude_dir=claude_dir)
    sprawl_findings = [f for f in result["findings"] if f["check"] == "permission_sprawl"]
    assert sprawl_findings == []


def test_overhead_flags_skill_missing_yaml(tmp_path: Path) -> None:
    skills_dir = tmp_path / "canonical" / "skills" / "ds-test"
    skills_dir.mkdir(parents=True)
    skill_md = skills_dir / "SKILL.md"
    # No frontmatter — just a bare heading
    skill_md.write_text("# Test Skill\n\nSome content.\n", encoding="utf-8")

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(
        source_root=tmp_path,
        claude_dir=tmp_path / "nonexistent-claude",
    )
    yaml_findings = [f for f in result["findings"] if f["check"] == "skill_missing_yaml"]
    assert len(yaml_findings) == 1
    assert "SKILL.md" in yaml_findings[0]["path"]


def test_overhead_does_not_flag_skill_with_yaml(tmp_path: Path) -> None:
    skills_dir = tmp_path / "canonical" / "skills" / "ds-ok"
    skills_dir.mkdir(parents=True)
    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text(
        textwrap.dedent("""\
            ---
            name: ds-ok
            description: Test skill with frontmatter
            pack: core
            ---
            # Test Skill
            """),
        encoding="utf-8",
    )

    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(
        source_root=tmp_path,
        claude_dir=tmp_path / "nonexistent-claude",
    )
    yaml_findings = [f for f in result["findings"] if f["check"] == "skill_missing_yaml"]
    assert yaml_findings == []


def test_overhead_pass_when_no_settings(tmp_path: Path) -> None:
    """No settings.json → no findings, status pass."""
    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(
        source_root=tmp_path,
        claude_dir=tmp_path / "no-such-claude",
    )
    assert result["ok"] is True
    assert result["status"] == "pass"
    assert result["finding_count"] == 0


def test_overhead_advisory_only_flag(tmp_path: Path) -> None:
    from core.health.overhead import run_overhead_checks

    result = run_overhead_checks(source_root=tmp_path)
    assert result["advisory_only"] is True


# ── Doctor integration test ───────────────────────────────────────────────────


def test_doctor_includes_overhead_check(tmp_path: Path) -> None:
    """run_doctor_checks() must include an 'overhead' key in checks."""
    source_root = Path(__file__).parent.parent.parent  # repo root

    with patch("core.health.doctor.run_overhead_checks") as mock_overhead:
        mock_overhead.return_value = {
            "ok": True,
            "status": "pass",
            "advisory_only": True,
            "findings": [],
            "finding_count": 0,
        }

        from core.health.doctor import run_doctor_checks

        result = run_doctor_checks(source_root=source_root)

    assert "overhead" in result["checks"]
    mock_overhead.assert_called_once()
    assert result["checks"]["overhead"]["advisory_only"] is True
