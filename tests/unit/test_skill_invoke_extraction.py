"""Direct-call tests for the A2.4 split of `_skill_invoke` into three
functions in `core.skills.invocation`:

- ``load_skill_content`` — validates specifier and reads SKILL.md
- ``record_skill_invocation`` — resolves project_id, emits spool event
- ``seed_gate_artifact_files`` — writes design-critique.md / security-scan.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-skill-ext-0001"
WO_ID = "wo-skill-ext-0001"
MILESTONE_ID = "ms-skill-ext-0001"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Skill Ext Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, ?, '', 'in_progress', 'api_endpoint', ?, ?)",
            (WO_ID, PROJECT_ID, "WO", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


@pytest.fixture
def spool_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(root))
    return root


def _read_spool_events(spool_root: Path) -> list[dict]:
    events_dir = spool_root / "spool"
    if not events_dir.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in events_dir.glob("*.json")]


# ── load_skill_content ────────────────────────────────────────────────────────


def test_load_skill_content_returns_ok_for_known_skill() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier="core:build", source_root=REPO_ROOT)
    assert result["ok"] is True
    assert result["specifier"] == "core:build"
    assert result["pack"] == "core"
    assert result["mode"] == "build"
    assert isinstance(result["skill_path"], Path)
    assert result["skill_path"].is_file()
    assert "skill_content" in result and len(result["skill_content"]) > 0


def test_load_skill_content_rejects_malformed_specifier_no_colon() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier="build", source_root=REPO_ROOT)
    assert result["ok"] is False
    assert "Unknown skill: build" in result["error"]


def test_load_skill_content_rejects_malformed_specifier_slash() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier="core/build", source_root=REPO_ROOT)
    assert result["ok"] is False
    assert "Unknown skill: core/build" in result["error"]


def test_load_skill_content_rejects_unknown_pack() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier="nonexistent:build", source_root=REPO_ROOT)
    assert result["ok"] is False
    assert "Unknown skill: nonexistent:build" in result["error"]


def test_load_skill_content_rejects_unknown_mode() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier="core:nonexistent", source_root=REPO_ROOT)
    assert result["ok"] is False
    assert "Unknown skill: core:nonexistent" in result["error"]


# ── record_skill_invocation ───────────────────────────────────────────────────


def test_record_skill_invocation_emits_skill_invoked_event(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import record_skill_invocation

    result = record_skill_invocation(
        specifier="core:build",
        target=None,
        work_order_id=None,
        project_id=None,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["event_emitted"] is True

    events = _read_spool_events(spool_root)
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "skill.invoked"
    assert ev["skill_id"] == "ds-core"
    assert ev["mode"] == "build"
    assert ev["invocation_mode"] == "direct"
    assert ev["payload"]["skill_specifier"] == "core:build"


def test_record_skill_invocation_pipeline_mode_with_work_order(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import record_skill_invocation

    result = record_skill_invocation(
        specifier="security:scan",
        target="src/auth.py",
        work_order_id=WO_ID,
        project_id=None,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["invocation_mode"] == "pipeline"
    events = _read_spool_events(spool_root)
    assert events[0]["invocation_mode"] == "pipeline"
    assert events[0]["payload"]["work_order_id"] == WO_ID
    assert events[0]["payload"]["target"] == "src/auth.py"


def test_record_skill_invocation_resolves_project_id_from_work_order(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import record_skill_invocation

    result = record_skill_invocation(
        specifier="core:build",
        target=None,
        work_order_id=WO_ID,
        project_id=None,  # not supplied; should be resolved from WO
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["resolved_project_id"] == PROJECT_ID


def test_record_skill_invocation_prefers_explicit_project_id(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import record_skill_invocation

    result = record_skill_invocation(
        specifier="core:build",
        target=None,
        work_order_id=WO_ID,
        project_id="explicit-pid-override",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["resolved_project_id"] == "explicit-pid-override"


# ── seed_gate_artifact_files ──────────────────────────────────────────────────


def test_seed_gate_artifacts_no_op_without_work_order_or_milestone(tmp_path: Path) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    result = seed_gate_artifact_files(
        specifier="website:critique",
        target=None,
        work_order_id=None,
        milestone_id=None,
        project_id=None,
        planning_root=tmp_path / ".planning",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["artifacts_written"] == []
    assert result["design_brief_seeded"] is False


def test_seed_gate_artifacts_writes_design_critique_template(tmp_path: Path) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    planning_root = tmp_path / ".planning"
    result = seed_gate_artifact_files(
        specifier="website:critique",
        target="src/page.tsx",
        work_order_id=WO_ID,
        milestone_id=None,
        project_id=None,
        planning_root=planning_root,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    artifact = planning_root / "work-orders" / WO_ID / "design-critique.md"
    assert artifact.is_file()
    content = artifact.read_text(encoding="utf-8")
    assert f"Work Order {WO_ID}" in content
    assert "Score: [PENDING]/4" in content
    assert "Visual Hierarchy" in content
    assert "[PASS/FAIL]" in content
    assert "src/page.tsx" in content
    assert str(artifact) in result["artifacts_written"]


def test_seed_gate_artifacts_writes_security_scan_template(tmp_path: Path) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    planning_root = tmp_path / ".planning"
    seed_gate_artifact_files(
        specifier="security:scan",
        target=None,
        work_order_id=WO_ID,
        milestone_id=None,
        project_id=None,
        planning_root=planning_root,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    artifact = planning_root / "work-orders" / WO_ID / "security-scan.md"
    assert artifact.is_file()
    content = artifact.read_text(encoding="utf-8")
    assert f"Work Order {WO_ID}" in content
    assert "Status: [PENDING]" in content
    assert "[PASS/BLOCKED]" in content


def test_seed_gate_artifacts_routes_to_milestone_dir(tmp_path: Path) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    planning_root = tmp_path / ".planning"
    seed_gate_artifact_files(
        specifier="website:critique",
        target=None,
        work_order_id=None,
        milestone_id=MILESTONE_ID,
        project_id=None,
        planning_root=planning_root,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert (planning_root / "milestones" / MILESTONE_ID / "design-critique.md").is_file()


def test_seed_gate_artifacts_no_op_for_unrelated_specifier(tmp_path: Path) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    planning_root = tmp_path / ".planning"
    result = seed_gate_artifact_files(
        specifier="core:build",
        target=None,
        work_order_id=WO_ID,
        milestone_id=None,
        project_id=None,
        planning_root=planning_root,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["artifacts_written"] == []
    assert result["design_brief_seeded"] is False
    # The WO dir is created (legacy behavior) but no artifact is written.
    assert not (planning_root / "work-orders" / WO_ID / "design-critique.md").exists()
    assert not (planning_root / "work-orders" / WO_ID / "security-scan.md").exists()


def test_seed_gate_artifacts_website_discover_seeds_design_brief(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    result = seed_gate_artifact_files(
        specifier="website:discover",
        target=None,
        work_order_id=WO_ID,
        milestone_id=None,
        project_id=PROJECT_ID,
        planning_root=tmp_path / ".planning",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["design_brief_seeded"] is True

    with sqlite3.connect(str(db_path)) as conn:
        brief_count = conn.execute(
            "SELECT COUNT(*) FROM business_design_briefs WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()[0]
    assert brief_count == 1


def test_seed_gate_artifacts_website_discover_skips_when_brief_exists(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.skills.invocation import seed_gate_artifact_files

    # Pre-seed a brief for the project.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_design_briefs"
        " (brief_id, project_id, status, created_at, updated_at)"
        " VALUES (?, ?, 'draft', ?, ?)",
        ("brief-existing", PROJECT_ID, NOW, NOW),
    )
    conn.commit()
    conn.close()

    result = seed_gate_artifact_files(
        specifier="website:discover",
        target=None,
        work_order_id=WO_ID,
        milestone_id=None,
        project_id=PROJECT_ID,
        planning_root=tmp_path / ".planning",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["design_brief_seeded"] is False

    with sqlite3.connect(str(db_path)) as conn:
        brief_count = conn.execute(
            "SELECT COUNT(*) FROM business_design_briefs WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()[0]
    assert brief_count == 1  # still only the pre-seeded one
