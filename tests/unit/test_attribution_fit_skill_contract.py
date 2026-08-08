"""WO-ATTR-FIT-SKILLS: the attribution fit-check-and-ask behavior is wired into the skill surface.

Two-layer behavior change (engine helper = WO-ATTR-FIT-HELPER). This guard asserts the SKILL-TEXT
layer: the three attribution surfaces (ds-project scope, ds-core plan, ds-workorder pack) instruct
the agent to fit-check proposed work and STOP-AND-ASK on a weak/ambiguous fit instead of
auto-filing into the active milestone/WO — plus the concrete invocation path the skills reference
(`ds project fit-check` CLI + `fit_check_work_order` wrapper) exists and behaves.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]

# The three canonical skill files that perform (or govern) WO/task/milestone attribution.
_SKILL_FILES = [
    "canonical/skills/ds-project/SKILL.md",
    "canonical/skills/core/modes/plan/SKILL.md",
    "canonical/skills/ds-workorder/SKILL.md",
]


@pytest.mark.parametrize("rel_path", _SKILL_FILES)
def test_skill_instructs_fit_check_and_ask(rel_path: str) -> None:
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    # The concrete, runnable invocation path — not just a vague "consider fit".
    assert "ds project fit-check" in text, f"{rel_path} must reference the fit-check command"
    # The stop-and-ask instruction (the operator's "ask rather than do" requirement).
    assert "STOP AND ASK" in text, f"{rel_path} must instruct STOP AND ASK on a weak fit"
    # The verdicts that trigger the ask — asserting behavior, not just a keyword.
    assert (
        "ambiguous" in text and "no_fit" in text
    ), f"{rel_path} must name the ambiguous / no_fit verdicts that trigger the ask"


def test_fit_check_cli_subcommand_registered() -> None:
    """The skills reference `ds project fit-check`; the subcommand + its args must exist."""
    from interfaces.cli.commands import project as project_cmd

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    project_cmd.register(sub)

    args = parser.parse_args(
        ["project", "fit-check", "--title", "T", "--description", "D", "--project-id", "p"]
    )
    assert args.project_command == "fit-check"
    assert args.title == "T"
    assert args.description == "D"
    assert args.project_id == "p"


def _seed(tmp_path: Path, *, active: bool = True, with_milestones: bool = True) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        status = "active" if active else "paused"
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES ('p', 'P', ?, 't', 't')",
            (status,),
        )
        if with_milestones:
            for mid, title, desc in [
                ("m-acct", "Back-Office", "CostPoint accounting payments invoices reconciliation"),
                ("m-skill", "Skill Library", "skill packs library authoring routing marketplace"),
            ]:
                conn.execute(
                    "INSERT INTO business_milestones (milestone_id, project_id, title, description,"
                    " status, order_index, created_at, updated_at) VALUES (?,?,?,?,'active',1,'t','t')",
                    (mid, "p", title, desc),
                )
        conn.commit()
    finally:
        conn.close()
    return db


def test_wrapper_delegates_with_explicit_project_id(tmp_path: Path, monkeypatch) -> None:
    from core.projects import queries

    db = _seed(tmp_path)
    monkeypatch.setattr(queries, "_require_db", lambda *a, **k: db)

    result = queries.fit_check_work_order(
        work_title="Reconcile CostPoint invoices",
        work_description="accounting reconciliation payments",
        project_id="p",
        source_root=REPO_ROOT,
    )
    assert result["ok"] is True
    assert result["verdict"] == "clear_single"
    assert result["best"] == "m-acct"


def test_wrapper_resolves_active_project_when_id_omitted(tmp_path: Path, monkeypatch) -> None:
    from core.projects import queries

    db = _seed(tmp_path, active=True)
    monkeypatch.setattr(queries, "_require_db", lambda *a, **k: db)

    result = queries.fit_check_work_order(
        work_title="skill packs marketplace authoring",
        work_description="library routing",
        source_root=REPO_ROOT,
    )
    assert result["ok"] is True
    assert result["verdict"] == "clear_single"
    assert result["best"] == "m-skill"


def test_wrapper_errors_without_active_project(tmp_path: Path, monkeypatch) -> None:
    from core.projects import queries

    db = tmp_path / "empty.db"
    bootstrap_database(db)  # no projects seeded
    monkeypatch.setattr(queries, "_require_db", lambda *a, **k: db)

    result = queries.fit_check_work_order(work_title="anything", source_root=REPO_ROOT)
    assert result["ok"] is False
    assert "active project" in result["error"]
