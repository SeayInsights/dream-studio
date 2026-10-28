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
def clean_registry():
    """Whatever the test registers is gone when it ends. Scoped, never a global unregister."""
    with type_registry.scoped_registration():
        yield


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


#: The presentation order and sentences of the hand-kept list in integrations/compiler/agents_md.py
#: (`_WO_TYPES`) the registry now owns. Copied from it, not derived from the registry.
OLD_PRESENTATION = (
    ("ui_component", "Building a reusable UI element (button, card, modal, chart)"),
    ("ui_page", "Building a complete screen/view with navigation and layout"),
    (
        "api_endpoint",
        "Adding or modifying a backend route, including request/response contract",
    ),
    ("authentication", "Implementing login, session management, OAuth, or token handling"),
    ("saas_feature", "A user-facing product capability that spans UI + API (e.g., billing)"),
    ("data_pipeline", "ETL, ingestion, transformation, or batch processing work"),
    ("game_mechanic", "A gameplay rule, interaction system, or physics behavior"),
    (
        "deployment",
        "CI/CD pipeline, containerization, infrastructure-as-code, release automation",
    ),
    ("infrastructure", "Database schema, cloud resource provisioning, network configuration"),
    ("documentation", "Technical specs, API references, architecture decision records"),
)


def test_the_registry_holds_the_old_presentation_order_and_sentences():
    from core.work_orders.type_registry import work_order_types_in_presentation_order

    built_in = [t for t in work_order_types_in_presentation_order() if t.declared_by is None][:10]
    assert tuple((t.name, t.description) for t in built_in) == OLD_PRESENTATION
    assert tuple(type_registry.builtin_work_order_type_names()) == OLD_TYPES


def test_a_registered_type_follows_every_built_in_in_presentation_order(clean_registry):
    from core.work_orders.type_registry import work_order_types_in_presentation_order

    register_work_order_type("first_added", artifact_class=CODE, description="One")
    register_work_order_type("second_added", artifact_class=CODE, description="Two")
    names = [t.name for t in work_order_types_in_presentation_order()]
    assert names[-2:] == ["first_added", "second_added"]
    assert names[:10] == [name for name, _ in OLD_PRESENTATION]


def test_an_explicit_order_places_a_type_among_the_built_ins(clean_registry):
    from core.work_orders.type_registry import work_order_types_in_presentation_order

    register_work_order_type("early", artifact_class=CODE, order=5, description="Before UI")
    assert work_order_types_in_presentation_order()[0].name == "early"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"description": 5}, "description must be a string"),
        ({"description": "two\nlines"}, "printable line"),
        ({"description": "has | pipe"}, "printable line"),
        ({"description": "x" * 201}, "at most 200"),
        ({"order": -1}, "non-negative integer"),
        ({"order": True}, "non-negative integer"),
        ({"order": "1"}, "non-negative integer"),
        ({"dashboard_truth_gated": "yes"}, "dashboard_truth_gated must be a bool"),
    ],
)
def test_the_new_fields_are_validated_like_the_old_ones(clean_registry, kwargs, match):
    with pytest.raises(ValueError, match=match):
        register_work_order_type("poster", artifact_class=CODE, **kwargs)
    assert get_work_order_type("poster") is None


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


@pytest.mark.parametrize("bad_class", [["code"], {"code"}, None, 3])
def test_a_non_string_artifact_class_is_a_value_error_not_a_type_error(clean_registry, bad_class):
    """An unhashable class (a list) used to escape as TypeError from the set membership
    test; every refusal this API makes is a ValueError, so a caller catches one thing."""
    with pytest.raises(ValueError, match="unknown artifact class"):
        register_work_order_type("ledger", artifact_class=bad_class)
    assert get_work_order_type("ledger") is None


@pytest.mark.parametrize("flag", ["ui_bearing", "stales_design_brief", "exempt_from_verification"])
@pytest.mark.parametrize("bad", ["no", "", 1, 0, [], None])
def test_a_flag_that_is_not_a_real_bool_is_refused(clean_registry, flag, bad):
    """ "no" is truthy: it used to register and read as UI-bearing. None is the one
    non-bool a flag may carry, and only stales_design_brief, where it means "follow
    ui_bearing"."""
    if flag == "stales_design_brief" and bad is None:
        pytest.skip("None is the documented default for stales_design_brief")
    with pytest.raises(ValueError, match=f"{flag} must be a bool"):
        register_work_order_type("poster", artifact_class=CODE, **{flag: bad})
    assert get_work_order_type("poster") is None


def test_an_overlong_name_is_refused_and_the_limit_itself_is_accepted(clean_registry):
    """The cap is pinned as the literal 64, not read from MAX_NAME_LENGTH: a test that read the
    constant would agree with any value the constant were changed to (issue #900)."""
    register_work_order_type("a" * 64, artifact_class=CODE)
    with pytest.raises(ValueError, match="at most 64"):
        register_work_order_type("a" * 65, artifact_class=CODE)
    assert get_work_order_type("a" * 65) is None
    assert get_work_order_type("a" * 64) is not None


