"""The work-order type registry: what it holds, what it refuses, and who reads it.

Two questions, kept apart.

1. EQUIVALENCE. The registry replaced a closed tuple and four private subsets spread over
   four modules. The expected values below are those old tables, copied from the code as it
   stood before the registry (core/work_orders/models.py WORK_ORDER_TYPES,
   review_rules._TYPE_ARTIFACT, brief_currency._UI_TYPES, milestones/close._UI_WO_TYPES and
   start_shared._UI_WO_TYPES, close_main._VERIFY_EXEMPT_TYPES). They are spelled out here on
   purpose: a test that derived them from the registry would agree with any registry.

2. WIRING. Equivalence for the ten built-ins says nothing about whether a consumer READS the
   registry. Each consumer is exercised with a type registered at runtime, a type no
   hardcoded table has ever heard of, and must treat it as the registry says.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import type_registry
from core.work_orders.type_registry import (
    CODE,
    CONFIG,
    DATA,
    DOCUMENT,
    artifact_class_for,
    design_brief_staling_types,
    get_work_order_type,
    is_ui_bearing,
    is_verification_exempt,
    register_work_order_type,
    work_order_type_names,
)

# ── the old values, captured before the registry existed ──────────────────────

OLD_TYPES = (
    "api_endpoint",
    "authentication",
    "data_pipeline",
    "deployment",
    "documentation",
    "game_mechanic",
    "infrastructure",
    "saas_feature",
    "ui_component",
    "ui_page",
)
OLD_ARTIFACT = {
    "ui_component": CODE,
    "ui_page": CODE,
    "api_endpoint": CODE,
    "authentication": CODE,
    "saas_feature": CODE,
    "game_mechanic": CODE,
    "data_pipeline": DATA,
    "deployment": CONFIG,
    "infrastructure": CONFIG,
    "documentation": DOCUMENT,
}
OLD_UI_BEARING = frozenset({"ui_component", "ui_page"})  # milestones/close, start_shared
OLD_BRIEF_STALING = frozenset({"ui_component", "ui_page", "saas_feature"})  # brief_currency
OLD_VERIFY_EXEMPT = frozenset({"documentation"})  # close_main

NOW = "2026-10-19T00:00:00+00:00"


@pytest.fixture
def clean_registry(monkeypatch):
    """A private copy of the registry, restored when the test ends."""
    monkeypatch.setattr(type_registry, "_REGISTRY", dict(type_registry._REGISTRY))


# ── equivalence ───────────────────────────────────────────────────────────────


def test_the_built_ins_are_the_old_ten_in_the_old_order():
    assert work_order_type_names() == OLD_TYPES


@pytest.mark.parametrize("name", OLD_TYPES)
def test_each_built_in_yields_what_the_old_tables_yielded(name):
    assert artifact_class_for(name) == OLD_ARTIFACT[name]
    assert is_ui_bearing(name) is (name in OLD_UI_BEARING)
    assert (name in design_brief_staling_types()) is (name in OLD_BRIEF_STALING)
    assert is_verification_exempt(name) is (name in OLD_VERIFY_EXEMPT)


def test_the_derived_subsets_equal_the_old_subsets():
    assert {t for t in work_order_type_names() if is_ui_bearing(t)} == OLD_UI_BEARING
    assert set(design_brief_staling_types()) == OLD_BRIEF_STALING
    assert {t for t in work_order_type_names() if is_verification_exempt(t)} == OLD_VERIFY_EXEMPT


def test_artifact_kind_matches_the_old_map_for_every_built_in_and_unknowns_stay_code():
    from core.work_orders.review_rules import artifact_kind

    for name, expected in OLD_ARTIFACT.items():
        assert artifact_kind(name) == expected
        assert artifact_kind(f"  {name.upper()} ") == expected, "normalised as before"
    assert artifact_kind("some_type_nobody_has_added_yet") == CODE
    assert artifact_kind(None) == CODE
    assert artifact_kind("") == CODE


# ── the registration API ──────────────────────────────────────────────────────


def test_registration_adds_a_type_and_appends_it_to_the_declared_order(clean_registry):
    declared = register_work_order_type("legal_review", artifact_class=DOCUMENT)
    assert get_work_order_type("legal_review") == declared
    assert work_order_type_names() == OLD_TYPES + ("legal_review",)
    assert artifact_class_for("legal_review") == DOCUMENT
    assert is_ui_bearing("legal_review") is False
    assert is_verification_exempt("legal_review") is False


def test_a_duplicate_is_refused_and_leaves_the_original_intact(clean_registry):
    with pytest.raises(ValueError, match="already registered"):
        register_work_order_type("ui_page", artifact_class=DOCUMENT)
    assert artifact_class_for("ui_page") == CODE
    assert is_ui_bearing("ui_page") is True


def test_an_unknown_artifact_class_is_refused_and_nothing_is_registered(clean_registry):
    with pytest.raises(ValueError, match="unknown artifact class 'spreadsheet'"):
        register_work_order_type("ledger", artifact_class="spreadsheet")
    assert get_work_order_type("ledger") is None


@pytest.mark.parametrize("bad", ["", "Legal", "1st", "has space", "dash-ed", None])
def test_a_malformed_name_is_refused(clean_registry, bad):
    with pytest.raises(ValueError, match="must be lowercase"):
        register_work_order_type(bad, artifact_class=CODE)


def test_a_ui_bearing_type_must_stale_the_design_brief(clean_registry):
    with pytest.raises(ValueError, match="does not stale the design brief"):
        register_work_order_type(
            "poster", artifact_class=CODE, ui_bearing=True, stales_design_brief=False
        )
    assert get_work_order_type("poster") is None


def test_ui_bearing_implies_staling_by_default_but_staling_alone_does_not_imply_ui(
    clean_registry,
):
    register_work_order_type("poster", artifact_class=CODE, ui_bearing=True)
    register_work_order_type("landing_copy", artifact_class=DOCUMENT, stales_design_brief=True)
    assert is_ui_bearing("poster") and "poster" in design_brief_staling_types()
    assert not is_ui_bearing("landing_copy") and "landing_copy" in design_brief_staling_types()


@pytest.mark.parametrize("name", [None, "", "never_registered"])
def test_accessors_answer_for_a_type_that_is_not_declared(name):
    assert get_work_order_type(name) is None
    assert artifact_class_for(name) is None
    assert is_ui_bearing(name) is False
    assert is_verification_exempt(name) is False


# ── wiring: every consumer reads the registry ─────────────────────────────────


def test_review_rules_classifies_a_registered_type_by_its_declared_class(clean_registry):
    from core.work_orders.review_rules import artifact_kind

    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    assert artifact_kind("legal_review") == DOCUMENT


def test_the_cli_type_choices_include_a_registered_type(clean_registry):
    from interfaces.cli.ds import build_parser

    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    wo = sub.choices["work-order"]
    wo_sub = next(a for a in wo._actions if getattr(a, "choices", None) and "create" in a.choices)
    type_action = next(a for a in wo_sub.choices["create"]._actions if a.dest == "work_order_type")
    assert tuple(type_action.choices) == work_order_type_names()
    assert "legal_review" in type_action.choices


def test_create_work_order_accepts_a_registered_type_and_still_names_the_valid_ones(
    clean_registry,
):
    """The type check in create_work_order is the door the MCP tool and every direct caller
    share. Whatever stops the call afterwards (no project, no authority here) is not it."""
    from core.work_orders.mutations import create_work_order

    def attempt(work_order_type: str) -> str:
        try:
            result = create_work_order(
                project_id="p-does-not-exist",
                milestone_id="m-1",
                title="A thing",
                description="A description long enough to clear the prompt floor for a work order.",
                work_order_type=work_order_type,
                source_root=Path("."),
            )
        except RuntimeError as exc:
            return str(exc)
        return result.get("error", "")

    assert "is not one the platform declares" in attempt("legal_review")
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    assert "is not one the platform declares" not in attempt("legal_review")
    refusal = attempt("still_undeclared")
    assert "legal_review" in refusal, "the refusal lists what is declared now"


def test_the_mcp_tool_enum_is_the_declared_set():
    """Read when integrations.mcp.tools is imported; a loader must register before then."""
    from integrations.mcp.tools import TOOLS_BY_NAME

    schema = TOOLS_BY_NAME["ds_work_order_create"].input_schema
    assert tuple(schema["properties"]["work_order_type"]["enum"]) == work_order_type_names()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _insert_project(db: Path) -> str:
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", NOW, NOW),
    )
    conn.commit()
    conn.close()
    return project_id


def _insert_wo(
    db: Path, project_id: str, wo_type: str, *, milestone_id: str | None = None, **cols: str
) -> str:
    wo_id = str(uuid.uuid4())
    status = cols.get("status", "created")
    closed_at = cols.get("closed_at")
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at, closed_at)"
        " VALUES (?,?,?,'t','d',?,?,?,?,?)",
        (wo_id, project_id, milestone_id, wo_type, status, NOW, NOW, closed_at),
    )
    conn.commit()
    conn.close()
    return wo_id


def test_brief_currency_judges_a_registered_type_by_its_staling_flag(db, clean_registry):
    from core.gates.brief_currency import brief_currency

    register_work_order_type("poster", artifact_class=CODE, ui_bearing=True)
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    project_id = _insert_project(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_design_briefs"
        " (brief_id, project_id, status, created_at, updated_at) VALUES (?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            project_id,
            "locked",
            "2026-05-01T00:00:00+00:00",
            "2026-05-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    _insert_wo(db, project_id, "legal_review", status="closed", closed_at=NOW)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        assert brief_currency(project_id, conn=conn, db_path=db)["current"] is True
        _insert_wo(db, project_id, "poster", status="closed", closed_at=NOW)
        info = brief_currency(project_id, conn=conn, db_path=db)
    finally:
        conn.close()
    assert info["current"] is False
    assert "poster" in info["reason"], "the verdict names the staling set from the registry"


def _insert_milestone(db: Path, project_id: str) -> str:
    milestone_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, due_date, status, created_at, updated_at)"
        " VALUES (?, ?, 'M', NULL, NULL, 'active', ?, ?)",
        (milestone_id, project_id, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return milestone_id


def test_milestone_status_owes_ui_artifacts_only_for_registered_ui_bearing_types(
    db, tmp_path, clean_registry
):
    from core.milestones.queries import get_milestone_status

    register_work_order_type("poster", artifact_class=CODE, ui_bearing=True)
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    project_id = _insert_project(db)
    plain = _insert_milestone(db, project_id)
    ui = _insert_milestone(db, project_id)
    _insert_wo(db, project_id, "legal_review", milestone_id=plain)
    _insert_wo(db, project_id, "poster", milestone_id=ui)

    def open_checks(milestone_id: str) -> list[str]:
        result = get_milestone_status(
            milestone_id=milestone_id,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / ".planning",
        )
        assert result["ok"] is True, result
        return result["open_gate_checks"]

    assert "design_audit" not in open_checks(plain)
    assert "cwv_results" not in open_checks(plain)
    assert "design_audit" in open_checks(ui)
    assert "cwv_results" in open_checks(ui)


def test_start_reads_the_design_brief_only_for_registered_ui_bearing_types(
    db, tmp_path, clean_registry
):
    from core.work_orders.start_brief import read_work_order_brief

    register_work_order_type("poster", artifact_class=CODE, ui_bearing=True)
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    conn = sqlite3.connect(str(db))
    for type_id in ("poster", "legal_review"):
        conn.execute(
            "INSERT INTO business_work_order_types (type_id, label) VALUES (?, ?)",
            (type_id, type_id),
        )
    conn.commit()
    conn.close()
    project_id = _insert_project(db)
    poster = _insert_wo(db, project_id, "poster")
    legal = _insert_wo(db, project_id, "legal_review")

    def brief_warning(work_order_id: str) -> bool:
        result = read_work_order_brief(
            work_order_id=work_order_id, source_root=tmp_path, dream_studio_home=tmp_path
        )
        assert result["ok"] is True, result
        return result["brief_warning"]

    assert brief_warning(poster) is True, "a UI-bearing type with no locked brief warns"
    assert brief_warning(legal) is False, "a type the registry does not mark UI is not asked"


def test_close_runs_independent_review_unless_the_registry_exempts_the_type(
    db, tmp_path, monkeypatch, capsys, clean_registry
):
    """Default-on review at close is skipped only for a type flagged exempt_from_verification.
    A closed work order with no review verdict fails the independent_review gate; an exempt
    one never reaches it."""
    import json

    from interfaces.cli.ds import main

    register_work_order_type("memo", artifact_class=DOCUMENT, exempt_from_verification=True)
    register_work_order_type("audit_report", artifact_class=DOCUMENT)
    conn = sqlite3.connect(str(db))
    for type_id in ("memo", "audit_report"):
        conn.execute(
            "INSERT INTO business_work_order_types (type_id, label) VALUES (?, ?)",
            (type_id, type_id),
        )
    conn.commit()
    conn.close()
    project_id = _insert_project(db)
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    def close_failures(wo_type: str) -> list[str]:
        wo_id = _insert_wo(db, project_id, wo_type, status="pushed")
        main(
            [
                "--home",
                str(tmp_path),
                "work-order",
                "close",
                wo_id,
                "--planning-root",
                str(tmp_path / ".planning"),
            ]
        )
        return json.loads(capsys.readouterr().out).get("failures", [])

    assert any("independent_review" in f for f in close_failures("audit_report"))
    assert not any("independent_review" in f for f in close_failures("memo"))


def test_milestone_close_requires_cwv_only_for_registered_ui_bearing_types(
    db, tmp_path, monkeypatch, capsys, clean_registry
):
    import json

    from interfaces.cli.ds import main

    register_work_order_type("poster", artifact_class=CODE, ui_bearing=True)
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    project_id = _insert_project(db)

    def close(wo_type: str) -> tuple[int, dict]:
        milestone_id = _insert_milestone(db, project_id)
        _insert_wo(db, project_id, wo_type, milestone_id=milestone_id, status="closed")
        artifacts = tmp_path / ".planning" / "milestones" / milestone_id
        artifacts.mkdir(parents=True)
        (artifacts / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
        (artifacts / "security-audit.md").write_text("clear\n", encoding="utf-8")
        (artifacts / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
        rc = main(
            [
                "--home",
                str(tmp_path),
                "milestone",
                "close",
                milestone_id,
                "--planning-root",
                str(tmp_path / ".planning"),
            ]
        )
        printed = capsys.readouterr().out
        return rc, (json.loads(printed) if rc else {"closed": printed})

    rc, out = close("poster")
    assert rc == 1 and any("Core Web Vitals" in f for f in out["failures"]), out
    rc, out = close("legal_review")
    assert rc == 0, out