def test_a_str_subclass_cannot_slip_past_the_length_cap(clean_registry):
    """A subclass that reports a short __len__ passed isinstance(name, str) and the cap check,
    which asks len(). The regex matched the real 100 characters; only the cap was fooled."""

    class Short(str):
        def __len__(self) -> int:
            return 1

    name = Short("a" * 100)
    assert len(name) == 1 and str.__len__(name) == 100
    with pytest.raises(ValueError, match="must be lowercase"):
        register_work_order_type(name, artifact_class=CODE)
    assert get_work_order_type("a" * 100) is None


def test_a_str_subclass_cannot_pose_as_an_allowed_artifact_class(clean_registry):
    """A subclass whose __eq__ is always true and whose hash collides with "code" is "in"
    ARTIFACT_CLASSES, so a class that is not allowed registered anyway."""

    class Spoof(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            return hash("code")

    assert Spoof("spreadsheet") in type_registry.ARTIFACT_CLASSES, "the spoof must work"
    with pytest.raises(ValueError, match="unknown artifact class"):
        register_work_order_type("ledger", artifact_class=Spoof("spreadsheet"))
    assert get_work_order_type("ledger") is None


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
    """The enum is computed when the tool is listed, not when the module is imported."""
    from integrations.mcp.tools import TOOLS_BY_NAME

    schema = TOOLS_BY_NAME["ds_work_order_create"].schema()
    assert tuple(schema["properties"]["work_order_type"]["enum"]) == work_order_type_names()


def test_a_type_registered_after_import_is_advertised_by_tools_list(clean_registry):
    """The snapshot defect (issue #897 item 3): the enum was a list built once at import, so a
    type registered afterwards was accepted by the server but never advertised. tools/list is
    what a client reads, so that is where it is asserted."""
    from integrations.mcp.server import _handle_tools_list

    def advertised() -> list[str]:
        tools = _handle_tools_list(1, {})["result"]["tools"]
        create = next(t for t in tools if t["name"] == "ds_work_order_create")
        return create["inputSchema"]["properties"]["work_order_type"]["enum"]

    assert "legal_review" not in advertised()
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    assert "legal_review" in advertised()
    assert tuple(advertised()) == work_order_type_names()


def test_the_live_enum_does_not_mutate_the_static_schema(clean_registry):
    """schema() copies: listing the tools must not write a type name into the shared dict."""
    from integrations.mcp.tools import TOOLS_BY_NAME

    tool = TOOLS_BY_NAME["ds_work_order_create"]
    assert "enum" not in tool.input_schema["properties"]["work_order_type"]
    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    tool.schema()["properties"]["work_order_type"]["enum"].append("scribble")
    assert "scribble" not in tool.schema()["properties"]["work_order_type"]["enum"]
    assert "enum" not in tool.input_schema["properties"]["work_order_type"]


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


def test_start_derives_a_profile_for_a_declared_type_with_no_row_and_writes_none(
    db, tmp_path, clean_registry
):
    """The profile of a type with no business_work_order_types row comes from its declaration:
    a label, and no gates, executor or workflow (a manifest carries none yet). Nothing is
    written, so a manifest that changes is read as it now stands rather than as a stale row."""
    from core.work_orders.start_brief import read_work_order_brief

    register_work_order_type("legal_review", artifact_class=DOCUMENT)
    project_id = _insert_project(db)
    wo = _insert_wo(db, project_id, "legal_review")
    result = read_work_order_brief(
        work_order_id=wo, source_root=tmp_path, dream_studio_home=tmp_path
    )
    assert result["ok"] is True, result
    assert result["type_id"] == "legal_review" and result["label"] == "Legal Review"
    assert [result[k] for k in ("pre_gate", "build_exec", "post_gate", "workflow_template")] == [
        None,
        None,
        None,
        None,
    ]
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_work_order_types").fetchone()[0] == 10
    finally:
        conn.close()


def test_start_refuses_an_undeclared_type_and_says_a_manifest_may_be_the_cause(db, tmp_path):
    from core.work_orders.start_brief import read_work_order_brief

    project_id = _insert_project(db)
    wo = _insert_wo(db, project_id, "legal_review")
    result = read_work_order_brief(
        work_order_id=wo, source_root=tmp_path, dream_studio_home=tmp_path
    )
    assert result["ok"] is False
    assert "legal_review" in result["error"] and "manifest" in result["error"]


def test_a_seeded_row_still_wins_over_the_derived_profile(db, tmp_path, clean_registry):
    """A built-in's real gates are read from its row, as before; derivation only fills a gap."""
    from core.work_orders.start_brief import read_work_order_brief

    project_id = _insert_project(db)
    wo = _insert_wo(db, project_id, "ui_page")
    result = read_work_order_brief(
        work_order_id=wo, source_root=tmp_path, dream_studio_home=tmp_path
    )
    assert result["ok"] is True
    assert result["pre_gate"] == "design_brief_locked"
    assert result["build_exec"] == "website:page"


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
